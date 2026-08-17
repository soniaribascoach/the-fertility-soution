from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.db.database import get_db
from config import APP_VERSION, APP_BRAIN, APP_REVISION, APP_STARTED_AT

router = APIRouter()


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    await db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "db": "connected",
        "version": APP_VERSION,
        "brain": APP_BRAIN,
        "revision": APP_REVISION,
        "started_at": APP_STARTED_AT.isoformat(),
    }
