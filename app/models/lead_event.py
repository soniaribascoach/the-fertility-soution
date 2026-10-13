from sqlalchemy import Column, Integer, String, Boolean, DateTime, func
from app.db.database import Base


class LeadEvent(Base):
    """One state change on a lead that the team, or Sonia, needs to be able to see happened.

    `kind` is handoff, release, release_refused, age_approved or opt_out. `ok` is whether the team
    alert went through, and is only set on a handoff.
    """
    __tablename__ = "lead_events"

    id = Column(Integer, primary_key=True)
    instagram_user_id = Column(String(100), nullable=False)
    kind = Column(String(30), nullable=False)
    reason = Column(String(60), nullable=True)
    ok = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
