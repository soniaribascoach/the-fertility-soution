from sqlalchemy import Column, String, Boolean, DateTime, JSON
from app.db.database import Base


class UserState(Base):
    __tablename__ = "user_state"

    instagram_user_id = Column(String(100), primary_key=True)
    is_ai_paused = Column(Boolean, nullable=False, default=False)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    pause_reason = Column(String(50), nullable=True)

    # Recorded states that a release does not touch (manual v4.1 §R). An opt out is permanent: no
    # admin action or resume webhook clears it. Age approval is written only by the team's
    # explicit approval, never by the handover that asked for it.
    opted_out_at = Column(DateTime(timezone=True), nullable=True)
    age_approved_at = Column(DateTime(timezone=True), nullable=True)

    # Qualification-funnel state (new brain). `phase` is kept top-level for
    # admin visibility/indexing; `qualification` holds {slots, flags, counters}.
    phase = Column(String(40), nullable=True)
    qualification = Column(JSON, nullable=True)
