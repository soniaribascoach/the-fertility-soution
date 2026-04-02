from sqlalchemy import Column, Integer, String, DateTime, Text, Index, func
from app.db.database import Base


class SimulationSession(Base):
    __tablename__ = "simulation_sessions"

    id            = Column(Integer, primary_key=True)
    session_id    = Column(String(36), unique=True, nullable=False)
    name          = Column(String(200), nullable=True)
    note          = Column(Text, nullable=True)
    first_name    = Column(String(100), nullable=True)
    message_count = Column(Integer, nullable=False, default=0)
    created_at    = Column(DateTime, server_default=func.now())
    updated_at    = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_simulation_sessions_created", "created_at"),
    )
