import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.lead_event import log_event
from app.repositories.user_state import approve_age, get_or_create_state, resume_ai

logger = logging.getLogger(__name__)

# What `resume_lead` reports back, so the webhook and the admin page can say what happened.
RESUMED = "resumed"
OPTED_OUT = "opted_out"


async def resume_lead(db: AsyncSession, ig_user_id: str) -> str:
    """Re-arm the AI for a lead after a human takeover. Idempotent.

    A lead who opted out is never resumed, from admin or from the ManyChat webhook (manual v4.1
    §R: a release must not clear an opt out). The refusal is logged so it shows on the dashboard.

    A release is only a release. It does not approve a booking at 48 or over; that is
    `approve_lead_age`, a separate action.
    """
    state = await get_or_create_state(db, ig_user_id)
    if state.opted_out_at:
        logger.info("Refusing to resume %s: opted out", ig_user_id)
        await log_event(db, ig_user_id, "release_refused", reason="opted_out")
        return OPTED_OUT

    prior_reason = state.pause_reason if state.is_ai_paused else None
    await resume_ai(db, ig_user_id)
    await log_event(db, ig_user_id, "release", reason=prior_reason)
    logger.info("AI resumed for user %s (was paused: %s)", ig_user_id, prior_reason or "no")
    return RESUMED


async def approve_lead_age(db: AsyncSession, ig_user_id: str) -> None:
    """Record the team's booking approval for a lead at or over the age threshold (v4.1 §R)."""
    if await approve_age(db, ig_user_id):
        await log_event(db, ig_user_id, "age_approved")
        logger.info("Age booking approval recorded for %s", ig_user_id)
