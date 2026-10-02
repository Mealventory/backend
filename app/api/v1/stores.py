from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_household
from app.dependencies.database import get_db
from app.schemas.stores import (
    HouseholdStoreCreate,
    HouseholdStoreOut,
    HouseholdStoreReorder,
    HouseholdStoreUpdate,
)
from app.services import store_service as service

router = APIRouter(
    responses={404: {"description": "Store not found in the selected household"}}
)


@router.get("", response_model=list[HouseholdStoreOut])
def list_stores(
    household_id: UUID = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    return service.list_stores(db, household_id)


@router.post("", response_model=HouseholdStoreOut, status_code=201)
def add_store(
    store: HouseholdStoreCreate,
    household_id: UUID = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    return service.add_store(db, household_id, store)


@router.put("/order", response_model=list[HouseholdStoreOut])
def reorder_stores(
    order: HouseholdStoreReorder,
    household_id: UUID = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    return service.reorder_stores(db, household_id, order.store_ids)


@router.patch("/{store_id}", response_model=HouseholdStoreOut)
def update_store(
    store_id: UUID,
    update: HouseholdStoreUpdate,
    household_id: UUID = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    return service.update_store(db, household_id, store_id, update)


@router.delete("/{store_id}", status_code=204)
def delete_store(
    store_id: UUID,
    household_id: UUID = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    service.delete_store(db, household_id, store_id)
    return Response(status_code=204)
