import json as _json
import os

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.models.few_shot_version import FewShotVersion
from app.repositories.config import get_all_config, set_config
from app.services.ai_pipeline import generate_reply
from app.services.few_shots import load_few_shot_scenarios
from app.api.admin.auth import (
    is_authenticated,
    check_rate_limit,
    record_failed_attempt,
    reset_attempts,
)
from config import settings

FEW_SHOTS_DIR = "few_shots"

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.filters["fromjson"] = lambda s: _json.loads(s) if s else {}
templates.env.filters["split_bubbles"] = lambda s: [b.strip() for b in s.split("\n\n") if b.strip()] or [s]

CONFIG_KEYS = [
    "phase1_cta_keywords", "phase1_opening_message",
    "booking_link", "score_threshold", "prompt_scoring_rules",
    "prompt_about", "prompt_services", "prompt_tone", "prompt_flow",
    "prompt_hard_rules", "prompt_opening_variants", "prompt_qualification_questions",
    "prompt_pattern_responses", "prompt_objection_handling", "prompt_authority_proof",
    "prompt_cta_transitions",
    "medical_blocklist", "medical_deflection",
    "human_takeover_triggers",
]


@router.get("/admin")
async def admin_root(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/admin/dashboard", status_code=302)
    return RedirectResponse("/admin/login", status_code=302)


@router.get("/admin/dashboard", response_class=HTMLResponse)
async def dashboard_get(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse(request, "admin/dashboard.html", {})


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

    def _split(key):
        return [t for t in cfg.get(key, "").split("\n") if t.strip()]

    phase1_keyword_items = _split("phase1_cta_keywords")
    blocklist_items = _split("medical_blocklist")
    takeover_items = _split("human_takeover_triggers")
    hard_rule_items = _split("prompt_hard_rules")
    opening_variant_items = _split("prompt_opening_variants")
    qualification_question_items = _split("prompt_qualification_questions")
    pattern_response_items = _split("prompt_pattern_responses")
    objection_handling_items = _split("prompt_objection_handling")
    authority_proof_items = _split("prompt_authority_proof")
    cta_transition_items = _split("prompt_cta_transitions")

    return templates.TemplateResponse(
        request,
        "admin/config.html",
        {
            "cfg": cfg,
            "phase1_keyword_items": phase1_keyword_items,
            "blocklist_items": blocklist_items,
            "takeover_items": takeover_items,
            "hard_rule_items": hard_rule_items,
            "opening_variant_items": opening_variant_items,
            "qualification_question_items": qualification_question_items,
            "pattern_response_items": pattern_response_items,
            "objection_handling_items": objection_handling_items,
            "authority_proof_items": authority_proof_items,
            "cta_transition_items": cta_transition_items,
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
    last_user_text = next(
        (m["content"].lower() for m in reversed(messages) if m.get("role") == "user"), ""
    )

    import re
    if re.match(r"^https?://\S+$", last_user_text):
        return JSONResponse({"reply": None, "human_takeover": True, "takeover_reason": "media"})

    triggers = [t.strip().lower() for t in cfg.get("human_takeover_triggers", "").split("\n") if t.strip()]
    if triggers and any(t in last_user_text for t in triggers):
        return JSONResponse({"reply": None, "human_takeover": True, "takeover_reason": "keyword"})

    client = request.app.state.openai_client
    few_shot_scenarios = getattr(request.app.state, "few_shot_scenarios", {})
    raw_text, _ = await generate_reply(db, client, few_shot_scenarios, "admin_sandbox", messages)
    return JSONResponse({"reply": raw_text, "human_takeover": False})


@router.post("/admin/config/save")
async def config_save(
        request: Request,
        phase1_cta_keywords: str = Form(""),
        phase1_opening_message: str = Form(""),
        booking_link: str = Form(""),
        score_threshold: str = Form(""),
        prompt_scoring_rules: str = Form(""),
        prompt_about: str = Form(""),
        prompt_services: str = Form(""),
        prompt_tone: str = Form(""),
        prompt_flow: str = Form(""),
        prompt_hard_rules: str = Form(""),
        prompt_opening_variants: str = Form(""),
        prompt_qualification_questions: str = Form(""),
        prompt_pattern_responses: str = Form(""),
        prompt_objection_handling: str = Form(""),
        prompt_authority_proof: str = Form(""),
        prompt_cta_transitions: str = Form(""),
        medical_blocklist: str = Form(""),
        medical_deflection: str = Form(""),
        human_takeover_triggers: str = Form(""),
        db: AsyncSession = Depends(get_db),
):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    await set_config(db, "phase1_cta_keywords", phase1_cta_keywords)
    await set_config(db, "phase1_opening_message", phase1_opening_message)
    await set_config(db, "booking_link", booking_link)
    await set_config(db, "score_threshold", score_threshold)
    await set_config(db, "prompt_scoring_rules", prompt_scoring_rules)
    await set_config(db, "prompt_about", prompt_about)
    await set_config(db, "prompt_services", prompt_services)
    await set_config(db, "prompt_tone", prompt_tone)
    await set_config(db, "prompt_flow", prompt_flow)
    await set_config(db, "prompt_hard_rules", prompt_hard_rules)
    await set_config(db, "prompt_opening_variants", prompt_opening_variants)
    await set_config(db, "prompt_qualification_questions", prompt_qualification_questions)
    await set_config(db, "prompt_pattern_responses", prompt_pattern_responses)
    await set_config(db, "prompt_objection_handling", prompt_objection_handling)
    await set_config(db, "prompt_authority_proof", prompt_authority_proof)
    await set_config(db, "prompt_cta_transitions", prompt_cta_transitions)
    await set_config(db, "medical_blocklist", medical_blocklist)
    await set_config(db, "medical_deflection", medical_deflection)
    await set_config(db, "human_takeover_triggers", human_takeover_triggers)

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

    return RedirectResponse(f"/admin/few-shots?scenario={name}&saved=true", status_code=302)


