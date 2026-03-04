from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_db
from app.serializers.webhook import ManychatPayload

router = APIRouter()


@router.post("/manychat")
async def manychat_webhook(payload: ManychatPayload, db: AsyncSession = Depends(get_db)):
    return {"status": "received", "instagram_user_id": payload.instagram_user_id, "message": payload.message}
