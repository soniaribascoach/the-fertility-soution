from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.serializers.webhook import ManychatContactPayload
from app.repositories.event import create_event
from app.repositories.config import get_all_config
from app.services.webhook import handle_contact
from app.services.manychat import ManyChatService

router = APIRouter()


@router.post("/contact")
async def manychat_contact(
    payload: ManychatContactPayload,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await create_event(db, payload.model_dump())

    cfg = await get_all_config(db)

    openai_client = request.app.state.openai_client
    mc_svc = request.app.state.mc_svc

    user_id = str(payload.ig_id or payload.id)
    user_message = payload.last_input_text or ""
    first_name = payload.first_name

    reply = await handle_contact(
        instagram_user_id=user_id,
        user_message=user_message,
        first_name=first_name,
        db=db,
        cfg=cfg,
        openai_client=openai_client,
        mc_svc=mc_svc,
    )

    return {"status": "ok", "reply": reply}
