import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_state import get_or_create_state, resume_ai

logger = logging.getLogger(__name__)


async def resume_lead(db: AsyncSession, ig_user_id: str) -> str | None:
    """Re-arm the AI for a lead after a human takeover. Idempotent.

    Returns the pause_reason that was cleared (None if she wasn't paused).

    The v14 brain also had to clear terminal flags inside `lead_state` here,
    because clearing the pause alone left it silent. Whether the new brain needs
    the same depends on how it stores state, so that step is deliberately absent
    rather than guessed at.
    """
    state = await get_or_create_state(db, ig_user_id)
    prior_reason = state.pause_reason if state.is_ai_paused else None

    await resume_ai(db, ig_user_id)

    logger.info(
        "AI resumed for user %s (was paused: %s)", ig_user_id, prior_reason or "no"
    )
    return prior_reason
