from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.config import AppConfig


async def get_config(db: AsyncSession, key: str) -> str | None:
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    row = result.scalar_one_or_none()
    return row.value if row else None


async def set_config(db: AsyncSession, key: str, value: str) -> AppConfig:
    result = await db.execute(select(AppConfig).where(AppConfig.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        row = AppConfig(key=key, value=value)
        db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def get_all_config(db: AsyncSession) -> dict:
    result = await db.execute(select(AppConfig))
    rows = result.scalars().all()
    return {row.key: row.value for row in rows}
