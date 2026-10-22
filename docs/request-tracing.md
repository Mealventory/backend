# Request correlation and private structured access logs

The backend assigns a request identifier to each inbound request. If a client
provides a single safe ASCII `X-Request-ID` value (1–64 characters of letters,
digits, underscores or hyphens, starting with a letter/digit), it is retained.
Otherwise a new random 32-character hexadecimal identifier is generated.

The backend returns `X-Request-ID` on handled responses. The CORS configuration
also exposes this header to browsers. For scan-preview, barcode lookup and
expiry prediction, the backend forwards the same header to the AI service. The
AI service returns it on its handled responses and records it in its own logs.

Both services emit compact JSON through the Python loggers
`mealventory.requests` and `mealventory.ai.requests` at INFO level. Ensure
those loggers are enabled in your deployment's logging configuration. Examples:

```json
{"event":"http_request","service":"backend","request_id":"scan-789","method":"POST","route":"/api/v1/scan/preview","status":200,"duration_ms":42.7,"failure_category":"none","user_ref":"f11a3a9a9e9d","household_ref":"81a4f59de1b2"}
{"event":"http_request","service":"ai-services","request_id":"scan-789","method":"POST","route":"/scan/","status":200,"duration_ms":34.5,"failure_category":"none"}
```

The identifiers above are **illustrative**, not captured from production.

Logging intentionally excludes raw paths containing resource IDs, URL query
strings, Authorization or other request headers, email addresses, passwords,
request/response bodies, receipt images, barcode contents, model results, and
upstream exception details. User and household IDs are SHA-256-derived short
pseudonyms, only populated when the backend has validated household access.
Logs must still be protected by normal access controls and retention policies.

For a scan error, ask the user for the `X-Request-ID` response header and
filter both services' logs on `request_id`. A 4xx status is normally a client
or authorization failure; 503/504 is categorized as service unavailable.

Tests: `pytest tests/test_request_logging.py tests/test_ai_client.py`
in the backend, and `pytest tests/test_request_logging.py` in ai-services.
