from datetime import date
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.push_token import PushToken
from app.services.notification_service import (
    PushDeliveryResult,
    run_expiry_notification_job,
    send_expo_push,
    send_low_stock_notification,
)
from tests.test_household_inventory import (
    HOME,
    MEMBER,
    OTHER,
    OUTSIDER,
    OWNER,
    inventory_api,
)


def _add_item(client, household, name, expiry_date, *, identity=None, user=None):
    if identity is not None and user is not None:
        identity["id"] = user
    payload = {"name": name}
    if expiry_date is not None:
        payload["expiry_date"] = expiry_date
    response = client.post(
        "/api/v1/items",
        headers={"X-Household-ID": household},
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_expiry_job_groups_active_items_and_targets_household_members(inventory_api):
    client, identity, engine = inventory_api

    _add_item(client, HOME, "Yogurt", "2026-10-01")
    _add_item(client, HOME, "Milk", "2026-10-02")
    _add_item(client, HOME, "Spinach", "2026-10-03")
    _add_item(client, HOME, "Bread", "2026-10-04")
    _add_item(client, HOME, "Old Lettuce", "2026-09-30")
    _add_item(client, HOME, "Oats", None)
    consumed = _add_item(client, HOME, "Consumed Chicken", "2026-10-02")
    assert client.post(
        f"/api/v1/items/{consumed['id']}/consume",
        headers={"X-Household-ID": HOME},
    ).status_code == 200

    _add_item(
        client,
        OTHER,
        "Other Household Fish",
        "2026-10-02",
        identity=identity,
        user=OUTSIDER,
    )
    identity["id"] = OWNER

    with Session(engine) as db:
        db.add_all(
            [
                PushToken(
                    user_id=OWNER,
                    token="ExpoPushToken[owner-phone]",
                    platform="ios",
                ),
                PushToken(
                    user_id=MEMBER,
                    token="ExpoPushToken[member-phone]",
                    platform="android",
                ),
                PushToken(
                    user_id=OUTSIDER,
                    token="ExpoPushToken[outsider-phone]",
                    platform="ios",
                ),
            ]
        )
        db.commit()

        sent = []

        def sender(messages):
            sent.extend(messages)
            return PushDeliveryResult(accepted=len(messages), rejected=0)

        report = run_expiry_notification_job(
            db,
            as_of=date(2026, 10, 1),
            sender=sender,
        )

    assert report == {
        "dry_run": False,
        "households_with_expiring": 2,
        "households_targeted": 2,
        "items_expiring": 4,
        "notifications_attempted": 3,
        "accepted": 3,
        "rejected": 0,
        "stale_tokens_removed": 0,
    }

    home_messages = [m for m in sent if m["data"]["household_id"] == HOME]
    other_messages = [m for m in sent if m["data"]["household_id"] == OTHER]
    assert {m["to"] for m in home_messages} == {
        "ExpoPushToken[owner-phone]",
        "ExpoPushToken[member-phone]",
    }
    assert {m["to"] for m in other_messages} == {"ExpoPushToken[outsider-phone]"}
    assert all("Yogurt" in m["body"] and "Milk" in m["body"] and "Spinach" in m["body"] for m in home_messages)
    assert all("Bread" not in m["body"] and "Old Lettuce" not in m["body"] and "Consumed Chicken" not in m["body"] for m in home_messages)
    assert all(m["data"]["screen"] == "recipes" for m in sent)


def test_expiry_job_removes_only_tokens_reported_device_not_registered(inventory_api):
    client, _, engine = inventory_api
    _add_item(client, HOME, "Milk", "2026-10-02")

    stale = "ExpoPushToken[stale-phone]"
    good = "ExpoPushToken[good-phone]"
    with Session(engine) as db:
        db.add_all(
            [
                PushToken(user_id=OWNER, token=stale, platform="ios"),
                PushToken(user_id=MEMBER, token=good, platform="android"),
            ]
        )
        db.commit()

        def sender(messages):
            assert {m["to"] for m in messages} == {stale, good}
            return PushDeliveryResult(
                accepted=1,
                rejected=1,
                stale_tokens=(stale,),
            )

        report = run_expiry_notification_job(
            db,
            as_of=date(2026, 10, 1),
            sender=sender,
        )
        assert report["stale_tokens_removed"] == 1
        assert {row.token for row in db.query(PushToken).all()} == {good}


def test_expiry_job_dry_run_never_contacts_expo(inventory_api):
    client, _, engine = inventory_api
    _add_item(client, HOME, "Milk", "2026-10-02")

    with Session(engine) as db:
        db.add(PushToken(user_id=OWNER, token="ExpoPushToken[test-phone]", platform="ios"))
        db.commit()

        def fail_sender(_):
            raise AssertionError("dry run must not contact Expo")

        report = run_expiry_notification_job(
            db,
            as_of=date(2026, 10, 1),
            sender=fail_sender,
            dry_run=True,
        )

    assert report["dry_run"] is True
    assert report["notifications_attempted"] == 1
    assert report["accepted"] == 0


def test_expo_ticket_mapping_marks_device_not_registered():
    messages = [
        {"to": "ExpoPushToken[good]", "body": "Good"},
        {"to": "ExpoPushToken[stale]", "body": "Stale"},
    ]

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": [
                    {"status": "ok", "id": "ticket-1"},
                    {
                        "status": "error",
                        "message": "Device not registered",
                        "details": {"error": "DeviceNotRegistered"},
                    },
                ]
            }

    class Client:
        def post(self, url, headers, json):
            assert url.endswith("/api/v2/push/send")
            assert [message["to"] for message in json] == [
                "ExpoPushToken[good]",
                "ExpoPushToken[stale]",
            ]
            return Response()

    result = send_expo_push(messages, client=Client())
    assert result == PushDeliveryResult(
        accepted=1,
        rejected=1,
        stale_tokens=("ExpoPushToken[stale]",),
    )


