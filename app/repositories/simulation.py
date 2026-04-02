from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, update
from app.models.simulation import SimulationSession


async def get_or_create_session(
    db: AsyncSession,
    session_id: str,
) -> SimulationSession:
    result = await db.execute(
        select(SimulationSession).where(SimulationSession.session_id == session_id)
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        obj = SimulationSession(session_id=session_id)
        db.add(obj)
        await db.commit()
        await db.refresh(obj)
    return obj


async def update_session_meta(
    db: AsyncSession,
    session_id: str,
    name: str | None,
    note: str | None,
    first_name: str | None,
) -> SimulationSession | None:
    result = await db.execute(
        select(SimulationSession).where(SimulationSession.session_id == session_id)
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        return None
    obj.name = name
    obj.note = note
    obj.first_name = first_name
    await db.commit()
    await db.refresh(obj)
    return obj


async def increment_message_count(
    db: AsyncSession,
    session_id: str,
) -> None:
    await db.execute(
        update(SimulationSession)
        .where(SimulationSession.session_id == session_id)
        .values(message_count=SimulationSession.message_count + 1)
    )
    await db.commit()


async def get_all_sessions(
    db: AsyncSession,
) -> list[SimulationSession]:
    result = await db.execute(
        select(SimulationSession)
        .where(SimulationSession.message_count > 0)
        .order_by(desc(SimulationSession.created_at))
    )
    return list(result.scalars().all())


async def get_session(
    db: AsyncSession,
    session_id: str,
) -> SimulationSession | None:
    result = await db.execute(
        select(SimulationSession).where(SimulationSession.session_id == session_id)
    )
    return result.scalar_one_or_none()


async def delete_session(
    db: AsyncSession,
    session_id: str,
) -> bool:
    result = await db.execute(
        select(SimulationSession).where(SimulationSession.session_id == session_id)
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        return False
    await db.delete(obj)
    await db.commit()
    return True
