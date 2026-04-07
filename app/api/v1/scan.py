from datetime import datetime, timezone
from collections import Counter
from pathlib import Path
from typing import Annotated, List, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
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

class ManualItemInput(BaseModel):
	name: str
	quantity: int = 1
	freezer_count: int = 0


class SampleScanRequest(BaseModel):
	sample_name: str
	mode: Literal["food", "receipt", "tag", "recipt"] = "food"
	persist_to_db: bool = False
	user_id: str | None = None
	freezer_counts: dict[str, int] = Field(default_factory=dict)
	manual_items: List[ManualItemInput] = Field(default_factory=list)


router = APIRouter()


FREEZER_STORABLE_KEYWORDS = {
	"chicken",
	"beef",
	"fish",
	"meat",
	"seafood",
	"pork",
	"shrimp",
	"salmon",
}


def _normalize_mode(mode: str) -> str:
	return "receipt" if mode == "recipt" else mode


def _normalize_name(name: str) -> str:
	return " ".join(name.lower().split())


def _is_freezer_candidate(name: str) -> bool:
	normalized = _normalize_name(name)
	return any(keyword in normalized for keyword in FREEZER_STORABLE_KEYWORDS)


def _build_quantity_map(detected_names: List[str]) -> dict[str, int]:
	return dict(Counter(detected_names))


def _normalize_manual_items(manual_items: List[ManualItemInput]) -> tuple[dict[str, int], dict[str, int]]:
	counts: dict[str, int] = {}
	freezer_counts: dict[str, int] = {}

	for item in manual_items:
		normalized_name = _normalize_name(item.name)
		quantity = max(0, int(item.quantity))
		freezer_count = max(0, min(quantity, int(item.freezer_count)))
		if quantity:
			counts[normalized_name] = counts.get(normalized_name, 0) + quantity
		if freezer_count:
			freezer_counts[normalized_name] = freezer_counts.get(normalized_name, 0) + freezer_count

	return counts, freezer_counts


def _split_by_storage_preference(item_counts: dict[str, int], freezer_counts: dict[str, int]) -> tuple[dict[str, int], dict[str, int]]:
	may_expire_counts: dict[str, int] = {}
	freezer_only_counts: dict[str, int] = {}

	for name, total_count in item_counts.items():
		requested_freezer = max(0, int(freezer_counts.get(name, 0)))
		freezer_count = min(total_count, requested_freezer)
		may_expire_count = total_count - freezer_count

		if may_expire_count:
			may_expire_counts[name] = may_expire_count
		if freezer_count:
			freezer_only_counts[name] = freezer_count

	return may_expire_counts, freezer_only_counts


def _expand_counts(item_counts: dict[str, int]) -> List[str]:
	expanded: List[str] = []
	for name, count in item_counts.items():
		expanded.extend([name] * count)
	return expanded


def _resolve_sample_path(sample_name: str) -> Path:
	base_dir = Path(settings.SAMPLE_IMAGES_DIR).resolve()
	file_path = (base_dir / sample_name).resolve()

	if base_dir not in file_path.parents:
		raise HTTPException(status_code=400, detail="Invalid sample file path")

	if file_path.suffix.lower() not in {".jpg", ".jpeg"}:
		raise HTTPException(status_code=400, detail="Sample file must be .jpg or .jpeg")

	if not file_path.exists():
		raise HTTPException(status_code=404, detail=f"Sample not found: {sample_name}")

	return file_path


def _build_empty_sample_response(sample_name: str, mode: str, detection: dict) -> dict:
	return {
		"sample": sample_name,
		"mode": mode,
		"detected": detection,
		"stored_count": 0,
		"stored_items": [],
		"detected_item_counts": {},
		"may_expire_items": [],
		"may_expire_item_counts": {},
		"ignored_freezer_items": [],
		"ignored_freezer_item_counts": {},
		"manual_item_counts": {},
		"manual_freezer_item_counts": {},
	}


def _build_preview_response(
	sample_name: str,
	mode: str,
	detection: dict,
	detected_item_counts: dict[str, int],
	may_expire_items: List[str],
	may_expire_counts: dict[str, int],
	freezer_only_counts: dict[str, int],
	manual_item_counts: dict[str, int],
	manual_freezer_counts: dict[str, int],
) -> dict:
	return {
		"sample": sample_name,
		"mode": mode,
		"detected": detection,
		"stored_count": 0,
		"stored_items": [],
		"may_expire_items": may_expire_items,
		"may_expire_item_counts": may_expire_counts,
		"detected_item_counts": detected_item_counts,
		"ignored_freezer_items": _expand_counts(freezer_only_counts),
		"ignored_freezer_item_counts": freezer_only_counts,
		"manual_item_counts": manual_item_counts,
		"manual_freezer_item_counts": manual_freezer_counts,
		"storage_prompt": "For freezer-eligible items, send freezer_counts with the quantity to store in the freezer. Example: {'chicken': 2}.",
	}