def test_job_endpoint_requires_configured_secret_and_supports_dry_run(
    inventory_api, monkeypatch
):
    client, _, _ = inventory_api
    monkeypatch.setattr(settings, "NOTIFICATION_JOB_SECRET", SecretStr("cron-secret"))

    assert client.post(
        "/api/v1/notifications/jobs/expiry?dry_run=true"
    ).status_code == 401
    response = client.post(
        "/api/v1/notifications/jobs/expiry?dry_run=true",
        headers={"X-Notification-Job-Secret": "cron-secret"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["dry_run"] is True

    monkeypatch.setattr(settings, "NOTIFICATION_JOB_SECRET", None)
    assert client.post(
        "/api/v1/notifications/jobs/expiry?dry_run=true",
        headers={"X-Notification-Job-Secret": "cron-secret"},
    ).status_code == 503


def test_low_stock_push_sends_once_until_item_is_restocked(inventory_api):
    client, _, engine = inventory_api
    flour = client.post(
        "/api/v1/items",
        headers={"X-Household-ID": HOME},
        json={"name": "Flour", "quantity": 10, "unit": "kg"},
    ).json()

    with Session(engine) as db:
        db.add_all(
            [
                PushToken(
                    user_id=OWNER,
                    token="ExpoPushToken[owner-low-stock]",
                    platform="ios",
                ),
                PushToken(
                    user_id=MEMBER,
                    token="ExpoPushToken[member-low-stock]",
                    platform="android",
                ),
            ]
        )
        db.execute(
            text(
                "UPDATE inventory_items SET quantity=1 WHERE id=:id"
            ),
            {"id": flour["id"]},
        )
        db.commit()

        sent = []

        def sender(messages):
            sent.extend(messages)
            return PushDeliveryResult(accepted=len(messages), rejected=0)

        first = send_low_stock_notification(
            db, HOME, flour["id"], sender=sender
        )
        assert first["low_stock"] is True
        assert first["notifications_attempted"] == 2
        assert first["accepted"] == 2
        assert len(sent) == 2
        assert all(m["title"] == "Mealventory low-stock alert" for m in sent)
        assert all("Flour is running low" in m["body"] for m in sent)
        assert all(m["data"]["type"] == "low_stock_alert" for m in sent)

        second = send_low_stock_notification(
            db, HOME, flour["id"], sender=sender
        )
        assert second["notifications_attempted"] == 0
        assert len(sent) == 2

        db.execute(
            text(
                "UPDATE inventory_items SET quantity=5 WHERE id=:id"
            ),
            {"id": flour["id"]},
        )
        db.commit()
        reset = send_low_stock_notification(
            db, HOME, flour["id"], sender=sender
        )
        assert reset["low_stock"] is False

        db.execute(
            text(
                "UPDATE inventory_items SET quantity=1 WHERE id=:id"
            ),
            {"id": flour["id"]},
        )
        db.commit()
        third = send_low_stock_notification(
            db, HOME, flour["id"], sender=sender
        )
        assert third["notifications_attempted"] == 2
        assert len(sent) == 4


def test_expiry_job_is_idempotent_per_household_and_calendar_day(inventory_api):
    client, _, engine = inventory_api
    _add_item(client, HOME, "Milk", "2026-10-02")
    token = "ExpoPushToken[idempotent-phone]"

    with Session(engine) as db:
        db.add(PushToken(user_id=OWNER, token=token, platform="ios"))
        db.commit()

        # Dry runs inspect pending work without consuming the day's dispatch slot.
        dry = run_expiry_notification_job(db, as_of=date(2026, 10, 1), dry_run=True)
        assert dry["notifications_attempted"] == 1

        # Transient transport failures roll back cleanly so same-day retries can succeed.
        from app.services.notification_service import PushDeliveryError

        def failing_sender(_messages):
            raise PushDeliveryError("temporary outage")

        try:
            run_expiry_notification_job(
                db,
                as_of=date(2026, 10, 1),
                sender=failing_sender,
            )
            raise AssertionError("expected PushDeliveryError")
        except PushDeliveryError:
            pass

        calls = []

        def sender(messages):
            calls.append(messages)
            return PushDeliveryResult(
                accepted=len(messages),
                rejected=0,
                ticket_ids=("ticket-day1",),
                ticket_tokens={"ticket-day1": token},
                accepted_tokens=(token,),
            )

        first = run_expiry_notification_job(
            db,
            as_of=date(2026, 10, 1),
            sender=sender,
        )
        assert first["accepted"] == 1
        assert len(calls) == 1
        assert calls[0][0]["data"]["route"] == "/(app)/(tabs)/"
        assert calls[0][0]["data"]["screen"] == "recipes"

        second = run_expiry_notification_job(
            db,
            as_of=date(2026, 10, 1),
            sender=sender,
        )
        assert second["households_with_expiring"] == 1
        assert second["households_targeted"] == 0
        assert second["notifications_attempted"] == 0
        assert second["accepted"] == 0
        assert len(calls) == 1

        next_day = run_expiry_notification_job(
            db,
            as_of=date(2026, 10, 2),
            sender=sender,
        )
        assert next_day["households_targeted"] == 1
        assert next_day["accepted"] == 1
        assert len(calls) == 2


def test_send_expo_push_and_fetch_receipts_log_outcomes_without_raw_tokens(caplog):
    import logging
    from app.services.notification_service import (
        EXPO_RECEIPTS_URL,
        ExpoReceiptResult,
        fetch_expo_receipts,
    )

    caplog.set_level(logging.INFO, logger="mealventory.notifications")
    secret_token = "ExpoPushToken[sensitive-device-token]"

    class SendResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"status": "ok", "id": "ticket-ok"}]}

    class SendClient:
        def post(self, url, headers=None, json=None):
            return SendResponse()

    push_result = send_expo_push(
        [{"to": secret_token, "body": "Milk expiring"}],
        client=SendClient(),
    )
    assert push_result.accepted == 1
    assert push_result.ticket_ids == ("ticket-ok",)
    assert push_result.ticket_tokens == {"ticket-ok": secret_token}

    class ReceiptResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "data": {
                    "ticket-ok": {"status": "ok"},
                    "ticket-stale": {
                        "status": "error",
                        "details": {"error": "DeviceNotRegistered"},
                    },
                }
            }

    class ReceiptClient:
        def __init__(self):
            self.calls = []

        def post(self, url, headers=None, json=None):
            self.calls.append((url, json))
            return ReceiptResponse()

    receipt_client = ReceiptClient()
    receipt_result = fetch_expo_receipts(
        ["ticket-ok", "ticket-stale", "ticket-pending"],
        client=receipt_client,
    )
    assert receipt_client.calls == [
        (EXPO_RECEIPTS_URL, {"ids": ["ticket-ok", "ticket-stale", "ticket-pending"]})
    ]
    assert receipt_result == ExpoReceiptResult(
        ok=1,
        errors=1,
        pending=1,
        stale_ticket_ids=("ticket-stale",),
        resolved_ticket_ids=("ticket-ok", "ticket-stale"),
    )
    assert "ticket-ok" in caplog.text
    assert "DeviceNotRegistered" in caplog.text
    assert secret_token not in caplog.text


