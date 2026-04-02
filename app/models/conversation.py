from sqlalchemy import Column, Integer, String, DateTime, Text, Float, Index, func
from app.db.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    instagram_user_id = Column(String(100), nullable=False)
    content = Column(String, nullable=True)
    role = Column(String(20), nullable=True)  # "user" or "assistant"
    lead_score = Column(Integer, nullable=True)
    contact_tags = Column(Text, nullable=True)  # JSON-encoded dict, e.g. '{"ttc": "ttc_1-2yr", ...}'
    token_cost        = Column(Float, nullable=True)        # USD cost of the OpenAI call
    prompt_tokens     = Column(Integer, nullable=True)      # input token count
    completion_tokens = Column(Integer, nullable=True)      # output token count
    ai_model          = Column(String(50), nullable=True)   # model used, e.g. "gpt-4.1-mini"
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_conversations_user_created", "instagram_user_id", "created_at"),
    )
