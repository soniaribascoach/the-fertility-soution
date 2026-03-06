from sqlalchemy import Column, Integer, DateTime, JSON
from sqlalchemy.sql import func
from app.db.database import Base


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    event_data = Column(JSON, nullable=False)
