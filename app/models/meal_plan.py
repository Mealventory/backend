"""Shared household meal slots and per-user import receipts."""
from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, JSON, String, Uuid, func
from app.db.base import Base


class MealPlanSlot(Base):
    __tablename__ = "household_meal_plan_slots"

    household_id = Column(Uuid(as_uuid=False), ForeignKey("households.id", ondelete="CASCADE"), primary_key=True)
    plan_date = Column(Date, primary_key=True)
    slot = Column(String(10), primary_key=True)
    # Tombstones preserve the version after a deletion, preventing stale re-creation.
    recipe_snapshot = Column(JSON, nullable=True)
    revision = Column(Integer, nullable=False, default=1)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class MealPlanImport(Base):
    __tablename__ = "household_meal_plan_imports"

    household_id = Column(Uuid(as_uuid=False), ForeignKey("households.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Uuid(as_uuid=False), primary_key=True)
    import_key = Column(String(64), primary_key=True)
    request_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