def _apply_manual_items_if_needed(
	payload: SampleScanRequest,
	detected_item_counts: dict[str, int],
	may_expire_counts: dict[str, int],
	freezer_only_counts: dict[str, int],
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
	manual_item_counts: dict[str, int] = {}
	manual_freezer_counts: dict[str, int] = {}
	if payload.mode == "tag" and payload.manual_items:
		manual_item_counts, manual_freezer_counts = _normalize_manual_items(payload.manual_items)
		for name, count in manual_item_counts.items():
			if count:
				may_expire_counts[name] = may_expire_counts.get(name, 0) + count
		for name, count in manual_freezer_counts.items():
			if count:
				freezer_only_counts[name] = freezer_only_counts.get(name, 0) + count
		for name, count in manual_item_counts.items():
			detected_item_counts[name] = detected_item_counts.get(name, 0) + count
	return manual_item_counts, manual_freezer_counts, detected_item_counts


def _build_sample_response(
	payload: SampleScanRequest,
	mode: str,
	detection: dict,
	detected_item_counts: dict[str, int],
	may_expire_counts: dict[str, int],
	freezer_only_counts: dict[str, int],
	manual_item_counts: dict[str, int],
	manual_freezer_counts: dict[str, int],
	may_expire_items: List[str],
) -> dict:
	return {
		"sample": payload.sample_name,
		"mode": mode,
		"detected": detection,
		"stored_count": 0,
		"stored_items": [],
		"may_expire_items": may_expire_items,
		"may_expire_item_counts": may_expire_counts,
		"detected_item_counts": detected_item_counts,
		"ignored_freezer_items": _expand_counts(freezer_only_counts),
		"ignored_freezer_item_counts": freezer_only_counts,
		"manual_item_counts": manual_item_counts,
		"manual_freezer_item_counts": manual_freezer_counts,
	}


def _add_detected_items_for_user(db: Session, user_id: str, detected_item_counts: dict[str, int]) -> List[InventoryItem]:
	added: List[InventoryItem] = []
	for name, count in detected_item_counts.items():
		food = db.query(Food).filter(Food.name.ilike(name)).first()
		if food is None:
			continue
		for _ in range(count):
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

	return _add_detected_items_for_user(db, current_user.id, detected_names)


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

	file_path = _resolve_sample_path(payload.sample_name)

	image_bytes = file_path.read_bytes()
	normalized_mode = _normalize_mode(payload.mode)
	detection = await detect_food(image_bytes, normalized_mode)

	if detection.get("type") == "mismatch":
		raise HTTPException(
			status_code=422,
			detail=f"Selected mode '{normalized_mode}' does not match image content",
		)

	detected_names: List[str] = detection.get("items", [])
	if not detected_names and not payload.manual_items:
		return _build_empty_sample_response(payload.sample_name, normalized_mode, detection)

	detected_item_counts = _build_quantity_map(detected_names)
	may_expire_counts, freezer_only_counts = _split_by_storage_preference(
		detected_item_counts,
		payload.freezer_counts,
	)
	manual_item_counts, manual_freezer_counts, detected_item_counts = _apply_manual_items_if_needed(
		payload,
		detected_item_counts,
		may_expire_counts,
		freezer_only_counts,
	)
	may_expire_items = _expand_counts(may_expire_counts)

	if payload.mode == "tag" and detection.get("needs_user_input") and not payload.manual_items:
		return {
			"sample": payload.sample_name,
			"mode": normalized_mode,
			"detected": detection,
			"stored_count": 0,
			"stored_items": [],
			"message": "Tag detected, but food name is unclear. Please provide food name and quantity.",
			"manual_item_prompt": "Provide manual_items as [{name, quantity, freezer_count}] and rescan.",
		}

	if not payload.persist_to_db:
		return _build_preview_response(
			payload.sample_name,
			normalized_mode,
			detection,
			detected_item_counts,
			may_expire_items,
			may_expire_counts,
			freezer_only_counts,
			manual_item_counts,
			manual_freezer_counts,
		)

	if not payload.user_id:
		raise HTTPException(status_code=400, detail="user_id is required when persist_to_db=true")

	user = db.query(User).filter(User.id == payload.user_id).first()
	if user is None:
		raise HTTPException(status_code=404, detail=f"User not found: {payload.user_id}")

	_add_detected_items_for_user(db, payload.user_id, may_expire_counts)

	return _build_sample_response(
		payload,
		normalized_mode,
		detection,
		detected_item_counts,
		may_expire_counts,
		freezer_only_counts,
		manual_item_counts,
		manual_freezer_counts,
		may_expire_items,
	)
