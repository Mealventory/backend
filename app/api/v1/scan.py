from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, List, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.inventory import InventoryItem
from app.models.food import Food
from app.models.user import User
from app.schemas.inventory import InventoryItemOut
from app.services.expiry_service import calculate_expiry
from app.services.ai_client import detect_food

router = APIRouter()


class SampleScanRequest(BaseModel):
	sample_name: str
	mode: Literal["food", "receipt", "tag", "recipt"] = "food"
	persist_to_db: bool = False
	user_id: str | None = None


def _normalize_mode(mode: str) -> str:
	return "receipt" if mode == "recipt" else mode


def _add_detected_items_for_user(db: Session, user_id: str, detected_names: List[str]) -> List[InventoryItem]:
	added: List[InventoryItem] = []
	for name in detected_names:
		food = db.query(Food).filter(Food.name.ilike(name)).first()
		if food is None:
			continue
		expiry = None
		if food.avg_shelf_life_days:
			expiry = calculate_expiry(datetime.now(timezone.utc), food.avg_shelf_life_days)
		db_item = InventoryItem(
			user_id=user_id,
			food_id=food.id,
			expiry_date=expiry,
		)
		db.add(db_item)
		added.append(db_item)

	db.commit()
	for item in added:
		db.refresh(item)
	return added


@router.post(
    "/",
    response_model=List[InventoryItemOut],
    responses={
        422: {"description": "Image type mismatch or no food items detected"},
    },
)
async def scan_and_add(
	mode: Annotated[Literal["food", "receipt", "tag", "recipt"], Form(...)],
	file: Annotated[UploadFile, File(...)],
	current_user: Annotated[User, Depends(get_current_user)],
	db: Annotated[Session, Depends(get_db)],
):
	"""
	Upload an image with a selected mode (food, receipt, tag).
	The ai-service detects food items and they are automatically added
	to the user's inventory.
	"""
	normalized_mode = _normalize_mode(mode)
	image_bytes = await file.read()
	detection = await detect_food(image_bytes, normalized_mode)

	if detection.get("type") == "mismatch":
		raise HTTPException(
			status_code=422,
			detail=f"Selected mode '{normalized_mode}' does not match image content",
		)

	detected_names: List[str] = detection.get("items", [])
	if not detected_names:
		raise HTTPException(status_code=422, detail="No food items detected in image")

	added = _add_detected_items_for_user(db, current_user.id, detected_names)
	return added


@router.post(
	"/sample",
	responses={
		400: {"description": "Invalid request data"},
		403: {"description": "Sample scan route disabled"},
		404: {"description": "Sample image or user not found"},
		422: {"description": "Image mismatch or no food detected"},
	},
)
async def scan_from_sample(
	payload: SampleScanRequest,
	db: Annotated[Session, Depends(get_db)],
):
	"""Dev helper: read a .jpg/.jpeg from backend/samples and process it like an uploaded image."""
	if not settings.ENABLE_SAMPLE_SCAN:
		raise HTTPException(status_code=403, detail="Sample scan endpoint disabled")

	base_dir = Path(settings.SAMPLE_IMAGES_DIR).resolve()
	file_path = (base_dir / payload.sample_name).resolve()

	if base_dir not in file_path.parents:
		raise HTTPException(status_code=400, detail="Invalid sample file path")

	if file_path.suffix.lower() not in {".jpg", ".jpeg"}:
		raise HTTPException(status_code=400, detail="Sample file must be .jpg or .jpeg")

	if not file_path.exists():
		raise HTTPException(status_code=404, detail=f"Sample not found: {payload.sample_name}")

	image_bytes = file_path.read_bytes()
	normalized_mode = _normalize_mode(payload.mode)
	detection = await detect_food(image_bytes, normalized_mode)

	if detection.get("type") == "mismatch":
		raise HTTPException(
			status_code=422,
			detail=f"Selected mode '{normalized_mode}' does not match image content",
		)

	detected_names: List[str] = detection.get("items", [])
	if not detected_names:
		return {
			"sample": payload.sample_name,
			"mode": normalized_mode,
			"detected": detection,
			"stored_count": 0,
			"stored_items": [],
		}

	if not payload.persist_to_db:
		return {
			"sample": payload.sample_name,
			"mode": normalized_mode,
			"detected": detection,
			"stored_count": 0,
			"stored_items": [],
		}

	if not payload.user_id:
		raise HTTPException(status_code=400, detail="user_id is required when persist_to_db=true")

	user = db.query(User).filter(User.id == payload.user_id).first()
	if user is None:
		raise HTTPException(status_code=404, detail=f"User not found: {payload.user_id}")

	added = _add_detected_items_for_user(db, payload.user_id, detected_names)

	return {
		"sample": payload.sample_name,
		"mode": normalized_mode,
		"detected": detection,
		"stored_count": len(added),
		"stored_items": [InventoryItemOut.model_validate(item).model_dump() for item in added],
	}
