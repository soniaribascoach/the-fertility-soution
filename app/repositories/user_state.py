from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.user_state import UserState


async def get_or_create_state(db: AsyncSession, ig_user_id: str) -> UserState:
    result = await db.execute(
        select(UserState).where(UserState.instagram_user_id == ig_user_id)
    )
    state = result.scalar_one_or_none()
    if state is None:
        state = UserState(instagram_user_id=ig_user_id, is_ai_paused=False)
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state


async def is_ai_paused(db: AsyncSession, ig_user_id: str) -> bool:
    state = await get_or_create_state(db, ig_user_id)
    return state.is_ai_paused


async def pause_ai(db: AsyncSession, ig_user_id: str, reason: str) -> None:
    state = await get_or_create_state(db, ig_user_id)
    state.is_ai_paused = True
    state.paused_at = datetime.now(timezone.utc)
    state.pause_reason = reason
    await db.commit()


async def resume_ai(db: AsyncSession, ig_user_id: str) -> None:
    state = await get_or_create_state(db, ig_user_id)
    state.is_ai_paused = False
    state.paused_at = None
    state.pause_reason = None
    await db.commit()


async def opt_out(db: AsyncSession, ig_user_id: str) -> bool:
    """Record the opt out. Returns False if she had already opted out."""
    state = await get_or_create_state(db, ig_user_id)
    if state.opted_out_at:
        return False
    state.opted_out_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def approve_age(db: AsyncSession, ig_user_id: str) -> bool:
    """Record the team's booking approval for a lead at or over the age threshold."""
    state = await get_or_create_state(db, ig_user_id)
    if state.age_approved_at:
        return False
    state.age_approved_at = datetime.now(timezone.utc)
    await db.commit()
    return True


async def get_lead_state(db: AsyncSession, ig_user_id: str) -> dict:
    """Return the qualification-funnel state for a lead as a plain dict.

    Shape: {"phase": str | None, "slots": dict, "flags": dict, "counters": dict, "told": list}.
    New/unseen leads come back with phase=None and empty sub-dicts, the brain
    treats that as the OPENING phase.

    `age_approved` is read from its column on every turn rather than stored in the JSON, so the
    team's approval is the only thing that can set it.
    """
    state = await get_or_create_state(db, ig_user_id)
    qual = state.qualification or {}
    flags = dict(qual.get("flags", {}))
    flags.pop("age_approved", None)
    if state.age_approved_at:
        flags["age_approved"] = True
    return {
        "phase": state.phase,
        "slots": qual.get("slots", {}),
        "flags": flags,
        "counters": qual.get("counters", {}),
        "told": qual.get("told", []),
    }


async def save_lead_state(db: AsyncSession, ig_user_id: str, lead_state: dict) -> None:
    """Persist the qualification-funnel state for a lead.

    Always assigns a fresh dict to the JSON column so SQLAlchemy detects the
    change (no in-place mutation tracking needed).
    """
    state = await get_or_create_state(db, ig_user_id)
    state.phase = lead_state.get("phase")
    flags = {k: v for k, v in (lead_state.get("flags") or {}).items() if k != "age_approved"}
    state.qualification = {
        "slots": lead_state.get("slots", {}),
        "flags": flags,
        "counters": lead_state.get("counters", {}),
        "told": lead_state.get("told", []),
    }
    await db.commit()


async def delete_user_state(db: AsyncSession, ig_user_id: str) -> None:
    await db.execute(
        delete(UserState).where(UserState.instagram_user_id == ig_user_id)
    )
    await db.commit()


async def delete_all_user_states(db: AsyncSession) -> None:
    await db.execute(delete(UserState))
    await db.commit()
