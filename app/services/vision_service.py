from app.services.ai_client import detect_food


async def recognize_food(image_bytes: bytes) -> dict:
    """Delegate food recognition to the ai-service via ai_client."""
    return await detect_food(image_bytes)