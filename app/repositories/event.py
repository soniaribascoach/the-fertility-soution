from sqlalchemy.ext.asyncio import AsyncSession
from app.models.event import Event


async def create_event(db: AsyncSession, event_data: dict) -> Event:
    obj = Event(event_data=event_data)
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj
