"""Database readiness probe, deliberately independent of user authentication."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.auth_errors import problem_response
from app.dependencies.database import get_db

router = APIRouter()


class HealthOut(BaseModel):
    status: str
    database: str


@router.get(
    "",
    response_model=HealthOut,
    responses={503: problem_response("Database unavailable")},
)
def health(db: Session = Depends(get_db)):
    """Check database connectivity. This does not verify schema or AI readiness."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        # Connection errors can contain credentials and hostnames; never return them.
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "healthy", "database": "available"}
