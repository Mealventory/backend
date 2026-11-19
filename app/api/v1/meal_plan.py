"""Authenticated shared household meal plan endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_household, get_current_user
from app.dependencies.database import get_db
from app.schemas.meal_plan import (
    MealPlanAssign, MealPlanImportPreview, MealPlanImportRequest,
    MealPlanMove, MealPlanRemove, MealPlanState,
)
from app.schemas.user import UserOut
from app.services import meal_plan_service as service

router = APIRouter()


@router.get("", response_model=MealPlanState)
def list_plan(
    household: UUID = Depends(get_current_household),
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.list_plan(db, household, user.id)


@router.put("/slots", response_model=MealPlanState)
def assign(
    body: MealPlanAssign,
    household: UUID = Depends(get_current_household),
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.assign(db, household, user.id, body)


@router.post("/slots/remove", response_model=MealPlanState)
def remove(
    body: MealPlanRemove,
    household: UUID = Depends(get_current_household),
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.remove(db, household, user.id, body)


@router.post("/move", response_model=MealPlanState)
def move(
    body: MealPlanMove,
    household: UUID = Depends(get_current_household),
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.move(db, household, user.id, body)


@router.post("/import/preview", response_model=MealPlanImportPreview)
def preview_import(
    body: MealPlanImportRequest,
    household: UUID = Depends(get_current_household),
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.preview_import(db, household, user.id, body)


@router.post("/import", response_model=MealPlanState)
def import_local(
    body: MealPlanImportRequest,
    household: UUID = Depends(get_current_household),
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.import_local(db, household, user.id, body)
