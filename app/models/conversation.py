from sqlalchemy import Column, Integer, String, DateTime, Text, Index, func
from app.db.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    instagram_user_id = Column(String(100), nullable=False)
    content = Column(String, nullable=True)
    role = Column(String(20), nullable=True)  # "user" or "assistant"
    lead_score = Column(Integer, nullable=True)
    contact_tags = Column(Text, nullable=True)  # JSON-encoded dict, e.g. '{"ttc": "ttc_1-2yr", ...}'
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_conversations_user_created", "instagram_user_id", "created_at"),
    )
