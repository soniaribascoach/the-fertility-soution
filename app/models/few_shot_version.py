from sqlalchemy import Column, Integer, String, Text, DateTime, func
from app.db.database import Base


class FewShotVersion(Base):
    __tablename__ = "few_shot_versions"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    scenario_name = Column(String(100), nullable=False, index=True)
    content       = Column(Text, nullable=False)
    saved_at      = Column(DateTime(timezone=True), server_default=func.now())
