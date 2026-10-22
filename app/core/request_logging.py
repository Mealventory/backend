"""Privacy-safe request correlation and structured HTTP access logs.

Only route templates and hashed authenticated identifiers are logged. Never log
headers, query strings, credentials, request bodies, or raw image contents.
"""
from contextvars import ContextVar
import hashlib
import json
import logging
import re
import time
from uuid import uuid4

from fastapi import Request

_REQUEST_ID = ContextVar("mealventory_request_id", default=None)
_LOG = logging.getLogger("mealventory.requests")
_LOG.setLevel(logging.INFO)
# Ensure INFO events reach the process logs even if the root logger is unconfigured.
if not _LOG.hasHandlers():
    _LOG.addHandler(logging.StreamHandler())
_ALLOWED_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")


def correlation_headers() -> dict[str, str]:
    """Headers to pass to internal AI requests made during the current request."""
    request_id = _REQUEST_ID.get()
    return {"X-Request-ID": request_id} if request_id else {}


def _safe_ref(value) -> str | None:
    # Non-reversible, short identifiers support debugging without exposing UUIDs.
    if value is None:
        return None
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def _failure_category(status: int) -> str:
    if status < 400:
        return "none"
    if status == 429:
        return "rate_limited"
    if status in (401, 403):
        return "authorization"
    if status in (502, 503, 504):
        return "service_unavailable"
    return "server_error" if status >= 500 else "client_error"


async def request_logging_middleware(request: Request, call_next):
    incoming_id = request.headers.get("X-Request-ID", "")
    request_id = incoming_id if _ALLOWED_ID.fullmatch(incoming_id) else uuid4().hex
    token = _REQUEST_ID.set(request_id)
    start = time.monotonic()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        route = request.scope.get("route")
        # A route template, not the raw path (which could contain a barcode).
        route_template = getattr(route, "path", None) or "<unmatched>"
        event = {
            "event": "http_request",
            "service": "backend",
            "request_id": request_id,
            "method": request.method,
            "route": route_template,
            "status": status,
            "duration_ms": elapsed_ms,
            "failure_category": _failure_category(status),
            "user_ref": _safe_ref(getattr(request.state, "user_id", None)),
            "household_ref": _safe_ref(getattr(request.state, "household_id", None)),
        }
        _LOG.info(json.dumps(event, separators=(",", ":"), sort_keys=True))
        _REQUEST_ID.reset(token)
