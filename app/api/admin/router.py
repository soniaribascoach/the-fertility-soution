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
    check_human_takeover_triggers,
    check_medical_blocklist,
    compute_score,
)
from config import settings

router = APIRouter()
templates = Jinja2Templates(directory="templates")

CONFIG_KEYS = [
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
        return RedirectResponse("/admin/config", status_code=302)
    return RedirectResponse("/admin/login", status_code=302)


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
    # Ensure all keys are present
    for key in CONFIG_KEYS:
        cfg.setdefault(key, "")

    def _split(key): return [t for t in cfg.get(key, "").split("\n") if t.strip()]

    blocklist_items             = _split("medical_blocklist")
    takeover_items              = _split("human_takeover_triggers")
    hard_rule_items             = _split("prompt_hard_rules")
    opening_variant_items       = _split("prompt_opening_variants")
    qualification_question_items = _split("prompt_qualification_questions")
    pattern_response_items      = _split("prompt_pattern_responses")
    objection_handling_items    = _split("prompt_objection_handling")
    authority_proof_items       = _split("prompt_authority_proof")
    cta_transition_items        = _split("prompt_cta_transitions")

    return templates.TemplateResponse(
        request,
        "admin/config.html",
        {
            "cfg": cfg,
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


@router.post("/admin/config/save")
async def config_save(
    request: Request,
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


# ── Chat Preview ───────────────────────────────────────────────────────────────

@router.get("/admin/test", response_class=HTMLResponse)
async def test_get(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)
    score = request.session.get("preview_score", 0)
    return templates.TemplateResponse(request, "admin/test.html", {"score": score})


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
        request,
        "admin/chat.html",
        {"cfg": cfg, "score": score, "history": history},
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
    tags = {}

    # Check medical blocklist on incoming message
    if check_medical_blocklist(message, cfg):
        guardrail = "medical"
        history_dicts.append({"role": "user", "content": message})
        request.session["preview_history"] = history_dicts
        return templates.TemplateResponse(
            request,
            "admin/partials/chat_message.html",
            {
                "user_message": message,
                "ai_reply": "",
                "tags": {},
                "score": score,
                "guardrail": guardrail,
                "booking_link_injected": False,
                "booking_url": "",
            },
        )

    # Check human takeover triggers
    if check_human_takeover_triggers(message, cfg):
        guardrail = "takeover"
        history_dicts.append({"role": "user", "content": message})
        request.session["preview_history"] = history_dicts
        return templates.TemplateResponse(
            request,
            "admin/partials/chat_message.html",
            {
                "user_message": message,
                "ai_reply": "",
                "tags": {},
                "score": score,
                "guardrail": guardrail,
                "booking_link_injected": False,
                "booking_url": "",
            },
        )
    else:
        reply, tags, booking_link_injected = await generate_reply(
            message,
            history_objs,
            cfg,
            user_name,
            request.app.state.openai_client,
        )

    if tags:
        score = compute_score(tags)

    # Replicate webhook booking-link logic for the preview
    booking_url = ""
    if not booking_link_injected and not guardrail:
        try:
            threshold = int(cfg.get("score_threshold", "70"))
        except (ValueError, TypeError):
            threshold = 70
        already_sent = request.session.get("preview_booking_sent", False)
        if score >= threshold and not already_sent:
            booking_url = cfg.get("booking_link", "")
            booking_link_injected = True
            request.session["preview_booking_sent"] = True

    # Persist to session
    history_dicts.append({"role": "user", "content": message})
    history_dicts.append({"role": "assistant", "content": reply})
    request.session["preview_history"] = history_dicts
    request.session["preview_score"] = score
    request.session["preview_tags"] = tags

    return templates.TemplateResponse(
        request,
        "admin/partials/chat_message.html",
        {
            "user_message": message,
            "ai_reply": reply,
            "tags": tags,
            "score": score,
            "guardrail": guardrail,
            "booking_link_injected": booking_link_injected,
            "booking_url": booking_url,
        },
    )


@router.post("/admin/chat/reset", response_class=HTMLResponse)
async def chat_reset(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    request.session.pop("preview_history", None)
    request.session.pop("preview_score", None)
    request.session.pop("preview_tags", None)
    request.session.pop("preview_booking_sent", None)

    return HTMLResponse(
        '<span id="score-badge" hx-swap-oob="true">Score: 0</span>',
        status_code=200,
    )
