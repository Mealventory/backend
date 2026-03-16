from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.models.inventory import InventoryItem
from app.models.user import User
from app.models.food import Food
from app.schemas.inventory import InventoryItemOut
from app.services.ai_client import detect_food
from app.services.expiry_service import calculate_expiry
from datetime import datetime, timezone

router = APIRouter()


@router.post("/", response_model=List[InventoryItemOut])
async def scan_and_add(
	file: UploadFile = File(...),
	current_user: User = Depends(get_current_user),
	db: Session = Depends(get_db),
):
	"""
	Upload a food image. The ai-service detects food items and they are
	automatically added to the user's inventory.
	"""
	image_bytes = await file.read()
	detection = await detect_food(image_bytes)

	detected_names: List[str] = detection.get("items", [])
	if not detected_names:
		raise HTTPException(status_code=422, detail="No food items detected in image")

	added: List[InventoryItem] = []
	for name in detected_names:
		food = db.query(Food).filter(Food.name.ilike(name)).first()
		if food is None:
			continue
		expiry = None
		if food.avg_shelf_life_days:
			expiry = calculate_expiry(datetime.now(timezone.utc), food.avg_shelf_life_days)
		db_item = InventoryItem(
			user_id=current_user.id,
			food_id=food.id,
			expiry_date=expiry,
		)
		db.add(db_item)
		added.append(db_item)

	db.commit()
	for item in added:
		db.refresh(item)
	return added