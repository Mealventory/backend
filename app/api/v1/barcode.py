"""Authenticated gateway to AI-service barcode resolution."""
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path

from app.core.config import settings
from app.core.rate_limit import limit_scans
from app.core.request_logging import correlation_headers
from app.schemas.user import UserOut

router = APIRouter()


@router.get("/{barcode}")
async def resolve_barcode(
    barcode: str = Path(..., description="UPC-A or EAN-13 barcode"),
    current_user: UserOut = Depends(limit_scans),
):
    """Resolve a barcode without exposing the AI service to the mobile client."""
    del current_user  # Dependency verifies identity and applies the scan rate limit.
    if not re.fullmatch(r"\d{8}|\d{12}|\d{13}", barcode.strip()):
        raise HTTPException(status_code=422, detail="Barcode must contain 8, 12, or 13 digits")

    try:
        async with httpx.AsyncClient(timeout=min(settings.AI_REQUEST_TIMEOUT_SECONDS, 3.0)) as client:
            response = await client.get(
                f"{settings.AI_SERVICE_URL.rstrip('/')}/barcode/{barcode.strip()}",
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
