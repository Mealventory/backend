from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends, Response, Query, Body
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_household
from app.dependencies.database import get_db
from app.schemas.household_inventory import ItemCreate, ItemOut, ItemUpdate, ItemStatus, StorageZone
from app.services import household_inventory_service as service

router = APIRouter(responses={400: {'description': 'Invalid storage zone, household header, or item is not active'}, 404: {'description': 'Item or location not in household'},
                             409: {'description': 'Item is no longer active or has a conflicting final status'}})


@router.get('', response_model=list[ItemOut])
def list_items(household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db),
               status: ItemStatus = 'active', zone: StorageZone | None = None,
               expiring_days: int | None = Query(None, ge=0, le=3650),
               search: str | None = Query(None, max_length=200)):
    """List active items for the selected household, for any household member."""
    return service.list_items(db, household_id, status, zone, expiring_days, search)


@router.post('/batch', response_model=list[ItemOut], status_code=201)
def add_batch(items: Annotated[list[ItemCreate], Body(min_length=1, max_length=100)],
              household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Persist all confirmed items in one transaction, or none on failure."""
    return service.add_batch(db, household_id, items)


@router.patch('/{item_id}', response_model=ItemOut)
def update_item(item_id: UUID, patch: ItemUpdate,
                household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Edit active items atomically, including labels, zone and status. Null clears expiry or location."""
    return service.update_item(db, household_id, item_id, patch)


@router.post('/{item_id}/consume', response_model=ItemOut)
def consume_item(item_id: UUID, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Mark an active item consumed without deleting history. Non-active items return 400."""
    return service.transition_item(db, household_id, item_id, 'consumed')


@router.post('/{item_id}/discard', response_model=ItemOut)
def discard_item(item_id: UUID, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Mark an active item discarded without deleting history. Non-active items return 400."""
    return service.transition_item(db, household_id, item_id, 'discarded')


@router.post('', response_model=ItemOut, status_code=201)
def add_item(item: ItemCreate, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    return service.add_item(db, household_id, item)


@router.delete('/{item_id}', status_code=204)
def delete_item(item_id: UUID, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Delete only from the selected household. Owners and members can delete."""
    service.delete_item(db, household_id, item_id)
    return Response(status_code=204)


from app.schemas.expiry_prediction import ExpiryPredictionInput, ExpiryPredictionOutput
from app.services.household_expiry_service import predict_expiry

@router.post('/predict-expiry', response_model=ExpiryPredictionOutput)
async def predict_item_expiry(request: ExpiryPredictionInput,
                              household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Suggest an expiry date without saving or replacing the item's existing date."""
    return await predict_expiry(db, household_id, request)
