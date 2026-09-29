import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import List
from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.food import Food
from app.models.inventory import InventoryItem
from app.models.user import User
from app.schemas.scan import ManualItemInput, SampleScanRequest
from app.services.expiry_service import calculate_expiry
from app.services.ai_client import detect_food

_CANADIAN_MONTHS = {
	"ja": 1, "fe": 2, "mr": 3, "al": 4, "ma": 5, "jn": 6,
	"jl": 7, "au": 8, "se": 9, "oc": 10, "no": 11, "de": 12,
}
_NAMED_MONTHS = {
	"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
	"july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
	"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6,
	"jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

def parse_detected_expiry_date(raw: str | None) -> datetime | None:
	if not raw:
		return None
	raw = raw.strip()
	try:
		dt = datetime.strptime(raw[:10], "%Y-%m-%d")
		return dt.replace(tzinfo=timezone.utc)
	except ValueError:
		pass
	tokens = re.sub(r"[,.]", "", raw.lower()).split()
	try:
		if len(tokens) == 3 and tokens[1] in _CANADIAN_MONTHS and tokens[0].isdigit():
			year_val, month_val, day_val = tokens[0], _CANADIAN_MONTHS[tokens[1]], int(tokens[2])
			year = int(year_val) + (2000 if len(year_val) == 2 else 0)
			return datetime(year, month_val, day_val, tzinfo=timezone.utc)
		if len(tokens) == 3 and tokens[0] in _NAMED_MONTHS:
			month_val, day_val, year_val = _NAMED_MONTHS[tokens[0]], int(tokens[1]), tokens[2]
			year = int(year_val) + (2000 if len(year_val) == 2 else 0)
			return datetime(year, month_val, day_val, tzinfo=timezone.utc)
	except (ValueError, TypeError):
		pass
	return None

def _normalize_mode(mode: str) -> str:
	return "receipt" if mode == "recipt" else mode

def _normalize_name(name: str) -> str:
	return " ".join(name.lower().split())

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

from uuid import uuid4
from sqlalchemy import text

def _add_detected_items_for_user(
	db: Session,
	user_id: str,
	detected_item_counts: dict[str, int],
	default_expiry: datetime | None = None,
	household_id: str | None = None,
) -> List[InventoryItem]:
	added: List[InventoryItem] = []
	is_postgres = db.get_bind().dialect.name == "postgresql"
	for name, count in detected_item_counts.items():
		food = db.query(Food).filter(Food.name.ilike(name)).first()
		if food is None:
			food = Food(name=name.title(), category="Pantry", default_unit="units")
			db.add(food)
			db.flush()
		for _ in range(count):
			expiry = default_expiry
			if not expiry and food.avg_shelf_life_days:
				expiry = calculate_expiry(datetime.now(timezone.utc), food.avg_shelf_life_days)

			if is_postgres:
				h_id = household_id
				if not h_id:
					try:
						from uuid import UUID as PyUUID
						PyUUID(str(user_id))
						row = db.execute(
							text("SELECT household_id FROM household_members WHERE user_id = :u_id LIMIT 1"),
							{"u_id": str(user_id)},
						).mappings().first()
						if row:
							h_id = str(row["household_id"])
					except (ValueError, TypeError, Exception):
						pass

				if not h_id:
					h_row = db.execute(text("SELECT id FROM households LIMIT 1")).mappings().first()
					h_id = str(h_row["id"]) if h_row else str(uuid4())

				expiry_d = expiry.date() if isinstance(expiry, datetime) else expiry
				item_id = str(uuid4())
				db.execute(
					text(
						"INSERT INTO inventory_items (id, household_id, food_id, quantity, unit, expiry_date, status) "
						"VALUES (:id, :household_id, :food_id, :qty, :unit, :expiry, 'active')"
					),
					{
						"id": item_id,
						"household_id": str(h_id),
						"food_id": str(food.id),
						"qty": 1,
						"unit": "units",
						"expiry": expiry_d,
					},
				)
				db_item = InventoryItem(
					id=item_id,
					user_id=user_id,
					food_id=food.id,
					expiry_date=expiry,
					status="active",
				)
				added.append(db_item)
			else:
				db_item = InventoryItem(
					user_id=user_id,
					food_id=food.id,
					expiry_date=expiry,
				)
				db.add(db_item)
				added.append(db_item)

	db.commit()
	if not is_postgres:
		for item in added:
			db.refresh(item)
	return added

async def scan_and_add(
	mode: str,
	file: UploadFile,
	current_user: User,
	db: Session,
	household_id: str | None = None,
):
    "\n\tUpload an image with a selected mode (food, receipt, tag).\n\tThe ai-service detects food items and they are automatically added\n\tto the user's inventory.\n\t"
    normalized_mode = _normalize_mode(mode)
    image_bytes = await file.read()
    detection = await detect_food(image_bytes, normalized_mode)
    if detection.get('type') == 'mismatch':
        raise HTTPException(status_code=422, detail=f"Selected mode '{normalized_mode}' does not match image content")
    detected_names: List[str] = detection.get('items', [])
    expiry_dates: List[str] = detection.get('expiry_dates', [])
    parsed_expiry = parse_detected_expiry_date(expiry_dates[0]) if expiry_dates else None

    if not detected_names:
        if normalized_mode == 'tag' and parsed_expiry:
            detected_names = ['Tagged Item']
        else:
            raise HTTPException(status_code=422, detail='No food items detected in image')

    return _add_detected_items_for_user(
        db,
        current_user.id,
        _build_quantity_map(detected_names),
        default_expiry=parsed_expiry,
        household_id=household_id,
    )
async def scan_from_sample(payload: SampleScanRequest, db: Session):
    'Dev helper: read a .jpg/.jpeg from backend/samples and process it like an uploaded image.'
    if not settings.ENABLE_SAMPLE_SCAN:
        raise HTTPException(status_code=403, detail='Sample scan endpoint disabled')
    file_path = _resolve_sample_path(payload.sample_name)
    image_bytes = file_path.read_bytes()
    normalized_mode = _normalize_mode(payload.mode)
    detection = await detect_food(image_bytes, normalized_mode)
    if detection.get('type') == 'mismatch':
        raise HTTPException(status_code=422, detail=f"Selected mode '{normalized_mode}' does not match image content")
    detected_names: List[str] = detection.get('items', [])
    if not detected_names and (not payload.manual_items):
        return _build_empty_sample_response(payload.sample_name, normalized_mode, detection)
    detected_item_counts = _build_quantity_map(detected_names)
    may_expire_counts, freezer_only_counts = _split_by_storage_preference(detected_item_counts, payload.freezer_counts)
    manual_item_counts, manual_freezer_counts, detected_item_counts = _apply_manual_items_if_needed(payload, detected_item_counts, may_expire_counts, freezer_only_counts)
    may_expire_items = _expand_counts(may_expire_counts)
    if payload.mode == 'tag' and detection.get('needs_user_input') and (not payload.manual_items):
        return {'sample': payload.sample_name, 'mode': normalized_mode, 'detected': detection, 'stored_count': 0, 'stored_items': [], 'message': 'Tag detected, but food name is unclear. Please provide food name and quantity.', 'manual_item_prompt': 'Provide manual_items as [{name, quantity, freezer_count}] and rescan.'}
    if not payload.persist_to_db:
        return _build_preview_response(payload.sample_name, normalized_mode, detection, detected_item_counts, may_expire_items, may_expire_counts, freezer_only_counts, manual_item_counts, manual_freezer_counts)
    if not payload.user_id:
        raise HTTPException(status_code=400, detail='user_id is required when persist_to_db=true')
    user = db.query(User).filter(User.id == payload.user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail=f'User not found: {payload.user_id}')
    expiry_dates: List[str] = detection.get('expiry_dates', [])
    parsed_expiry = parse_detected_expiry_date(expiry_dates[0]) if expiry_dates else None
    _add_detected_items_for_user(db, payload.user_id, may_expire_counts, default_expiry=parsed_expiry)
    return _build_sample_response(payload, normalized_mode, detection, detected_item_counts, may_expire_counts, freezer_only_counts, manual_item_counts, manual_freezer_counts, may_expire_items)
