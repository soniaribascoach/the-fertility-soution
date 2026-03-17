import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from app.models.conversation import Conversation


async def save_message(
    db: AsyncSession,
    instagram_user_id: str,
    role: str,
    content: str,
    lead_score: int | None = None,
    contact_tags: dict | None = None,
) -> Conversation:
    obj = Conversation(
        instagram_user_id=instagram_user_id,
        role=role,
        content=content,
        lead_score=lead_score,
        contact_tags=json.dumps(contact_tags) if contact_tags is not None else None,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


async def get_history(
    db: AsyncSession,
    instagram_user_id: str,
    limit: int = 20,
) -> list[Conversation]:
    """Returns up to `limit` most recent messages, ordered oldest→newest."""
    result = await db.execute(
        select(Conversation)
        .where(Conversation.instagram_user_id == instagram_user_id)
        .order_by(desc(Conversation.created_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return list(reversed(rows))  # oldest first for OpenAI messages array


async def get_latest_score(
    db: AsyncSession,
    instagram_user_id: str,
) -> int:
    """Returns the most recent lead_score for the user, or 0 if none."""
    result = await db.execute(
        select(Conversation.lead_score)
        .where(
            Conversation.instagram_user_id == instagram_user_id,
            Conversation.lead_score.is_not(None),
        )
        .order_by(desc(Conversation.created_at))
        .limit(1)
    )
    score = result.scalar_one_or_none()
    return score if score is not None else 0


async def get_latest_tags(
    db: AsyncSession,
    instagram_user_id: str,
) -> dict:
    """Returns the most recent contact_tags dict for the user, or {} if none."""
    result = await db.execute(
        select(Conversation.contact_tags)
        .where(
            Conversation.instagram_user_id == instagram_user_id,
            Conversation.contact_tags.is_not(None),
        )
        .order_by(desc(Conversation.created_at))
        .limit(1)
    )
    raw = result.scalar_one_or_none()
    if raw is None:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


async def has_received_booking_link(
    db: AsyncSession,
    instagram_user_id: str,
) -> bool:
    """Returns True if any assistant message for this user contains a booking link marker."""
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.instagram_user_id == instagram_user_id,
            Conversation.role == "assistant",
            Conversation.content.contains("[BOOKING_SENT]"),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
