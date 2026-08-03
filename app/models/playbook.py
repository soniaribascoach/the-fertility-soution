from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Playbook(Base):
    """One conversation pattern, as Part 4 of the Operating Manual defines it.

    Admin-editable, and the intended growth path for the whole system: Sonia
    reviews a real conversation, edits it, and it becomes an example here.

    List-shaped columns are newline-separated Text rather than JSON so they can
    be edited in a plain textarea, matching `knowledge.triggers`. `examples` is
    genuinely nested and stays JSON.
    """
    __tablename__ = "playbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))

    # Retrieval keys.
    mode: Mapped[str] = mapped_column(String(32), default="", index=True)
    intents: Mapped[str] = mapped_column(Text, default="")
    stages: Mapped[str] = mapped_column(Text, default="")
    triggers: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(8), default="en", index=True)

    # Injected into the writer prompt.
    situation: Mapped[str] = mapped_column(Text, default="")
    goal: Mapped[str] = mapped_column(Text, default="")
    emotional_outcome: Mapped[str] = mapped_column(Text, default="")
    communication_priorities: Mapped[str] = mapped_column(Text, default="")
    mistakes_to_avoid: Mapped[str] = mapped_column(Text, default="")
    examples: Mapped[list] = mapped_column(JSON, default=list)

    # Kept for review; never injected, because every prompt token is paid on
    # every turn and these describe the pattern rather than instruct the reply.
    conversation_state: Mapped[str] = mapped_column(Text, default="")
    success_criteria: Mapped[str] = mapped_column(Text, default="")
    information_that_matters: Mapped[str] = mapped_column(Text, default="")
    decision_outcome: Mapped[str] = mapped_column(Text, default="")
    why_this_works: Mapped[str] = mapped_column(Text, default="")

    source: Mapped[str] = mapped_column(String(120), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
