
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
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


@router.get("/analytics")
def get_activity_analytics(
    household_id: UUID = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    """Return consumption and waste counts and daily totals for a household."""

    summary = db.execute(
        text("""
            SELECT
                COUNT(*) FILTER (WHERE action = 'consumed') AS consumed_count,
                COUNT(*) FILTER (WHERE action = 'discarded') AS discarded_count
            FROM household_activity_events
            WHERE household_id = :household_id
              AND entity_type = 'inventory'
        """),
        {"household_id": str(household_id)},
    ).mappings().one()

    daily_rows = db.execute(
        text("""
            SELECT
                CAST(created_at AS DATE) AS day,
                COUNT(*) FILTER (WHERE action = 'consumed') AS consumed,
                COUNT(*) FILTER (WHERE action = 'discarded') AS discarded
            FROM household_activity_events
            WHERE household_id = :household_id
              AND entity_type = 'inventory'
              AND created_at >= CURRENT_DATE - INTERVAL '29 days'
            GROUP BY CAST(created_at AS DATE)
            ORDER BY day
        """),
        {"household_id": str(household_id)},
    ).mappings().all()

    return {
        "consumed_count": int(summary["consumed_count"] or 0),
        "discarded_count": int(summary["discarded_count"] or 0),
        "daily": [
            {
                "date": row["day"].isoformat(),
                "consumed": int(row["consumed"] or 0),
                "discarded": int(row["discarded"] or 0),
            }
            for row in daily_rows
        ],
    }
