"""Request IDs are safe, returned to the caller and forwarded to AI scans."""
import json
import logging
import re

import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.services import ai_client
from tests.test_household_inventory import HOME, inventory_api


def _event(caplog, request_id):
    entries = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "mealventory.requests"
    ]
    return next(entry for entry in entries if entry["request_id"] == request_id)


def test_response_header_and_structured_log_never_expose_request_secrets(caplog):
    caplog.set_level(logging.INFO, logger="mealventory.requests")
    with TestClient(app) as client:
        response = client.get(
            "/?password=do-not-log",
            headers={"X-Request-ID": "trace-123", "Authorization": "Bearer secret-token"},
        )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-123"
    event = _event(caplog, "trace-123")
    assert event["service"] == "backend"
    assert event["route"] == "/"
    assert event["status"] == 200
    assert isinstance(event["duration_ms"], float)
    assert event["failure_category"] == "none"
    assert event["user_ref"] is None
    assert "secret-token" not in caplog.text
    assert "do-not-log" not in caplog.text
    assert "Authorization" not in caplog.text


def test_invalid_request_id_is_regenerated_and_errors_are_classified(caplog):
    caplog.set_level(logging.INFO, logger="mealventory.requests")
    with TestClient(app) as client:
        response = client.get("/missing?password=do-not-log", headers={
            "X-Request-ID": "bad\nINJECTED",
        })
    assert response.status_code == 404
    request_id = response.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", request_id)
    event = _event(caplog, request_id)
    assert event["route"] == "<unmatched>"
    assert event["failure_category"] == "client_error"
    assert "INJECTED" not in caplog.text
    assert "do-not-log" not in caplog.text


def test_scan_preview_propagates_one_id_to_ai_and_logs_tenant_safely(
    inventory_api, monkeypatch, caplog
):
    caplog.set_level(logging.INFO, logger="mealventory.requests")
    client, _, _ = inventory_api
    seen = []
    factory = httpx.AsyncClient

    def handler(request):
        seen.append(request.headers.get("x-request-id"))
        return httpx.Response(200, json={"type": "food", "items": ["milk"]})

    monkeypatch.setattr(ai_client, "breaker", ai_client.CircuitBreaker())
    monkeypatch.setattr(
        ai_client.httpx,
        "AsyncClient",
        lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs),
    )
    response = client.post(
        "/api/v1/scan/preview",
        headers={"X-Household-ID": HOME, "X-Request-ID": "scan-789"},
        data={"mode": "food"},
        files={"file": ("private-image.jpg", b"private-image-bytes", "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    assert response.headers["X-Request-ID"] == "scan-789"
    assert seen == ["scan-789"]
    event = _event(caplog, "scan-789")
    assert event["status"] == 200
    assert event["route"] == "/api/v1/scan/preview"
    assert event["household_ref"] is not None
    assert event["user_ref"] is not None
    assert HOME not in caplog.text
    assert "private-image" not in caplog.text
