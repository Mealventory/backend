"""Expiry push-notification delivery for household inventory.

Scheduling is intentionally external to the FastAPI process. A deployment cron can call
POST /api/v1/notifications/jobs/expiry once per day. This module owns selection,
household targeting, Expo delivery, and stale-token cleanup.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable, Iterable, Sequence

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.household_member import HouseholdMember
from app.models.push_token import PushToken

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_BATCH_SIZE = 100


class PushDeliveryError(RuntimeError):
    """Raised when Expo cannot accept or parse a notification batch."""


@dataclass(frozen=True)
class PushDeliveryResult:
    accepted: int
    rejected: int
    stale_tokens: tuple[str, ...] = ()


def _chunks(values: Sequence[dict], size: int = EXPO_BATCH_SIZE) -> Iterable[Sequence[dict]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _expo_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Content-Type": "application/json",
    }
    token = settings.EXPO_PUSH_ACCESS_TOKEN
    if token:
        value = token.get_secret_value().strip()
        if value:
            headers["Authorization"] = f"Bearer {value}"
    return headers


def send_expo_push(
    messages: Sequence[dict],
    *,
    client: httpx.Client | None = None,
) -> PushDeliveryResult:
    """Send Expo push messages and identify permanently invalid device tokens."""
    if not messages:
        return PushDeliveryResult(accepted=0, rejected=0)

    owns_client = client is None
    transport = client or httpx.Client(timeout=settings.EXPO_PUSH_TIMEOUT_SECONDS)
    accepted = rejected = 0
    stale_tokens: list[str] = []

    try:
        for batch in _chunks(list(messages)):
            try:
                response = transport.post(EXPO_PUSH_URL, headers=_expo_headers(), json=list(batch))
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise PushDeliveryError("Expo push delivery failed. Retry the notification job.") from exc

            tickets = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(tickets, list) or len(tickets) != len(batch):
                raise PushDeliveryError("Expo returned an unexpected push-ticket response.")

            for message, ticket in zip(batch, tickets):
                if not isinstance(ticket, dict):
                    rejected += 1
                    continue
                if ticket.get("status") == "ok":
                    accepted += 1
                    continue

                rejected += 1
                details = ticket.get("details") or {}
                if details.get("error") == "DeviceNotRegistered":
                    token = message.get("to")
                    if isinstance(token, str):
                        stale_tokens.append(token)
    finally:
        if owns_client:
            transport.close()

    return PushDeliveryResult(
        accepted=accepted,
        rejected=rejected,
        stale_tokens=tuple(dict.fromkeys(stale_tokens)),
    )


def _message_body(names: list[str], item_count: int) -> str:
    unique_names = list(dict.fromkeys(names))
    shown = unique_names[:4]
    extra = max(0, len(unique_names) - len(shown))
    listed = ", ".join(shown)
    if extra:
        listed += f" +{extra} more"
    noun = "item is" if item_count == 1 else "items are"
    return f"{item_count} {noun} expiring soon: {listed}. Plan a meal before they go to waste."


def _expiring_by_household(db: Session, as_of: date) -> dict[str, list[str]]:
    cutoff = as_of + timedelta(days=2)
    rows = db.execute(
        text(
            """SELECT i.household_id, f.name
               FROM inventory_items i
               JOIN foods f ON f.id = i.food_id
               WHERE i.status = 'active'
                 AND i.expiry_date IS NOT NULL
                 AND i.expiry_date >= :as_of
                 AND i.expiry_date <= :cutoff
               ORDER BY i.household_id, i.expiry_date, lower(f.name), i.id"""
        ),
        {"as_of": as_of, "cutoff": cutoff},
    ).mappings().all()

    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(str(row["household_id"]), []).append(str(row["name"]))
    return grouped


def _tokens_for_household(db: Session, household_id: str) -> list[str]:
    member_ids = [
        row[0]
        for row in db.query(HouseholdMember.user_id)
        .filter(HouseholdMember.household_id == household_id)
        .all()
    ]
    if not member_ids:
        return []
    return [
        row[0]
        for row in db.query(PushToken.token)
        .filter(PushToken.user_id.in_(member_ids))
        .distinct()
        .all()
    ]


def run_expiry_notification_job(
    db: Session,
    *,
    as_of: date | None = None,
    sender: Callable[[Sequence[dict]], PushDeliveryResult] = send_expo_push,
    dry_run: bool = False,
) -> dict[str, int | bool]:
    """Build and deliver one grouped expiry alert per household/device token."""
    today = as_of or date.today()
    grouped = _expiring_by_household(db, today)

    messages: list[dict] = []
    targeted_households = 0
    total_items = sum(len(names) for names in grouped.values())

    for household_id, names in grouped.items():
        tokens = _tokens_for_household(db, household_id)
        if not tokens:
            continue
        targeted_households += 1
        body = _message_body(names, len(names))
        for token in tokens:
            messages.append(
                {
                    "to": token,
                    "title": "Mealventory expiry alert",
                    "body": body,
                    "sound": "default",
                    "data": {
                        "type": "expiry_alert",
                        "household_id": household_id,
                        "screen": "recipes",
                    },
                }
            )

    if dry_run or not messages:
        return {
            "dry_run": dry_run,
            "households_with_expiring": len(grouped),
            "households_targeted": targeted_households,
            "items_expiring": total_items,
            "notifications_attempted": len(messages),
            "accepted": 0,
            "rejected": 0,
            "stale_tokens_removed": 0,
        }

    result = sender(messages)
    removed = 0
    if result.stale_tokens:
        removed = (
            db.query(PushToken)
            .filter(PushToken.token.in_(result.stale_tokens))
            .delete(synchronize_session=False)
        )
        db.commit()

    return {
        "dry_run": False,
        "households_with_expiring": len(grouped),
        "households_targeted": targeted_households,
        "items_expiring": total_items,
        "notifications_attempted": len(messages),
        "accepted": result.accepted,
        "rejected": result.rejected,
        "stale_tokens_removed": removed,
    }
