from uuid import UUID
from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_household
from app.dependencies.database import get_db
from app.schemas.shopping import ShoppingItemCreate, ShoppingItemUpdate, ShoppingItemOut, ClearCheckedOut
from app.services import shopping_service as service

router = APIRouter(responses={404: {'description': 'Shopping item or food not found'}})


@router.get('', response_model=list[ShoppingItemOut])
def list_items(household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """List unchecked and checked items for any member of the selected household."""
    return service.list_items(db, household_id)


@router.post('', response_model=ShoppingItemOut, status_code=201)
def add_item(item: ShoppingItemCreate, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    return service.add_item(db, household_id, item)


@router.post('/clear-checked', response_model=ClearCheckedOut)
def clear_checked(household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Remove checked items only from the selected household."""
    return service.clear_checked(db, household_id)


@router.patch('/{item_id}', response_model=ShoppingItemOut)
def update_item(item_id: UUID, update: ShoppingItemUpdate,
                household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Set checked explicitly or edit quantity/unit; omitted fields are preserved."""
    return service.update_item(db, household_id, item_id, update)


@router.delete('/{item_id}', status_code=204)
def delete_item(item_id: UUID, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    service.delete_item(db, household_id, item_id)
    return Response(status_code=204)
