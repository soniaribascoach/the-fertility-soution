from sqlalchemy import Column, Integer, String, DateTime, func
from app.db.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True)
    instagram_user_id = Column(String(100), nullable=False)
    message = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
