from types import SimpleNamespace

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.repositories.config import get_all_config, set_config, get_config
from app.api.admin.auth import (
    is_authenticated,
    check_rate_limit,
    record_failed_attempt,
    reset_attempts,
)
from app.services.ai import (
    generate_reply,
    check_medical_blocklist,
    MEDICAL_DEFLECTION,
)
from config import settings

router = APIRouter()
templates = Jinja2Templates(directory="templates")

CONFIG_KEYS = ["booking_link", "score_threshold", "prompt_about", "prompt_services",
               "prompt_tone", "medical_blocklist", "medical_deflection"]


@router.get("/admin")
async def admin_root(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/admin/config", status_code=302)
    return RedirectResponse("/admin/login", status_code=302)


@router.get("/admin/login", response_class=HTMLResponse)
async def login_get(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": None})


@router.post("/admin/login", response_class=HTMLResponse)
async def login_post(request: Request, password: str = Form(...)):
    if not check_rate_limit(request):
        return templates.TemplateResponse(
            "admin/login.html",
            {"request": request, "error": "Too many failed attempts. Try again in 15 minutes."},
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
        "admin/login.html",
        {"request": request, "error": error},
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
    # Ensure all keys are present
    for key in CONFIG_KEYS:
        cfg.setdefault(key, "")

    blocklist_items = [t for t in cfg.get("medical_blocklist", "").split("\n") if t.strip()]

    return templates.TemplateResponse(
        "admin/config.html",
        {
            "request": request,
            "cfg": cfg,
            "blocklist_items": blocklist_items,
            "saved": saved == "true",
        },
    )


@router.post("/admin/config/save")
async def config_save(
    request: Request,
    booking_link: str = Form(""),
    score_threshold: str = Form(""),
    prompt_about: str = Form(""),
    prompt_services: str = Form(""),
    prompt_tone: str = Form(""),
    medical_blocklist: str = Form(""),
    medical_deflection: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    await set_config(db, "booking_link", booking_link)
    await set_config(db, "score_threshold", score_threshold)
    await set_config(db, "prompt_about", prompt_about)
    await set_config(db, "prompt_services", prompt_services)
    await set_config(db, "prompt_tone", prompt_tone)
    await set_config(db, "medical_blocklist", medical_blocklist)
    await set_config(db, "medical_deflection", medical_deflection)

    return RedirectResponse("/admin/config?saved=true", status_code=302)


@router.post("/admin/blocklist/add", response_class=HTMLResponse)
async def blocklist_add(request: Request, term: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    current = await get_config(db, "medical_blocklist") or ""
    items = [t for t in current.split("\n") if t.strip()]
    term = term.strip()
    if term and term not in items:
        items.append(term)
    await set_config(db, "medical_blocklist", "\n".join(items))

    return templates.TemplateResponse(
        "admin/partials/blocklist_item.html",
        {"request": request, "term": term},
    )


@router.post("/admin/blocklist/remove")
async def blocklist_remove(request: Request, term: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    current = await get_config(db, "medical_blocklist") or ""
    items = [t for t in current.split("\n") if t.strip() and t.strip() != term.strip()]
    await set_config(db, "medical_blocklist", "\n".join(items))

    return HTMLResponse("", status_code=200)


# ── Chat Preview ───────────────────────────────────────────────────────────────

@router.get("/admin/test", response_class=HTMLResponse)
async def test_get(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    score = request.session.get("preview_score", 50)
    return templates.TemplateResponse("admin/test.html", {"request": request, "score": score})


@router.get("/admin/chat", response_class=HTMLResponse)
async def chat_get(request: Request, db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    cfg = await get_all_config(db)
    for key in CONFIG_KEYS:
        cfg.setdefault(key, "")

    score = request.session.get("preview_score", 50)
    history = request.session.get("preview_history", [])

    return templates.TemplateResponse(
        "admin/chat.html",
        {"request": request, "cfg": cfg, "score": score, "history": history},
    )


@router.post("/admin/chat/send", response_class=HTMLResponse)
async def chat_send(
    request: Request,
    message: str = Form(...),
    user_name: str = Form("Test User"),
    db: AsyncSession = Depends(get_db),
):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    cfg = await get_all_config(db)
    for key in CONFIG_KEYS:
        cfg.setdefault(key, "")

    history_dicts = request.session.get("preview_history", [])
    score = request.session.get("preview_score", 50)

    # Wrap history dicts as objects with .role / .content for generate_reply
    history_objs = [SimpleNamespace(**h) for h in history_dicts]

    guardrail = None

    # Check medical blocklist on incoming message
    if check_medical_blocklist(message, cfg):
        reply = cfg.get("medical_deflection") or MEDICAL_DEFLECTION
        delta = 0
        guardrail = "medical"
        booking_link_injected = False
    else:
        reply, delta, booking_link_injected = await generate_reply(
            message,
            history_objs,
            cfg,
            user_name,
            request.app.state.openai_client,
        )

    score = max(0, min(100, score + delta))

    # Persist to session
    history_dicts.append({"role": "user", "content": message})
    history_dicts.append({"role": "assistant", "content": reply})
    request.session["preview_history"] = history_dicts
    request.session["preview_score"] = score

    return templates.TemplateResponse(
        "admin/partials/chat_message.html",
        {
            "request": request,
            "user_message": message,
            "ai_reply": reply,
            "delta": delta,
            "score": score,
            "guardrail": guardrail,
            "booking_link_injected": booking_link_injected,
        },
    )


@router.post("/admin/chat/reset", response_class=HTMLResponse)
async def chat_reset(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    request.session.pop("preview_history", None)
    request.session.pop("preview_score", None)

    return HTMLResponse(
        '<span id="score-badge" hx-swap-oob="true">Score: 50</span>',
        status_code=200,
    )
