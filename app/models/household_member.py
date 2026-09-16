"""Membership mapping for the membership table introduced by init_db.sql.

Presence is active membership: the schema has no separate active/status column.
No runtime table creation or migration is performed here.
"""
from sqlalchemy import Column, String, Uuid
from app.db.base import Base


class HouseholdMember(Base):
    __tablename__ = "household_members"
    household_id = Column(Uuid(as_uuid=False), primary_key=True)
    user_id = Column(Uuid(as_uuid=False), primary_key=True)
    role = Column(String, nullable=False)
