from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.lead_event import LeadEvent


async def log_event(
    db: AsyncSession,
    ig_user_id: str,
    kind: str,
    reason: str | None = None,
    ok: bool | None = None,
) -> None:
    db.add(LeadEvent(instagram_user_id=ig_user_id, kind=kind, reason=reason, ok=ok))
    await db.commit()


async def recent_events(db: AsyncSession, limit: int = 50) -> list[LeadEvent]:
    result = await db.execute(select(LeadEvent).order_by(LeadEvent.id.desc()).limit(limit))
    return list(result.scalars().all())
