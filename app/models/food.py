# models/food.py

from sqlalchemy import Column, Integer, String
from app.db.base import Base

class Food(Base):

    __tablename__ = "foods"

    id = Column(Integer, primary_key=True)
    name = Column(String)
    type = Column(String)
    subtype = Column(String)
    avg_shelf_life_days = Column(Integer)