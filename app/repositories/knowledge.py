"""Knowledge persistence. Retrieval logic itself lives in
`app.services.brain.knowledge` so it stays pure and testable without a database.
"""
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge import Knowledge
from app.services.brain.knowledge import KnowledgeEntry


def _to_entry(row: Knowledge) -> KnowledgeEntry:
    return KnowledgeEntry(
        id=row.id,
        kind=row.kind,
        topic=row.topic,
        content=row.content,
        triggers=[t.strip() for t in (row.triggers or "").splitlines() if t.strip()],
        language=row.language,
        source=row.source or "",
        active=bool(row.active),
    )


async def get_active_knowledge(db: AsyncSession) -> list[KnowledgeEntry]:
    result = await db.execute(sa_select(Knowledge).where(Knowledge.active.is_(True)))
    return [_to_entry(row) for row in result.scalars().all()]


async def all_knowledge(db: AsyncSession) -> list[Knowledge]:
    result = await db.execute(
        sa_select(Knowledge).order_by(Knowledge.kind, Knowledge.topic)
    )
    return list(result.scalars().all())


async def upsert_entry(db: AsyncSession, entry: KnowledgeEntry) -> Knowledge:
    row = None
    if entry.id is not None:
        row = await db.get(Knowledge, entry.id)
    if row is None:
        row = Knowledge(kind=entry.kind, topic=entry.topic)
        db.add(row)
    row.kind = entry.kind
    row.topic = entry.topic
    row.content = entry.content
    row.triggers = "\n".join(entry.triggers)
    row.language = entry.language
    row.source = entry.source
    row.active = entry.active
    await db.commit()
    return row


async def set_active(db: AsyncSession, entry_id: int, active: bool) -> None:
    row = await db.get(Knowledge, entry_id)
    if row is not None:
        row.active = active
        await db.commit()
