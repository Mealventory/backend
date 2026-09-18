"""Database readiness probe, deliberately independent of user authentication."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.dependencies.database import get_db

router = APIRouter()


class HealthOut(BaseModel):
    status: str
    database: str


@router.get('', response_model=HealthOut, responses={503: {'model': HealthOut, 'description': 'Database unavailable'}})
def health(db: Session = Depends(get_db)):
    """Check database connectivity. This does not verify schema or AI readiness."""
    try:
        db.execute(text('SELECT 1'))
    except SQLAlchemyError:
        # Connection errors can contain credentials and hostnames; never return them.
        return JSONResponse(status_code=503, content={'status': 'unhealthy', 'database': 'unavailable'})
    return {'status': 'healthy', 'database': 'available'}
