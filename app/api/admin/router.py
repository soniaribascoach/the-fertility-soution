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
from config import settings

router = APIRouter()
templates = Jinja2Templates(directory="templates")

CONFIG_KEYS = ["booking_link", "score_threshold", "system_prompt", "hard_nos", "medical_blocklist"]


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
    hard_nos_items = [t for t in cfg.get("hard_nos", "").split("\n") if t.strip()]

    return templates.TemplateResponse(
        "admin/config.html",
        {
            "request": request,
            "cfg": cfg,
            "blocklist_items": blocklist_items,
            "hard_nos_items": hard_nos_items,
            "saved": saved == "true",
        },
    )


@router.post("/admin/config/save")
async def config_save(
    request: Request,
    booking_link: str = Form(""),
    score_threshold: str = Form(""),
    system_prompt: str = Form(""),
    hard_nos: str = Form(""),
    medical_blocklist: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    await set_config(db, "booking_link", booking_link)
    await set_config(db, "score_threshold", score_threshold)
    await set_config(db, "system_prompt", system_prompt)
    await set_config(db, "hard_nos", hard_nos)
    await set_config(db, "medical_blocklist", medical_blocklist)

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


@router.delete("/admin/blocklist/remove")
async def blocklist_remove(request: Request, term: str = Form(...), db: AsyncSession = Depends(get_db)):
    if not is_authenticated(request):
        return RedirectResponse("/admin/login", status_code=302)

    current = await get_config(db, "medical_blocklist") or ""
    items = [t for t in current.split("\n") if t.strip() and t.strip() != term.strip()]
    await set_config(db, "medical_blocklist", "\n".join(items))

    return HTMLResponse("", status_code=200)
