from sqlalchemy import Column, String, Boolean, DateTime
from app.db.database import Base


class UserState(Base):
    __tablename__ = "user_state"

    instagram_user_id = Column(String(100), primary_key=True)
    is_ai_paused = Column(Boolean, nullable=False, default=False)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    pause_reason = Column(String(50), nullable=True)
