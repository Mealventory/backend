"""Device registration and protected expiry-notification job trigger."""
import hmac
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.dependencies.database import get_db
from app.schemas.user import UserOut
from app.models.push_token import PushToken
from app.services.notification_service import PushDeliveryError, run_expiry_notification_job

router = APIRouter()


class TokenBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(
        max_length=255,
        pattern=r"^(ExpoPushToken|ExponentPushToken)\[[A-Za-z0-9_-]+\]$",
    )


class Registration(TokenBody):
    platform: Literal["ios", "android"]


class ExpiryNotificationJobReport(BaseModel):
    dry_run: bool
    households_with_expiring: int
    households_targeted: int
    items_expiring: int
    notifications_attempted: int
    accepted: int
    rejected: int
    stale_tokens_removed: int


def require_notification_job_secret(
    x_notification_job_secret: str | None = Header(
        default=None, alias="X-Notification-Job-Secret"
    ),
) -> None:
    configured = settings.NOTIFICATION_JOB_SECRET
    if configured is None or not configured.get_secret_value().strip():
        raise HTTPException(
            status_code=503,
            detail="Notification job trigger is not configured.",
        )
    supplied = x_notification_job_secret or ""
    if not hmac.compare_digest(configured.get_secret_value(), supplied):
        raise HTTPException(status_code=401, detail="Invalid notification job secret.")


@router.put("/device", status_code=204)
def register_device(
    body: Registration,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # A token has one owner. Signing in on the same phone transfers it atomically.
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    stmt = insert(PushToken).values(
        user_id=user.id, token=body.token, platform=body.platform
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["token"],
        set_={"user_id": user.id, "platform": body.platform, "updated_at": func.now()},
    )
    try:
        db.execute(stmt)
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.post("/device/remove", status_code=204)
def remove_device(
    body: TokenBody,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        db.query(PushToken).filter_by(user_id=user.id, token=body.token).delete()
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.post(
    "/jobs/expiry",
    response_model=ExpiryNotificationJobReport,
    dependencies=[Depends(require_notification_job_secret)],
)
def run_expiry_notifications(
    dry_run: bool = Query(
        False,
        description="Build the notification plan without contacting Expo.",
    ),
    db: Session = Depends(get_db),
):
    """Called by an external daily scheduler; do not expose this secret to clients."""
    try:
        return run_expiry_notification_job(db, dry_run=dry_run)
    except PushDeliveryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
