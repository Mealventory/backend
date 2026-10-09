from app.core.config import settings
from app.core.rate_limit import InMemoryRateLimiter, limiter
from app.services import scan_service
from tests.test_supabase_auth import OTHER, UID, claims, headers, token


def test_limiter_blocks_then_resets_after_window():
    clock = {"now": 1000.0}
    buckets = InMemoryRateLimiter()
    assert buckets.hit("join:user:a", 2, 60, now=clock["now"]) is None
    assert buckets.hit("join:user:a", 2, 60, now=clock["now"] + 1) is None
    retry_after = buckets.hit("join:user:a", 2, 60, now=clock["now"] + 2)
    assert retry_after >= 1
    assert buckets.hit("join:user:a", 2, 60, now=clock["now"] + 61) is None


def test_limiter_isolates_keys():
    buckets = InMemoryRateLimiter()
    assert buckets.hit("join:user:a", 1, 60, now=1) is None
    assert buckets.hit("join:user:b", 1, 60, now=1) is None
    assert buckets.hit("scan:user:a", 1, 60, now=1) is None
    assert buckets.hit("join:user:a", 1, 60, now=2) >= 1


def _join(client, user, code="ZZZZZZ"):
    return client.post(
        "/api/v1/households/join",
        headers=headers(token(claims(sub=user))),
        json={"invite_code": code},
    )


def test_invite_guessing_is_throttled_without_leaking_codes(secured_client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_JOIN_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_JOIN_WINDOW_SECONDS", 60.0)

    first = _join(secured_client, OTHER)
    second = _join(secured_client, OTHER)
    blocked = _join(secured_client, OTHER)

    assert first.status_code == 404
    assert second.status_code == 404
    assert first.json()["detail"] == second.json()["detail"] == "Invalid invite code"
    assert blocked.status_code == 429
    assert blocked.headers["content-type"] == "application/problem+json"
    assert blocked.headers["Retry-After"].isdigit()
    assert int(blocked.headers["Retry-After"]) >= 1
    body = blocked.json()
    assert body["status"] == 429
    assert body["title"] == "Too Many Requests"
    assert body["detail"] == "Too many requests. Try again later."
    assert body["code"] == "RATE_LIMITED"
    assert body["action"] == "retry"
    assert "ZZZZZZ" not in blocked.text
    assert "invite" not in body["detail"].lower()
    assert "exist" not in body["detail"].lower()


def test_join_limit_resets_and_is_isolated_per_user(secured_client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_JOIN_ATTEMPTS", 1)
    monkeypatch.setattr(settings, "RATE_LIMIT_JOIN_WINDOW_SECONDS", 30.0)

    assert _join(secured_client, OTHER).status_code == 404
    assert _join(secured_client, OTHER).status_code == 429
    assert _join(secured_client, UID).status_code == 404

    limiter.reset()
    assert _join(secured_client, OTHER).status_code == 404


def test_scan_preview_is_throttled_before_ai(client, monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_SCAN_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "RATE_LIMIT_SCAN_WINDOW_SECONDS", 60.0)
    calls = {"count": 0}

    async def detect(*args):
        calls["count"] += 1
        return {"items": ["yogurt"], "type": "food"}

    monkeypatch.setattr(scan_service, "detect_food", detect)

    def preview():
        return client.post(
            "/api/v1/scan/preview",
            data={"mode": "food"},
            files={"file": ("scan.jpg", b"image-bytes", "image/jpeg")},
        )

    assert preview().status_code == 200
    assert preview().status_code == 200
    blocked = preview()
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"].isdigit()
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert calls["count"] == 2


def test_normal_scan_usage_stays_under_default_limit(client, monkeypatch):
    async def detect(*args):
        return {"items": ["apple"], "type": "food"}

    monkeypatch.setattr(scan_service, "detect_food", detect)
    for _ in range(5):
        response = client.post(
            "/api/v1/scan/preview",
            data={"mode": "food"},
            files={"file": ("scan.jpg", b"image-bytes", "image/jpeg")},
        )
        assert response.status_code == 200, response.text
