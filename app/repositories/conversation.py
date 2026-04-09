import json

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.models.conversation import Conversation


async def save_message(
    db: AsyncSession,
    instagram_user_id: str,
    role: str,
    content: str,
    lead_score: int | None = None,
    contact_tags: dict | None = None,
    token_cost: float | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    ai_model: str | None = None,
) -> Conversation:
    obj = Conversation(
        instagram_user_id=instagram_user_id,
        role=role,
        content=content,
        lead_score=lead_score,
        contact_tags=json.dumps(contact_tags) if contact_tags is not None else None,
        token_cost=token_cost,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        ai_model=ai_model,
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


async def get_stats(db: AsyncSession) -> dict:
    """Returns aggregate AI usage stats from assistant messages."""
    result = await db.execute(
        select(
            func.count(Conversation.id).label("total_messages"),
            func.count(func.distinct(Conversation.instagram_user_id)).label("unique_users"),
            func.sum(Conversation.token_cost).label("total_cost_usd"),
            func.sum(Conversation.prompt_tokens).label("total_prompt_tokens"),
            func.sum(Conversation.completion_tokens).label("total_completion_tokens"),
            func.avg(Conversation.token_cost).label("avg_cost_per_message"),
        ).where(Conversation.role == "assistant")
    )
    row = result.one()

    models_result = await db.execute(
        select(func.distinct(Conversation.ai_model))
        .where(Conversation.role == "assistant", Conversation.ai_model.is_not(None))
    )
    models = [m for (m,) in models_result.all() if m]

    return {
        "total_messages": row.total_messages or 0,
        "unique_users": row.unique_users or 0,
        "total_cost_usd": round(row.total_cost_usd or 0.0, 6),
        "total_prompt_tokens": row.total_prompt_tokens or 0,
        "total_completion_tokens": row.total_completion_tokens or 0,
        "total_tokens": (row.total_prompt_tokens or 0) + (row.total_completion_tokens or 0),
        "avg_cost_per_message": round(row.avg_cost_per_message or 0.0, 6),
        "models_used": models,
    }


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


async def has_sent_booking_ask(
    db: AsyncSession,
    instagram_user_id: str,
) -> bool:
    """Returns True if the AI has already asked the buy-in question for this user."""
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.instagram_user_id == instagram_user_id,
            Conversation.role == "assistant",
            Conversation.content.contains("[BOOKING_ASKED]"),
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None
