"""In-process sliding-window rate limits. No Redis or other infrastructure."""
from collections import defaultdict, deque
from time import monotonic

from fastapi import Depends, HTTPException

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.schemas.user import UserOut

RATE_LIMIT_DETAIL = {
    "message": "Too many requests. Try again later.",
    "code": "RATE_LIMITED",
    "action": "retry",
}


class InMemoryRateLimiter:
    def __init__(self):
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def reset(self):
        self._hits.clear()

    def hit(self, key: str, limit: int, window_seconds: float, now: float | None = None) -> int | None:
        """Record one attempt. Return Retry-After seconds if blocked, else None."""
        current = monotonic() if now is None else now
        window_start = current - window_seconds
        bucket = self._hits[key]
        while bucket and bucket[0] <= window_start:
            bucket.popleft()
        if len(bucket) >= limit:
            oldest = bucket[0]
            retry_after = max(1, int(window_seconds - (current - oldest) + 0.999))
            return retry_after
        bucket.append(current)
        return None


limiter = InMemoryRateLimiter()


def _identity(scope: str, user_id: str) -> str:
    # Use the verified token subject, not the TCP peer
    # Cloudflare Quick Tunnels make request.client.host the tunnel hop which would throttle every teammate
    return f"{scope}:user:{user_id}"


def enforce(scope: str, user_id: str, limit: int, window_seconds: float) -> None:
    if not settings.RATE_LIMIT_ENABLED:
        return
    retry_after = limiter.hit(_identity(scope, user_id), limit, window_seconds)
    if retry_after is None:
        return
    raise HTTPException(
        status_code=429,
        detail=RATE_LIMIT_DETAIL,
        headers={"Retry-After": str(retry_after)},
    )


def limit_invite_joins(user: UserOut = Depends(get_current_user)) -> UserOut:
    enforce(
        "join",
        user.id,
        settings.RATE_LIMIT_JOIN_ATTEMPTS,
        settings.RATE_LIMIT_JOIN_WINDOW_SECONDS,
    )
    return user


def limit_scans(user: UserOut = Depends(get_current_user)) -> UserOut:
    enforce(
        "scan",
        user.id,
        settings.RATE_LIMIT_SCAN_ATTEMPTS,
        settings.RATE_LIMIT_SCAN_WINDOW_SECONDS,
    )
    return user
