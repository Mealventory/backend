"""Database readiness probe, deliberately independent of user authentication."""
from datetime import datetime, timezone
import time
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.auth_errors import problem_response
from app.dependencies.database import get_db
from app.core.config import settings

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


class DatabaseReadiness(BaseModel):
    status: str
    latency_ms: float | None = None
    pool_size: int | None = None
    checked_out: int | None = None


class AIServiceReadiness(BaseModel):
    status: str
    http_status: int | None = None


class ReadinessOut(BaseModel):
    status: str
    components: dict[str, DatabaseReadiness | AIServiceReadiness]
    timestamp: str


def _pool_metrics(db: Session) -> tuple[int | None, int | None]:
    """Retrieve SQLAlchemy pool counters only when the pool exposes them.

    NullPool and some test drivers have no meaningful pool telemetry.
    No connection strings, engine reprs or hostnames are returned.
    """
    try:
        pool = db.get_bind().pool
        size = getattr(pool, "size", None)
        checkedout = getattr(pool, "checkedout", None)
        return (
            int(size()) if callable(size) else None,
            int(checkedout()) if callable(checkedout) else None,
        )
    except Exception:
        return None, None


def _ai_readiness() -> AIServiceReadiness:
    """Bounded readiness probe without exposing the configured upstream URL."""
    try:
        response = httpx.get(
            f"{settings.AI_SERVICE_URL.rstrip('/')}/ready",
            timeout=2.0,
            follow_redirects=False,
        )
        status = response.status_code
        # A bare 200 (e.g., proxy fallback page) is not proof that the
        # scanner's model and OCR configuration are ready.
        payload = response.json() if status in (200, 503) else {}
        reported = payload.get("status") if isinstance(payload, dict) else None
        ready = status == 200 and reported == "ready"
        return AIServiceReadiness(
            status="ready" if ready else (
                reported if status == 503 and reported in ("degraded", "unavailable")
                else "unavailable"
            ),
            http_status=status,
        )
    except (httpx.HTTPError, ValueError, TypeError):
        return AIServiceReadiness(status="unavailable")


@router.get(
    "/ready",
    response_model=ReadinessOut,
    responses={503: {"model": ReadinessOut, "description": "Database or AI service unavailable"}},
)
def ready(db: Session = Depends(get_db)):
    """Deep readiness, separate from the existing cheap database liveness route."""
    pool_size, checked_out = _pool_metrics(db)
    began = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        database = DatabaseReadiness(
            status="healthy",
            latency_ms=round((time.perf_counter() - began) * 1000, 2),
            pool_size=pool_size,
            checked_out=checked_out,
        )
    except Exception:
        # SQLAlchemy errors may contain a full private DSN and credentials.
        database = DatabaseReadiness(
            status="unavailable",
            pool_size=pool_size,
            checked_out=checked_out,
        )
    ai_service = _ai_readiness()
    healthy = database.status == "healthy" and ai_service.status == "ready"
    payload = ReadinessOut(
        status="healthy" if healthy else "degraded",
        components={"database": database, "ai_service": ai_service},
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    if not healthy:
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))
    return payload
