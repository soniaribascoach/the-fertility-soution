import json as _json
import os

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.few_shot_version import FewShotVersion
from app.models.user_state import UserState
from app.repositories.config import get_all_config, set_config
from app.services.brain import reload_playbooks, run_turn
from app.services.resume import resume_lead
from app.services.few_shots import load_few_shot_scenarios
from app.services.prompts import reload_layers
from app.api.admin.auth import (
    is_authenticated,
    check_rate_limit,
    record_failed_attempt,
    reset_attempts,
)
from config import settings, APP_VERSION

FEW_SHOTS_DIR = "few_shots"

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.filters["fromjson"] = lambda s: _json.loads(s) if s else {}
templates.env.filters["split_bubbles"] = lambda s: [b.strip() for b in s.split("\n\n") if b.strip()] or [s]
templates.env.globals["app_version"] = APP_VERSION

# The knowledge base and the operational knobs. Everything the brain may state as fact lives
# here, so Sonia can correct a price or a link without a deploy, and the prompt layers in
# `prompts/` carry only behaviour, never facts.
CONFIG_KEYS = [
    "kb_about", "kb_program", "kb_pricing", "kb_boundaries", "kb_team", "kb_faq",
    "kb_free_resource",
    "booking_link", "masterclass_link", "price_range",
    "years_experience", "babies_welcomed",
    "human_takeover_triggers", "qualified_tag_id",
    "handover_message_team", "handover_message_crisis", "handover_message_urgent_medical",
    "brain_model", "brain_temperature",
]


