from datetime import date
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.push_token import PushToken
from app.services.notification_service import (
    PushDeliveryResult,
    run_expiry_notification_job,
    send_expo_push,
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
    PushToken.__table__.create(engine)

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
    PushToken.__table__.create(engine)
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
    PushToken.__table__.create(engine)
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
