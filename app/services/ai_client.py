"""Bounded scan gateway with a per-process circuit breaker."""
import asyncio
import time
from threading import Lock
import httpx
from fastapi import HTTPException
from app.core.config import settings


class AIServiceUnavailable(HTTPException):
    def __init__(self, status_code=503):
        super().__init__(status_code, detail={
            'code': 'AI_SERVICE_UNAVAILABLE',
            'message': 'Scanning is temporarily unavailable. Please enter your items manually or try again shortly.',
            'action': 'manual_entry',
        })


class CircuitBreaker:
    def __init__(self):
        self.lock = Lock()
        self.failures = 0
        self.opened_at = None
        self.probing = False
        self.generation = 0

    def acquire(self):
        with self.lock:
            if self.opened_at is not None:
                if self.probing or time.monotonic() - self.opened_at < settings.AI_CIRCUIT_COOLDOWN_SECONDS:
                    raise AIServiceUnavailable()
                self.probing = True
            return self.generation, self.probing

    def finish(self, ticket, failed):
        generation, probe = ticket
        with self.lock:
            if generation != self.generation:
                return  # An older request must not close a newly opened circuit.
            if probe:
                self.probing = False
                self.generation += 1
                self.opened_at = time.monotonic() if failed else None
                self.failures = 0
            elif failed:
                self.failures += 1
                if self.failures >= settings.AI_CIRCUIT_FAILURE_THRESHOLD:
                    self.opened_at = time.monotonic()
                    self.generation += 1
            else:
                self.failures = 0


breaker = CircuitBreaker()


async def _request(image_bytes, mode):
    async with httpx.AsyncClient(timeout=settings.AI_REQUEST_TIMEOUT_SECONDS) as client:
        for attempt in range(2):
            try:
                response = await client.post(
                    f"{settings.AI_SERVICE_URL.rstrip('/')}/scan/",
                    data={'mode': mode},
                    files={'file': ('image.jpg', image_bytes, 'image/jpeg')},
                )
            except httpx.TimeoutException:
                raise AIServiceUnavailable(504) from None
            except httpx.ConnectError:
                if attempt == 0:
                    await asyncio.sleep(0.2)
                    continue
                raise AIServiceUnavailable() from None
            except httpx.RequestError:
                raise AIServiceUnavailable() from None
            if response.status_code in (502, 503, 504) and attempt == 0:
                await asyncio.sleep(0.2)
                continue
            if response.is_error or response.is_redirect:
                raise AIServiceUnavailable(504 if response.status_code == 504 else 503)
            try:
                result = response.json()
            except ValueError:
                raise AIServiceUnavailable() from None
            if not isinstance(result, dict) or not isinstance(result.get('items'), list) or any(
                not isinstance(item, str) for item in result['items']
            ):
                raise AIServiceUnavailable()
            return result


async def detect_food(image_bytes: bytes, mode: str = 'food') -> dict:
    """Keep the existing multipart contract; retries share one total deadline."""
    ticket = breaker.acquire()
    try:
        async with asyncio.timeout(settings.AI_REQUEST_TIMEOUT_SECONDS):
            result = await _request(image_bytes, mode)
    except TimeoutError:
        breaker.finish(ticket, True)
        raise AIServiceUnavailable(504) from None
    except BaseException:
        # Cancellation must release the half-open probe as well.
        breaker.finish(ticket, True)
        raise
    breaker.finish(ticket, False)
    return result
