"""Playbook persistence. Retrieval logic itself lives in
`app.services.brain.playbooks`, which stays pure so it can be tested without a
database."""
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook import Playbook as PlaybookRow
from app.services.brain.playbooks import Playbook


def _lines(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _to_playbook(row: PlaybookRow) -> Playbook:
    return Playbook(
        id=row.id,
        slug=row.slug,
        title=row.title,
        mode=row.mode or None,
        intents=_lines(row.intents),
        stages=_lines(row.stages),
        triggers=_lines(row.triggers),
        language=row.language,
        situation=row.situation,
        goal=row.goal,
        emotional_outcome=row.emotional_outcome,
        communication_priorities=_lines(row.communication_priorities),
        mistakes_to_avoid=_lines(row.mistakes_to_avoid),
        examples=row.examples or [],
        conversation_state=row.conversation_state,
        success_criteria=row.success_criteria,
        information_that_matters=row.information_that_matters,
        decision_outcome=row.decision_outcome,
        why_this_works=row.why_this_works,
        source=row.source,
        active=row.active,
    )


async def get_active_playbooks(db: AsyncSession) -> list[Playbook]:
    result = await db.execute(sa_select(PlaybookRow).where(PlaybookRow.active.is_(True)))
    return [_to_playbook(row) for row in result.scalars().all()]


def next_examples(existing: list, lead: str, sonia: str):
    """The examples list after adding this exchange, or None if it is unusable.

    Pure, so the rule that matters - never replace what she already has, never
    store a half-empty exchange - is testable without a database.
    """
    lead, sonia = (lead or "").strip(), (sonia or "").strip()
    if not lead or not sonia:
        return None
    return list(existing or []) + [{"turns": [{"lead": lead, "sonia": sonia}]}]


async def append_example(db: AsyncSession, slug: str, lead: str, sonia: str) -> bool:
    """Add one reviewed exchange to a playbook's examples.

    This is Sonia's stated iteration loop, closed: she reads a real turn, edits
    the reply if it needs it, and the next matching conversation learns from it.
    Before this, growing the library meant a developer editing a seed file.

    The JSON column is reassigned rather than mutated in place, or SQLAlchemy
    does not notice the change and the write is silently lost.
    """
    result = await db.execute(sa_select(PlaybookRow).where(PlaybookRow.slug == slug))
    row = result.scalar_one_or_none()
    if row is None:
        return False
    updated = next_examples(row.examples, lead, sonia)
    if updated is None:
        return False

    row.examples = updated
    # An entry with a reviewed example is no longer an unreviewed draft.
    if row.source.startswith("DRAFT"):
        row.source = "reviewed in /admin/shadow"
    await db.commit()
    return True


async def all_playbooks(db: AsyncSession) -> list[PlaybookRow]:
    result = await db.execute(sa_select(PlaybookRow).order_by(PlaybookRow.mode, PlaybookRow.slug))
    return list(result.scalars().all())
