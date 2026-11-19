"""Authenticated gateway to AI-service barcode resolution."""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Path

from app.core.config import settings
from app.core.rate_limit import limit_scans
from app.core.request_logging import correlation_headers
from app.schemas.user import UserOut

router = APIRouter()
SUPPORTED_BARCODE_LENGTHS = (8, 12, 13)


def _normalize_and_validate_barcode(barcode: str) -> str:
    normalized = (barcode or "").strip()
    if len(normalized) not in SUPPORTED_BARCODE_LENGTHS or not normalized.isascii() or not normalized.isdigit():
        raise ValueError("Barcode must contain 8, 12, or 13 digits")

    weighted_sum = sum(
        int(digit) * (3 if offset % 2 == 0 else 1)
        for offset, digit in enumerate(reversed(normalized[:-1]))
    )
    if int(normalized[-1]) != (10 - weighted_sum % 10) % 10:
        raise ValueError("Barcode has an invalid check digit")
    return normalized


@router.get("/{barcode}")
async def resolve_barcode(
    barcode: str = Path(..., description="GTIN-8, UPC-A/GTIN-12, or EAN-13 barcode with a valid check digit"),
    current_user: UserOut = Depends(limit_scans),
):
    """Resolve a barcode without exposing the AI service to the mobile client."""
    del current_user  # Dependency verifies identity and applies the scan rate limit.
    try:
        normalized_barcode = _normalize_and_validate_barcode(barcode)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        async with httpx.AsyncClient(timeout=min(settings.AI_REQUEST_TIMEOUT_SECONDS, 3.0)) as client:
            response = await client.get(
                f"{settings.AI_SERVICE_URL.rstrip('/')}/barcode/{normalized_barcode}",
                headers=correlation_headers(),
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(
            status_code=503,
            detail="Barcode lookup is temporarily unavailable. You can enter the item manually.",
        ) from None

    if not isinstance(result, dict):
        raise HTTPException(status_code=503, detail="Barcode lookup returned an invalid response")
    return result
