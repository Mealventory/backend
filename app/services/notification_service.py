"""Expiry push-notification delivery for household inventory.

Scheduling is intentionally external to the FastAPI process. A deployment cron can call
POST /api/v1/notifications/jobs/expiry once per day. This module owns selection,
household targeting, same-calendar-day idempotency, Expo delivery, ticket/receipt
logging, and stale-token cleanup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
from typing import Callable, Iterable, Sequence

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.request_logging import _safe_ref
from app.models.household_member import HouseholdMember
from app.models.push_token import PushToken

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
EXPO_BATCH_SIZE = 100
EXPO_RECEIPT_BATCH_SIZE = 1000

_LOG = logging.getLogger("mealventory.notifications")
_LOG.setLevel(logging.INFO)
if not _LOG.hasHandlers():
    _LOG.addHandler(logging.StreamHandler())


def _log_notification_event(event_name: str, **fields: object) -> None:
    """Emit structured, token-safe JSON logs for push ticket and receipt tracking."""
    payload = {"event": event_name, "service": "backend", **fields}
    _LOG.info(json.dumps(payload, separators=(",", ":"), sort_keys=True))


class PushDeliveryError(RuntimeError):
    """Raised when Expo cannot accept or parse a notification batch."""


@dataclass(frozen=True)
class PushDeliveryResult:
    accepted: int
    rejected: int
    stale_tokens: tuple[str, ...] = ()
    ticket_ids: tuple[str, ...] = field(default=(), compare=False, repr=False)
    ticket_tokens: dict[str, str] = field(default_factory=dict, compare=False, repr=False)
    accepted_tokens: tuple[str, ...] = field(default=(), compare=False, repr=False)


@dataclass(frozen=True)
class ExpoReceiptResult:
    ok: int
    errors: int
    pending: int
    stale_ticket_ids: tuple[str, ...] = ()
    resolved_ticket_ids: tuple[str, ...] = field(default=(), compare=False, repr=False)


def _chunks(values: Sequence, size: int = EXPO_BATCH_SIZE) -> Iterable[Sequence]:
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
    """Send Expo push messages, log ticket outcomes, and identify invalid device tokens."""
    if not messages:
        return PushDeliveryResult(accepted=0, rejected=0)

    owns_client = client is None
    transport = client or httpx.Client(timeout=settings.EXPO_PUSH_TIMEOUT_SECONDS)
    accepted = rejected = 0
    stale_tokens: list[str] = []
    ticket_ids: list[str] = []
    ticket_tokens: dict[str, str] = {}
    accepted_tokens: list[str] = []

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
                token = message.get("to")
                token_ref = _safe_ref(token) if isinstance(token, str) else None
                if not isinstance(ticket, dict):
                    rejected += 1
                    _log_notification_event(
                        "expo_push_ticket",
                        status="error",
                        error="invalid_ticket_payload",
                        token_ref=token_ref,
                    )
                    continue
                ticket_id = ticket.get("id") if isinstance(ticket.get("id"), str) else None
                if ticket.get("status") == "ok":
                    accepted += 1
                    if isinstance(token, str):
                        accepted_tokens.append(token)
                    if ticket_id:
                        ticket_ids.append(ticket_id)
                        if isinstance(token, str):
                            ticket_tokens[ticket_id] = token
                    _log_notification_event(
                        "expo_push_ticket",
                        status="ok",
                        ticket_id=ticket_id,
                        token_ref=token_ref,
                    )
                    continue

                rejected += 1
                details = ticket.get("details") if isinstance(ticket.get("details"), dict) else {}
                error_code = details.get("error")
                _log_notification_event(
                    "expo_push_ticket",
                    status="error",
                    error=error_code,
                    ticket_id=ticket_id,
                    token_ref=token_ref,
                )
                if error_code == "DeviceNotRegistered" and isinstance(token, str):
                    stale_tokens.append(token)
    finally:
        if owns_client:
            transport.close()

    return PushDeliveryResult(
        accepted=accepted,
        rejected=rejected,
        stale_tokens=tuple(dict.fromkeys(stale_tokens)),
        ticket_ids=tuple(dict.fromkeys(ticket_ids)),
        ticket_tokens=ticket_tokens,
        accepted_tokens=tuple(accepted_tokens),
    )


def fetch_expo_receipts(
    ticket_ids: Sequence[str],
    *,
    client: httpx.Client | None = None,
) -> ExpoReceiptResult:
    """Fetch Expo delivery receipts for previously accepted push tickets."""
    unique_ids = list(dict.fromkeys(tid for tid in ticket_ids if isinstance(tid, str) and tid))
    if not unique_ids:
        return ExpoReceiptResult(ok=0, errors=0, pending=0)

    owns_client = client is None
    transport = client or httpx.Client(timeout=settings.EXPO_PUSH_TIMEOUT_SECONDS)
    ok = errors = pending = 0
    stale_ticket_ids: list[str] = []
    resolved_ticket_ids: list[str] = []

    try:
        for batch in _chunks(unique_ids, size=EXPO_RECEIPT_BATCH_SIZE):
            try:
                response = transport.post(
                    EXPO_RECEIPTS_URL,
                    headers=_expo_headers(),
                    json={"ids": list(batch)},
                )
                response.raise_for_status()
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise PushDeliveryError("Expo push receipt check failed. Retry the receipt check.") from exc

            receipts = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(receipts, dict):
                raise PushDeliveryError("Expo returned an unexpected push-receipt response.")

            for ticket_id in batch:
                receipt = receipts.get(ticket_id)
                if receipt is None:
                    pending += 1
                    _log_notification_event("expo_push_receipt", status="pending", ticket_id=ticket_id)
                    continue
                resolved_ticket_ids.append(ticket_id)
                if isinstance(receipt, dict) and receipt.get("status") == "ok":
                    ok += 1
                    _log_notification_event("expo_push_receipt", status="ok", ticket_id=ticket_id)
                    continue

                errors += 1
                details = (
                    receipt.get("details")
                    if isinstance(receipt, dict) and isinstance(receipt.get("details"), dict)
                    else {}
                )
                error_code = details.get("error")
                _log_notification_event(
                    "expo_push_receipt",
                    status="error",
                    error=error_code,
                    ticket_id=ticket_id,
                )
                if error_code == "DeviceNotRegistered":
                    stale_ticket_ids.append(ticket_id)
    finally:
        if owns_client:
            transport.close()

    return ExpoReceiptResult(
        ok=ok,
        errors=errors,
        pending=pending,
        stale_ticket_ids=tuple(dict.fromkeys(stale_ticket_ids)),
        resolved_ticket_ids=tuple(dict.fromkeys(resolved_ticket_ids)),
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


def send_low_stock_notification(
    db: Session,
    household_id: str,
    item_id: str,
    *,
    sender: Callable[[Sequence[dict]], PushDeliveryResult] = send_expo_push,
) -> dict[str, int | bool]:
    """Send one push per household device when an item enters a low-stock episode.

    The alert is best-effort and deduplicated with inventory_items.low_stock_notified_at.
    Restocking above 10% clears that marker so a later low-stock episode can notify again.
    """
    params = {"household_id": str(household_id), "item_id": str(item_id)}
    row = db.execute(
        text(
            """SELECT i.quantity, i.initial_quantity, i.low_stock_notified_at, f.name
               FROM inventory_items i
               JOIN foods f ON f.id = i.food_id
               WHERE i.household_id = :household_id
                 AND i.id = :item_id
                 AND i.status = 'active'"""
        ),
        params,
    ).mappings().first()

    empty = {
        "low_stock": False,
        "notifications_attempted": 0,
        "accepted": 0,
        "rejected": 0,
        "stale_tokens_removed": 0,
    }
    if row is None or row["initial_quantity"] is None:
        return empty

    initial = Decimal(str(row["initial_quantity"]))
    if initial <= 0:
        return empty

    percent = (
        Decimal(str(row["quantity"])) * Decimal("100") / initial
    ).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    low_stock = percent <= Decimal("10")

    if not low_stock:
        if row["low_stock_notified_at"] is not None:
            db.execute(
                text(
                    """UPDATE inventory_items
                       SET low_stock_notified_at = NULL
                       WHERE household_id = :household_id AND id = :item_id"""
                ),
                params,
            )
            db.commit()
        return empty

    if row["low_stock_notified_at"] is not None:
        return {**empty, "low_stock": True}

    tokens = _tokens_for_household(db, str(household_id))
    if not tokens:
        return {**empty, "low_stock": True}

    shown_percent = max(Decimal("0"), percent)
    body = f"{row['name']} is running low — {shown_percent}% remaining."
    messages = [
        {
            "to": token,
            "title": "Mealventory low-stock alert",
            "body": body,
            "sound": "default",
            "data": {
                "type": "low_stock_alert",
                "household_id": str(household_id),
                "item_id": str(item_id),
                "screen": "inventory",
            },
        }
        for token in tokens
    ]

    try:
        active_sender = sender or send_expo_push
        result = active_sender(messages)
    except PushDeliveryError:
        db.rollback()
        return {
            "low_stock": True,
            "notifications_attempted": len(messages),
            "accepted": 0,
            "rejected": len(messages),
            "stale_tokens_removed": 0,
        }

    removed = 0
    if result.stale_tokens:
        removed = (
            db.query(PushToken)
            .filter(PushToken.token.in_(result.stale_tokens))
            .delete(synchronize_session=False)
        )

    if result.accepted > 0:
        db.execute(
            text(
                """UPDATE inventory_items
                   SET low_stock_notified_at = CURRENT_TIMESTAMP
                   WHERE household_id = :household_id AND id = :item_id"""
            ),
            params,
        )

    if removed or result.accepted > 0:
        db.commit()

    return {
        "low_stock": True,
        "notifications_attempted": len(messages),
        "accepted": result.accepted,
        "rejected": result.rejected,
        "stale_tokens_removed": removed,
    }


def _dispatched_households_on(db: Session, dispatched_on: date) -> set[str]:
    rows = db.execute(
        text(
            """SELECT household_id
               FROM expiry_notification_dispatches
               WHERE dispatched_on = :dispatched_on"""
        ),
        {"dispatched_on": dispatched_on},
    ).all()
    return {str(row[0]) for row in rows}


def run_expiry_notification_job(
    db: Session,
    *,
    as_of: date | None = None,
    sender: Callable[[Sequence[dict]], PushDeliveryResult] | None = None,
    dry_run: bool = False,
) -> dict[str, int | bool]:
    """Build and deliver one grouped expiry alert per household/device token."""
    today = as_of or date.today()
    grouped = _expiring_by_household(db, today)
    already_dispatched = _dispatched_households_on(db, today)

    messages: list[dict] = []
    targeted_households = 0
    total_items = sum(len(names) for names in grouped.values())
    household_tokens: dict[str, set[str]] = {}
    household_item_counts: dict[str, int] = {}

    for household_id, names in grouped.items():
        if household_id in already_dispatched:
            continue
        tokens = _tokens_for_household(db, household_id)
        if not tokens:
            continue
        targeted_households += 1
        household_tokens[household_id] = set(tokens)
        household_item_counts[household_id] = len(names)
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
                        "route": "/(app)/(tabs)/",
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

    active_sender = sender or send_expo_push
    result = active_sender(messages)
    removed = 0
    if result.stale_tokens:
        removed = (
            db.query(PushToken)
            .filter(PushToken.token.in_(result.stale_tokens))
            .delete(synchronize_session=False)
        )

    recorded = 0
    if result.accepted > 0:
        stale_set = set(result.stale_tokens)
        dispatched_at = datetime.now(timezone.utc)
        for household_id, tokens_set in household_tokens.items():
            if result.accepted_tokens:
                matched_accepted = sum(
                    1 for token in result.accepted_tokens if token in tokens_set
                )
                if matched_accepted == 0:
                    continue
            else:
                non_stale = tokens_set - stale_set
                if stale_set and not non_stale:
                    continue
                matched_accepted = len(non_stale) if non_stale else result.accepted

            household_tickets = {
                ticket_id: token
                for ticket_id, token in result.ticket_tokens.items()
                if token in tokens_set
            }
            db.execute(
                text(
                    """INSERT INTO expiry_notification_dispatches (
                           household_id,
                           dispatched_on,
                           dispatched_at,
                           item_count,
                           notifications_accepted,
                           ticket_tokens_json
                       )
                       VALUES (
                           :household_id,
                           :dispatched_on,
                           :dispatched_at,
                           :item_count,
                           :notifications_accepted,
                           :ticket_tokens_json
                       )
                       ON CONFLICT (household_id, dispatched_on) DO NOTHING"""
                ),
                {
                    "household_id": household_id,
                    "dispatched_on": today,
                    "dispatched_at": dispatched_at,
                    "item_count": household_item_counts[household_id],
                    "notifications_accepted": matched_accepted,
                    "ticket_tokens_json": (
                        json.dumps(household_tickets, sort_keys=True)
                        if household_tickets
                        else None
                    ),
                },
            )
            recorded += 1

    if removed or recorded:
        db.commit()

    _log_notification_event(
        "expiry_notification_job_completed",
        dispatched_on=today.isoformat(),
        households_with_expiring=len(grouped),
        households_targeted=targeted_households,
        households_recorded=recorded,
        notifications_attempted=len(messages),
        accepted=result.accepted,
        rejected=result.rejected,
        stale_tokens_removed=removed,
        ticket_count=len(result.ticket_ids),
    )

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


def check_pending_expiry_receipts(
    db: Session,
    *,
    fetcher: Callable[[Sequence[str]], ExpoReceiptResult] | None = None,
) -> dict[str, int]:
    """Verify Expo push receipts for logged expiry dispatches and prune invalid tokens."""
    rows = db.execute(
        text(
            """SELECT household_id, dispatched_on, ticket_tokens_json
               FROM expiry_notification_dispatches
               WHERE receipts_checked_at IS NULL
                 AND ticket_tokens_json IS NOT NULL
               ORDER BY dispatched_on, household_id"""
        )
    ).mappings().all()

    pending_rows: list[tuple[str, object, dict[str, str]]] = []
    ticket_to_token: dict[str, str] = {}
    all_ticket_ids: list[str] = []

    for row in rows:
        raw_json = row["ticket_tokens_json"]
        try:
            parsed = json.loads(raw_json) if raw_json else {}
        except (TypeError, ValueError):
            parsed = {}
        if not isinstance(parsed, dict) or not parsed:
            continue
        clean_map = {
            str(ticket_id): str(token)
            for ticket_id, token in parsed.items()
            if isinstance(ticket_id, str)
            and ticket_id
            and isinstance(token, str)
            and token
        }
        if not clean_map:
            continue
        pending_rows.append((str(row["household_id"]), row["dispatched_on"], clean_map))
        for ticket_id, token in clean_map.items():
            ticket_to_token[ticket_id] = token
            all_ticket_ids.append(ticket_id)

    unique_ticket_ids = list(dict.fromkeys(all_ticket_ids))
    if not unique_ticket_ids:
        return {
            "dispatches_checked": 0,
            "tickets_checked": 0,
            "ok": 0,
            "errors": 0,
            "pending": 0,
            "stale_tokens_removed": 0,
        }

    active_fetcher = fetcher or fetch_expo_receipts
    receipt_result = active_fetcher(unique_ticket_ids)
    stale_tokens = tuple(
        dict.fromkeys(
            ticket_to_token[ticket_id]
            for ticket_id in receipt_result.stale_ticket_ids
            if ticket_id in ticket_to_token
        )
    )
    removed = 0
    if stale_tokens:
        removed = (
            db.query(PushToken)
            .filter(PushToken.token.in_(stale_tokens))
            .delete(synchronize_session=False)
        )

    checked_at = datetime.now(timezone.utc)
    resolved_ids = set(receipt_result.resolved_ticket_ids)
    for household_id, dispatched_on, row_tickets in pending_rows:
        if receipt_result.pending == 0 or set(row_tickets).issubset(resolved_ids):
            db.execute(
                text(
                    """UPDATE expiry_notification_dispatches
                       SET receipts_checked_at = :checked_at
                       WHERE household_id = :household_id
                         AND dispatched_on = :dispatched_on"""
                ),
                {
                    "checked_at": checked_at,
                    "household_id": household_id,
                    "dispatched_on": dispatched_on,
                },
            )
        elif resolved_ids:
            remaining = {
                ticket_id: token
                for ticket_id, token in row_tickets.items()
                if ticket_id not in resolved_ids
            }
            db.execute(
                text(
                    """UPDATE expiry_notification_dispatches
                       SET ticket_tokens_json = :ticket_tokens_json
                       WHERE household_id = :household_id
                         AND dispatched_on = :dispatched_on"""
                ),
                {
                    "ticket_tokens_json": json.dumps(remaining, sort_keys=True),
                    "household_id": household_id,
                    "dispatched_on": dispatched_on,
                },
            )

    db.commit()
    _log_notification_event(
        "expiry_receipt_check_completed",
        dispatches_checked=len(pending_rows),
        tickets_checked=len(unique_ticket_ids),
        ok=receipt_result.ok,
        errors=receipt_result.errors,
        pending=receipt_result.pending,
        stale_tokens_removed=removed,
    )
    return {
        "dispatches_checked": len(pending_rows),
        "tickets_checked": len(unique_ticket_ids),
        "ok": receipt_result.ok,
        "errors": receipt_result.errors,
        "pending": receipt_result.pending,
        "stale_tokens_removed": removed,
    }
