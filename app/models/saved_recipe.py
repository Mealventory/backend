from sqlalchemy import Column, Uuid, String, JSON, DateTime, func
from app.db.base import Base


class SavedRecipe(Base):
    __tablename__ = 'household_saved_recipes'
    household_id = Column(Uuid(as_uuid=False), primary_key=True)
    recipe_key = Column(String(64), primary_key=True)
    snapshot = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