@router.get("/admin")
async def admin_root(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/admin/dashboard", status_code=302)
    return RedirectResponse("/admin/login", status_code=302)


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def dashboard_get(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    result = await db.execute(
        select(UserState)
        .where(UserState.is_ai_paused == True)  # noqa: E712
        .order_by(UserState.paused_at.desc())
    )
    paused_leads = result.scalars().all()
    return templates.TemplateResponse(
        request, "admin/dashboard.html", {"paused_leads": paused_leads}
    )


@router.post("/admin/leads/{ig_user_id}/resume")
async def lead_resume(request: Request, ig_user_id: str, db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    await resume_lead(db, ig_user_id)
    return RedirectResponse("/admin/dashboard", status_code=302)


@router.get("/admin/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse(request, "admin/login.html", {"error": None})


@router.post("/admin/login", response_class=HTMLResponse)
async def login_post(request: Request, password: str = Form(...)):
    if not check_rate_limit(request):
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"error": "Too many failed attempts. Try again in 15 minutes."},
            status_code=429,
        )

    if password == settings.admin_password:
        reset_attempts(request)
        request.session["admin_authenticated"] = True
        return RedirectResponse("/admin/config", status_code=302)

    remaining = record_failed_attempt(request)
    if remaining == 0:
        error = "Too many failed attempts. Locked out for 15 minutes."
    else:
        error = f"Invalid password. {remaining} attempt(s) remaining."
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {"error": error},
        status_code=401,
    )


@router.get("/admin/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)



@router.get("/admin/config", response_class=HTMLResponse)
async def config_get(request: Request, saved: str = None, db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    cfg = await get_all_config(db)
    for key in CONFIG_KEYS:
        cfg.setdefault(key, "")

    takeover_items = [t for t in cfg.get("human_takeover_triggers", "").split("\n") if t.strip()]

    return templates.TemplateResponse(
        request,
        "admin/config.html",
        {
            "cfg": cfg,
            "takeover_items": takeover_items,
            "saved": saved == "true",
        },
    )


@router.get("/admin/chat", response_class=HTMLResponse)
async def chat_get(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse(request, "admin/chat.html", {})


@router.post("/admin/chat")
async def chat_post(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    body = await request.json()
    messages = body.get("messages", [])

    cfg = await get_all_config(db)

    # The sandbox is stateless server-side, so lead_state is round-tripped via
    # the client. This is the surface the team tests on: it calls exactly what
    # the worker calls, so the two can never drift apart.
    last_user = next((m["content"] for m in reversed(messages)
                      if m.get("role") == "user"), "")
    result = await run_turn(
        request.app.state.openai_client, messages, cfg,
        body.get("lead_state"), ig_user_id="admin_sandbox",
        new_texts=[last_user] if last_user else [],
    )

    return JSONResponse({
        "reply": result.reply_text,
        "human_takeover": result.pause,
        "takeover_reason": result.pause_reason,
        "lead_state": result.lead_state,
        "phase": (result.lead_state or {}).get("phase"),
        "action": result.action,
        "violations": result.violations,
        "trace": result.trace,
        "usage": result.usage,
    })


@router.post("/admin/config/save")
async def config_save(request: Request, db: AsyncSession = Depends(get_db)):
    """Persist whichever of `CONFIG_KEYS` the form posted.

    Reading the keys off the form rather than declaring twenty `Form(...)` parameters means adding
    a knowledge-base field is a template change plus one entry in `CONFIG_KEYS`, and a field that
    is temporarily absent from the form no longer silently blanks its stored value.
    """
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    form = await request.form()
    for key in CONFIG_KEYS:
        if key in form:
            await set_config(db, key, str(form[key]))

    reload_layers()
    return RedirectResponse("/admin/config?saved=true", status_code=302)


# ── Few-shots ─────────────────────────────────────────────────────────────────

def _list_scenarios() -> list[str]:
    return sorted(
        f for f in os.listdir(FEW_SHOTS_DIR)
        if os.path.isfile(os.path.join(FEW_SHOTS_DIR, f)) and not f.startswith(".")
    )


@router.get("/admin/few-shots", response_class=HTMLResponse)
async def few_shots_get(request: Request, scenario: str = None, saved: str = None, db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    scenarios = _list_scenarios()
    if not scenarios:
        return templates.TemplateResponse(request, "admin/few_shots.html", {"scenarios": [], "selected": None})

    selected = scenario if scenario in scenarios else scenarios[0]

    with open(os.path.join(FEW_SHOTS_DIR, selected), "r", encoding="utf-8") as fh:
        content = fh.read()

    versions_result = await db.execute(
        select(FewShotVersion)
        .where(FewShotVersion.scenario_name == selected)
        .order_by(FewShotVersion.id.desc())
    )
    versions = versions_result.scalars().all()

    counts_result = await db.execute(
        select(FewShotVersion.scenario_name, sa_func.count(FewShotVersion.id))
        .group_by(FewShotVersion.scenario_name)
    )
    version_counts = dict(counts_result.all())

    return templates.TemplateResponse(request, "admin/few_shots.html", {
        "scenarios": scenarios,
        "selected": selected,
        "content": content,
        "versions": versions,
        "version_counts": version_counts,
        "saved": saved == "true",
    })


@router.post("/admin/few-shots/{name}/save")
async def few_shots_save(request: Request, name: str, content: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    path = os.path.join(FEW_SHOTS_DIR, name)
    if not os.path.isfile(path):
        return RedirectResponse(f"/admin/few-shots?scenario={name}", status_code=302)

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)

    db.add(FewShotVersion(scenario_name=name, content=content))
    await db.commit()

    request.app.state.few_shot_scenarios = load_few_shot_scenarios(FEW_SHOTS_DIR)
    reload_playbooks()

    return RedirectResponse(f"/admin/few-shots?scenario={name}&saved=true", status_code=302)


@router.post("/admin/few-shots/{name}/rollback/{version_id}")
async def few_shots_rollback(request: Request, name: str, version_id: int, db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    result = await db.execute(
        select(FewShotVersion).where(FewShotVersion.id == version_id, FewShotVersion.scenario_name == name)
    )
    version = result.scalar_one_or_none()
    if not version:
        return RedirectResponse(f"/admin/few-shots?scenario={name}", status_code=302)

    path = os.path.join(FEW_SHOTS_DIR, name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(version.content)

    db.add(FewShotVersion(scenario_name=name, content=version.content))
    await db.commit()

    request.app.state.few_shot_scenarios = load_few_shot_scenarios(FEW_SHOTS_DIR)
    reload_playbooks()

    return RedirectResponse(f"/admin/few-shots?scenario={name}&saved=true", status_code=302)


