from sqlalchemy import Column, Integer, String, Text, DateTime, Index
from sqlalchemy.sql import func
from app.db.database import Base


class PendingMessage(Base):
    __tablename__ = "pending_messages"

    id = Column(Integer, primary_key=True)
    instagram_user_id = Column(String(100), nullable=False)
    manychat_contact_id = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    received_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_pending_messages_user_processed_received",
              "instagram_user_id", "processed_at", "received_at"),
    )
