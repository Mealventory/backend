from uuid import UUID
from app.core.dependencies import get_current_household
from app.core.auth_errors import AuthProblem
from typing import Annotated, List, Literal
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session
from app.dependencies.auth import get_current_user
from app.dependencies.database import get_db
from app.schemas.user import UserOut
from app.schemas.inventory import InventoryItemOut
from app.schemas.scan import SampleScanRequest
from app.services import scan_service

router = APIRouter()

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
	current_user: Annotated[UserOut, Depends(get_current_user)],
	household_id: Annotated[UUID, Depends(get_current_household)],
	db: Annotated[Session, Depends(get_db)],
):
    "Upload an image with a selected mode (food, receipt, tag).\nThe ai-service detects food items and they are automatically added\nto the user's inventory."
    return await scan_service.scan_and_add(mode, file, current_user, db)

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
	current_user: Annotated[UserOut, Depends(get_current_user)],
	household_id: Annotated[UUID, Depends(get_current_household)],
	db: Annotated[Session, Depends(get_db)],
):
    'Dev helper: read a .jpg/.jpeg from backend/samples and process it like an uploaded image.'
    if payload.persist_to_db:
        if payload.user_id and payload.user_id != current_user.id:
            raise AuthProblem(403, "Cannot store samples for another user")
        payload = payload.model_copy(update={"user_id": current_user.id})
    return await scan_service.scan_from_sample(payload, db)
