import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_state import (
    get_lead_state,
    get_or_create_state,
    resume_ai,
    save_lead_state,
)
from app.services.brain.constants import resume_lead_state

logger = logging.getLogger(__name__)


async def resume_lead(db: AsyncSession, ig_user_id: str) -> str | None:
    """Re-arm the AI for a lead after a human takeover.

    Clears the pause row AND the terminal control flags in the funnel state
    (handed_off, cost_declined, loop guard, ...) — clearing the pause alone
    leaves the brain silent. Facts and funnel progress are preserved; the AI
    stays quiet until the lead's next DM. Idempotent.

    Returns the pause_reason that was cleared (None if the lead wasn't paused).
    """
    state = await get_or_create_state(db, ig_user_id)
    prior_reason = state.pause_reason if state.is_ai_paused else None

    await resume_ai(db, ig_user_id)
    lead_state = await get_lead_state(db, ig_user_id)
    await save_lead_state(db, ig_user_id, resume_lead_state(lead_state))

    logger.info(
        "AI resumed for user %s (was paused: %s)", ig_user_id, prior_reason or "no"
    )
    return prior_reason
