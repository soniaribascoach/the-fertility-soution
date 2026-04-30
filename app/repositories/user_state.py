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


async def delete_user_state(db: AsyncSession, ig_user_id: str) -> None:
    await db.execute(
        delete(UserState).where(UserState.instagram_user_id == ig_user_id)
    )
    await db.commit()


async def delete_all_user_states(db: AsyncSession) -> None:
    await db.execute(delete(UserState))
    await db.commit()
