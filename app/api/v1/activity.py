from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_household
from app.dependencies.database import get_db
from app.schemas.activity import ActivityEventOut
from app.services import activity_service


router = APIRouter()


@router.get("", response_model=list[ActivityEventOut])
def list_activity(
    household_id: UUID = Depends(get_current_household),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
):
    """Return newest-first activity only for the selected household."""
    return activity_service.list_events(db, household_id, limit)
