from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_household
from app.dependencies.database import get_db
from app.schemas.household_inventory import ItemCreate, ItemOut
from app.services import household_inventory_service as service

router = APIRouter()


@router.get('', response_model=list[ItemOut])
def list_items(household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """List active items for the selected household, for any household member."""
    return service.list_items(db, household_id)


@router.post('', response_model=ItemOut, status_code=201)
def add_item(item: ItemCreate, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    return service.add_item(db, household_id, item)


@router.delete('/{item_id}', status_code=204)
def delete_item(item_id: UUID, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Delete only from the selected household. Owners and members can delete."""
    service.delete_item(db, household_id, item_id)
    return Response(status_code=204)
