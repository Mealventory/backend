import asyncio
import json

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app.core.auth_errors import (
    COMMON_PROBLEM_STATUS_CODES,
    http_problem_handler,
    validation_problem_handler,
)


def request(path="/example"):
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("testclient", 123),
            "server": ("testserver", 80),
        }
    )


@pytest.mark.parametrize("status_code", COMMON_PROBLEM_STATUS_CODES)
def test_common_http_errors_use_problem_details(status_code):
    response = asyncio.run(
        http_problem_handler(
            request(),
            HTTPException(status_code=status_code, detail="Safe public detail"),
        )
    )
    body = json.loads(response.body)

    assert response.status_code == status_code
    assert response.media_type == "application/problem+json"
    assert body["type"] == "about:blank"
    assert body["status"] == status_code
    assert body["detail"] == "Safe public detail"
    assert body["instance"] == "/example"
    assert isinstance(body["title"], str) and body["title"]


def test_structured_http_detail_keeps_only_safe_extensions():
    response = asyncio.run(
        http_problem_handler(
            request("/api/v1/scan/"),
            HTTPException(
                status_code=503,
                detail={
                    "code": "AI_SERVICE_UNAVAILABLE",
                    "message": "Scanning is temporarily unavailable.",
                    "action": "manual_entry",
                    "debug": "password=do-not-expose host=private",
                },
            ),
        )
    )
    body = json.loads(response.body)

    assert body["detail"] == "Scanning is temporarily unavailable."
    assert body["code"] == "AI_SERVICE_UNAVAILABLE"
    assert body["action"] == "manual_entry"
    assert "debug" not in body
    assert "do-not-expose" not in response.body.decode()


def test_validation_problem_is_actionable_without_echoing_input():
    exc = RequestValidationError(
        [
            {
                "type": "string_too_short",
                "loc": ("body", "password"),
                "msg": "String should have at least 8 characters",
                "input": "supersecret",
                "ctx": {"min_length": 8},
            }
        ]
    )
    response = asyncio.run(validation_problem_handler(request("/example"), exc))
    body = json.loads(response.body)

    assert response.status_code == 422
    assert response.media_type == "application/problem+json"
    assert body["detail"] == "Request validation failed"
    assert body["errors"] == [
        {
            "loc": ["body", "password"],
            "msg": "String should have at least 8 characters",
            "type": "string_too_short",
        }
    ]
    assert "supersecret" not in response.body.decode()
    assert "input" not in response.body.decode()


def test_runtime_validation_and_not_found_are_problem_details(client):
    validation = client.post("/api/v1/items", json={"name": ""})
    assert validation.status_code == 422
    assert validation.headers["content-type"] == "application/problem+json"
    assert validation.json()["detail"] == "Request validation failed"
    assert validation.json()["errors"]

    missing = client.get("/api/v1/definitely-not-a-route")
    assert missing.status_code == 404
    assert missing.headers["content-type"] == "application/problem+json"
    assert missing.json() == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
        "instance": "/api/v1/definitely-not-a-route",
    }
