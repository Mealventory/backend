"""Household-scoped activity events for shared kitchen changes."""
import re
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import text

from app.schemas.user import UserOut


COLUMNS = (
    "id, household_id, actor_user_id, actor_name, action, "
    "entity_type, entity_id, item_name, created_at"
)


def actor_label(user: UserOut) -> str:
    if user.email:
        local = user.email.split("@", 1)[0]
        cleaned = re.sub(r"[._-]+", " ", local).strip()
        if cleaned:
            return cleaned.title()[:120]
    return "Household member"


def record_event(
    db,
    household_id,
    actor: UserOut | None,
    action: str,
    item_name: str,
    *,
    entity_type: str = "inventory",
    entity_id=None,
):
    if actor is None:
        return None
    row = db.execute(
        text(
            f"""INSERT INTO household_activity_events
            (id, household_id, actor_user_id, actor_name, action, entity_type, entity_id, item_name, created_at)
            VALUES (:id, :household_id, :actor_user_id, :actor_name, :action, :entity_type, :entity_id, :item_name, :created_at)
            RETURNING {COLUMNS}"""
        ),
        {
            "id": str(uuid4()),
            "household_id": str(household_id),
            "actor_user_id": actor.id,
            "actor_name": actor_label(actor),
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "item_name": item_name,
            "created_at": datetime.now(timezone.utc),
        },
    ).mappings().one()
    return dict(row)


def list_events(db, household_id, limit: int = 50):
    return db.execute(
        text(
            f"""SELECT {COLUMNS}
            FROM household_activity_events
            WHERE household_id=:household_id
            ORDER BY created_at DESC, id DESC
            LIMIT :limit"""
        ),
        {"household_id": str(household_id), "limit": limit},
    ).mappings().all()
