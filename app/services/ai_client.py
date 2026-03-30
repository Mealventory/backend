import httpx
from app.core.config import settings


async def detect_food(image_bytes: bytes, mode: str = "food") -> dict:
    """POST an image and mode to the ai-service /scan endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.AI_SERVICE_URL}/scan/",
            data={"mode": mode},
            files={"file": ("image.jpg", image_bytes, "image/jpeg")},
            timeout=30.0,
        )
    response.raise_for_status()
    return response.json()