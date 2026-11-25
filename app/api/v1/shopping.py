from uuid import UUID
from fastapi import APIRouter, Body, Depends, Response
from sqlalchemy.orm import Session
from app.core.auth_errors import problem_response
from app.core.dependencies import get_current_household, get_current_user
from app.dependencies.database import get_db
from app.schemas.shopping import (
    ClearCheckedOut,
    EndShoppingTripOut,
    EndShoppingTripRequest,
    ShoppingClaimRequest,
    ShoppingHandoffRequest,
    ShoppingItemCreate,
    ShoppingItemOut,
    ShoppingItemUpdate,
)
from app.schemas.user import UserOut
from app.services import shopping_service as service

router = APIRouter(
    responses={404: problem_response("Shopping item or food not found")}
)


@router.get('', response_model=list[ShoppingItemOut])
def list_items(household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """List unchecked and checked items for any member of the selected household."""
    return service.list_items(db, household_id)


@router.post('', response_model=ShoppingItemOut, status_code=201)
def add_item(item: ShoppingItemCreate, household_id: UUID = Depends(get_current_household),
             current_user: UserOut = Depends(get_current_user), db: Session = Depends(get_db)):
    return service.add_item(db, household_id, item, actor=current_user)


@router.post('/clear-checked', response_model=ClearCheckedOut)
def clear_checked(household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Remove checked items only from the selected household."""
    return service.clear_checked(db, household_id)


@router.post('/trip/end', response_model=EndShoppingTripOut)
def end_trip(
    payload: EndShoppingTripRequest | None = Body(default=None),
    household_id: UUID = Depends(get_current_household),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Release active shopping claims for the current shopper or whole household trip."""
    scope = payload.scope if payload is not None else 'mine'
    return service.end_trip(db, household_id, current_user.id, scope=scope)


@router.patch('/{item_id}', response_model=ShoppingItemOut)
def update_item(item_id: UUID, update: ShoppingItemUpdate,
                household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    """Set checked explicitly or edit quantity/unit; omitted fields are preserved."""
    return service.update_item(db, household_id, item_id, update)


@router.delete('/{item_id}', status_code=204)
def delete_item(item_id: UUID, household_id: UUID = Depends(get_current_household), db: Session = Depends(get_db)):
    service.delete_item(db, household_id, item_id)
    return Response(status_code=204)


@router.post('/{item_id}/claim', response_model=ShoppingItemOut)
def claim_item(
    item_id: UUID,
    payload: ShoppingClaimRequest | None = Body(default=None),
    household_id: UUID = Depends(get_current_household),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Atomically claim a shopping item for the current shopper."""
    ttl = payload.ttl_minutes if payload is not None else service.DEFAULT_CLAIM_TTL_MINUTES
    return service.claim_item(db, household_id, item_id, current_user.id, ttl_minutes=ttl)


@router.delete('/{item_id}/claim', response_model=ShoppingItemOut)
def release_claim(
    item_id: UUID,
    household_id: UUID = Depends(get_current_household),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Release an active claim idempotently (or allow owner/admin override)."""
    return service.release_claim(db, household_id, item_id, current_user.id)


@router.post('/{item_id}/handoff', response_model=ShoppingItemOut)
def handoff_claim(
    item_id: UUID,
    payload: ShoppingHandoffRequest,
    household_id: UUID = Depends(get_current_household),
    current_user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Hand off a claimed or unclaimed shopping item to another member of the household."""
    return service.handoff_claim(
        db,
        household_id,
        item_id,
        current_user.id,
        payload.target_user_id,
        ttl_minutes=payload.ttl_minutes,
    )
