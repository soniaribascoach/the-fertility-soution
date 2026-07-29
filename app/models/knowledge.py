from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Knowledge(Base):
    """Approved substance the writer is allowed to use.

    Admin-editable: adding a reframe here is how Sonia teaches the bot something
    new, and the writer may not state a fertility or positioning claim that is
    not retrieved from this table.
    """
    __tablename__ = "knowledge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    topic: Mapped[str] = mapped_column(String(80), index=True)
    content: Mapped[str] = mapped_column(Text)
    # Newline-separated regexes or plain keywords matched against her message.
    triggers: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(8), default="en", index=True)
    source: Mapped[str] = mapped_column(String(120), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped["DateTime"] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
