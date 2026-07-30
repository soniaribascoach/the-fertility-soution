from sqlalchemy import JSON, Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class BrainTurn(Base):
    """One row per brain turn: what it decided, why, and what it cost.

    Before this table, `TurnResult.action` and `.violations` were computed and
    thrown away and the two LLM calls of a turn were blended into a single cost
    figure, so "why did the bot say that" could not be answered from the
    database. Reviewing tone or calibrating the uncertainty threshold was
    guesswork.

    Shadow rows (`shadow=True`) were generated but never sent: the routed brain
    run against live traffic alongside whichever brain actually replied, with
    that reply kept in `live_reply` so one row is a complete comparison.
    """
    __tablename__ = "brain_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instagram_user_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    brain_version: Mapped[str] = mapped_column(String(16))
    shadow: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    # What the lead said, so a row reads on its own without joining conversations.
    lead_message: Mapped[str] = mapped_column(Text, default="")

    # The routing decision.
    intent: Mapped[str] = mapped_column(String(48), default="", index=True)
    intent_certainty: Mapped[str] = mapped_column(String(16), default="")
    stage: Mapped[str] = mapped_column(String(16), default="")
    mode: Mapped[str] = mapped_column(String(24), default="", index=True)
    reason: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(48), default="")
    question_asked: Mapped[str] = mapped_column(Text, default="")

    # What was said, and what was suppressed.
    reply: Mapped[str] = mapped_column(Text, default="")
    live_reply: Mapped[str] = mapped_column(Text, default="")  # shadow rows only

    # Why. `trace` holds the full structure; the columns above are the ones
    # worth filtering and sorting on.
    trace: Mapped[dict] = mapped_column(JSON, default=dict)
    violations: Mapped[dict] = mapped_column(JSON, default=list)
    uncertainty_score: Mapped[int] = mapped_column(Integer, default=0, index=True)

    pause: Mapped[bool] = mapped_column(Boolean, default=False)
    pause_reason: Mapped[str] = mapped_column(String(48), default="")
    qualified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Per-call usage, so the classifier, writer and checker stay separable.
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    token_cost: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (
        Index("ix_brain_turns_shadow_created", "shadow", "created_at"),
    )