def test_receipt_check_endpoint_prunes_stale_tokens_and_marks_checked(inventory_api, monkeypatch):
    from app.services import notification_service
    from app.services.notification_service import ExpoReceiptResult, check_pending_expiry_receipts

    client, _, engine = inventory_api
    _add_item(client, HOME, "Milk", "2026-10-02")
    ok_token = "ExpoPushToken[ok-device]"
    dead_token = "ExpoPushToken[dead-device]"

    with Session(engine) as db:
        db.add_all(
            [
                PushToken(user_id=OWNER, token=ok_token, platform="ios"),
                PushToken(user_id=MEMBER, token=dead_token, platform="android"),
            ]
        )
        db.commit()

        def sender(_messages):
            return PushDeliveryResult(
                accepted=2,
                rejected=0,
                ticket_ids=("t-ok", "t-dead"),
                ticket_tokens={"t-ok": ok_token, "t-dead": dead_token},
                accepted_tokens=(ok_token, dead_token),
            )

        run_expiry_notification_job(db, as_of=date(2026, 10, 1), sender=sender)

        # Partial receipt readiness keeps the unresolved ticket pending.
        partial = check_pending_expiry_receipts(
            db,
            fetcher=lambda ids: ExpoReceiptResult(
                ok=1,
                errors=0,
                pending=1,
                resolved_ticket_ids=("t-ok",),
            ),
        )
        assert partial["pending"] == 1
        row = db.execute(
            text(
                """SELECT ticket_tokens_json, receipts_checked_at
                   FROM expiry_notification_dispatches
                   WHERE household_id = :hid"""
            ),
            {"hid": HOME},
        ).mappings().one()
        assert row["receipts_checked_at"] is None
        assert "t-dead" in row["ticket_tokens_json"]
        assert "t-ok" not in row["ticket_tokens_json"]

    monkeypatch.setattr(settings, "NOTIFICATION_JOB_SECRET", SecretStr("cron-secret"))
    monkeypatch.setattr(
        notification_service,
        "fetch_expo_receipts",
        lambda ids: ExpoReceiptResult(
            ok=0,
            errors=1,
            pending=0,
            stale_ticket_ids=("t-dead",),
            resolved_ticket_ids=("t-dead",),
        ),
    )

    assert client.post("/api/v1/notifications/jobs/receipts").status_code == 401
    response = client.post(
        "/api/v1/notifications/jobs/receipts",
        headers={"X-Notification-Job-Secret": "cron-secret"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {
        "dispatches_checked": 1,
        "tickets_checked": 1,
        "ok": 0,
        "errors": 1,
        "pending": 0,
        "stale_tokens_removed": 1,
    }

    with Session(engine) as db:
        assert {row.token for row in db.query(PushToken).all()} == {ok_token}
        checked_at = db.execute(
            text(
                """SELECT receipts_checked_at
                   FROM expiry_notification_dispatches
                   WHERE household_id = :hid"""
            ),
            {"hid": HOME},
        ).scalar_one()
        assert checked_at is not None
        assert check_pending_expiry_receipts(db)["dispatches_checked"] == 0
