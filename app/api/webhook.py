from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.serializers.webhook import ManychatContactPayload
from app.repositories.event import create_event
from app.repositories.config import get_all_config

router = APIRouter()


@router.post("/contact")
async def manychat_contact(payload: ManychatContactPayload, db: AsyncSession = Depends(get_db)):
    cfg = await get_all_config(db)
    # cfg keys available: booking_link, score_threshold, system_prompt, hard_nos, medical_blocklist

    event = await create_event(db, payload.model_dump())
    ts = event.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
    name = payload.name or f"{payload.first_name or ''} {payload.last_name or ''}".strip() or "Unknown"
    username = f"@{payload.ig_username}" if payload.ig_username else payload.id
    text = payload.last_input_text or ""
    return {"reply": f"{name} ({username}) sent: '{text}' — logged at {ts}"}
