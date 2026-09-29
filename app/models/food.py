from sqlalchemy import Column, Integer, String
from app.db.base import Base


class Food(Base):

    __tablename__ = "foods"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    category = Column(String, nullable=True)
    default_unit = Column(String, nullable=True)
    avg_shelf_life_days = Column(Integer, nullable=True)
