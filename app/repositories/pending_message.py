from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, text

from app.models.pending_message import PendingMessage


async def insert_message(
    db: AsyncSession,
    ig_user_id: str,
    manychat_contact_id: str,
    content: str,
) -> PendingMessage:
    row = PendingMessage(
        instagram_user_id=ig_user_id,
        manychat_contact_id=manychat_contact_id,
        content=content,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def is_duplicate(
    db: AsyncSession,
    ig_user_id: str,
    content: str,
    within_seconds: int = 5,
) -> bool:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=within_seconds)
    result = await db.execute(
        select(PendingMessage.id)
        .where(
            PendingMessage.instagram_user_id == ig_user_id,
            PendingMessage.content == content,
            PendingMessage.received_at >= cutoff,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def get_users_ready_to_process(
    db: AsyncSession,
    debounce_seconds: int,
) -> list[str]:
    """Return ig_user_ids whose last message arrived > debounce_seconds ago and have no lock."""
    result = await db.execute(
        select(PendingMessage.instagram_user_id)
        .where(
            PendingMessage.processed_at.is_(None),
            PendingMessage.locked_at.is_(None),
        )
        .group_by(PendingMessage.instagram_user_id)
        .having(
            func.max(PendingMessage.received_at)
            < func.now() - text(f"interval '{debounce_seconds} seconds'")
        )
    )
    return [row[0] for row in result.all()]


async def lock_batch(db: AsyncSession, ig_user_id: str) -> None:
    await db.execute(
        update(PendingMessage)
        .where(
            PendingMessage.instagram_user_id == ig_user_id,
            PendingMessage.processed_at.is_(None),
            PendingMessage.locked_at.is_(None),
        )
        .values(locked_at=func.now())
    )
    await db.commit()


async def get_locked_batch(
    db: AsyncSession,
    ig_user_id: str,
) -> list[PendingMessage]:
    result = await db.execute(
        select(PendingMessage)
        .where(
            PendingMessage.instagram_user_id == ig_user_id,
            PendingMessage.locked_at.is_not(None),
            PendingMessage.processed_at.is_(None),
        )
        .order_by(PendingMessage.received_at.asc())
    )
    return list(result.scalars().all())


async def mark_batch_processed(db: AsyncSession, ig_user_id: str) -> None:
    await db.execute(
        update(PendingMessage)
        .where(
            PendingMessage.instagram_user_id == ig_user_id,
            PendingMessage.processed_at.is_(None),
        )
        .values(processed_at=func.now())
    )
    await db.commit()


async def release_stale_locks(
    db: AsyncSession,
    stale_after_minutes: int = 5,
) -> None:
    await db.execute(
        update(PendingMessage)
        .where(
            PendingMessage.locked_at.is_not(None),
            PendingMessage.processed_at.is_(None),
            PendingMessage.locked_at
            < func.now() - text(f"interval '{stale_after_minutes} minutes'"),
        )
        .values(locked_at=None)
    )
    await db.commit()
