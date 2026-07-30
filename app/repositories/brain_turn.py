"""Brain-turn trace persistence."""
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brain_turn import BrainTurn

logger = logging.getLogger(__name__)


async def save_turn(
    db: AsyncSession,
    ig_user_id: str,
    *,
    brain_version: str,
    result,
    lead_message: str = "",
    shadow: bool = False,
    live_reply: str = "",
) -> None:
    """Record one turn. Never let tracing break a conversation.

    A failure here must not stop a reply going out or a batch being marked
    processed, so everything is caught and logged.
    """
    trace = result.trace or {}
    try:
        db.add(BrainTurn(
            instagram_user_id=ig_user_id,
            brain_version=brain_version,
            shadow=shadow,
            lead_message=(lead_message or "")[:4000],
            intent=trace.get("intent") or "",
            intent_certainty=trace.get("intent_certainty") or "",
            stage=trace.get("stage") or "",
            mode=trace.get("mode") or "",
            reason=(trace.get("reason") or "")[:64],
            action=result.action or "",
            question_asked=trace.get("question_asked") or "",
            reply=result.reply_text or "",
            live_reply=live_reply or "",
            trace=trace,
            violations=list(result.violations or []),
            uncertainty_score=int(trace.get("uncertainty_score") or 0),
            pause=bool(result.pause),
            pause_reason=(result.pause_reason or "")[:48],
            qualified=bool(result.qualified),
            usage=result.usage or {},
            token_cost=float((result.usage or {}).get("token_cost") or 0.0),
        ))
        await db.commit()
    except Exception:
        logger.exception("Failed to record brain turn for %s", ig_user_id)
        await db.rollback()


async def recent_turns(db: AsyncSession, *, shadow: bool = False, limit: int = 50) -> list:
    result = await db.execute(
        select(BrainTurn)
        .where(BrainTurn.shadow.is_(shadow))
        .order_by(BrainTurn.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def mode_counts(db: AsyncSession, *, shadow: bool = False) -> list:
    """How often each response mode fires. The first thing to look at when
    asking whether the router is behaving: a healthy distribution should not be
    almost entirely QUALIFY, which was the whole complaint."""
    result = await db.execute(
        select(BrainTurn.mode, func.count(BrainTurn.id))
        .where(BrainTurn.shadow.is_(shadow))
        .group_by(BrainTurn.mode)
        .order_by(func.count(BrainTurn.id).desc())
    )
    return [(mode or "(none)", count) for mode, count in result.all()]


async def handoff_rate(db: AsyncSession, *, shadow: bool = False) -> tuple:
    """(paused, total). The number to watch when tuning `uncertainty_threshold`."""
    total = await db.scalar(
        select(func.count(BrainTurn.id)).where(BrainTurn.shadow.is_(shadow))
    ) or 0
    paused = await db.scalar(
        select(func.count(BrainTurn.id))
        .where(BrainTurn.shadow.is_(shadow), BrainTurn.pause.is_(True))
    ) or 0
    return paused, total
