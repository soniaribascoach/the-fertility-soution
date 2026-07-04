import hashlib
import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.repositories.conversation import save_message
from app.repositories.pending_message import insert_message, is_duplicate
from app.services.resume import resume_lead
from config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_signature(body: bytes, header: str | None) -> bool:
    if not settings.manychat_webhook_secret:
        logger.warning("MANYCHAT_WEBHOOK_SECRET not set — skipping signature verification")
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        settings.manychat_webhook_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, header)


def _verify_resume_auth(body: bytes, request: Request) -> bool:
    """ManyChat's External Request node can't compute an HMAC, so /webhook/resume
    also accepts the shared secret verbatim in an X-Manychat-Secret header."""
    if _verify_signature(body, request.headers.get("X-Hub-Signature-256")):
        return True
    header_secret = request.headers.get("X-Manychat-Secret") or ""
    return bool(header_secret) and hmac.compare_digest(
        settings.manychat_webhook_secret, header_secret
    )


@router.post("/webhook/resume")
async def resume_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    body = await request.body()
    if not _verify_resume_auth(body, request):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    ig_user_id = str(payload.get("ig_id") or "")
    if not ig_user_id:
        raise HTTPException(status_code=400, detail="Missing ig_id")

    prior_reason = await resume_lead(db, ig_user_id)
    return {"status": "ok", "was_paused": prior_reason is not None}


@router.post("/webhook")
async def receive_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    if not _verify_signature(body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    manychat_contact_id: str = str(payload.get("id", ""))
    ig_user_id: str = str(payload.get("ig_id", ""))
    text: str = (payload.get("last_input_text") or "").strip()

    if not text:
        return {"status": "ok"}

    if await is_duplicate(db, ig_user_id, text, within_seconds=5):
        logger.debug("Duplicate webhook ignored for user %s", ig_user_id)
        return {"status": "ok"}

    await save_message(db, ig_user_id, "user", text)
    await insert_message(db, ig_user_id, manychat_contact_id, text)

    return {"status": "ok"}
