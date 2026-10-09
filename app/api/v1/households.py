from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.auth_errors import PROBLEM_SCHEMA
from app.core.dependencies import get_current_user
from app.core.rate_limit import limit_invite_joins
from app.dependencies.database import get_db
from app.schemas.household import (
    HouseholdCreate,
    HouseholdJoin,
    HouseholdMemberOut,
    HouseholdOut,
    MemberRoleUpdate,
)
from app.schemas.user import UserOut
from app.services import household_service

router = APIRouter(
    responses={
        code: {
            "description": description,
            "content": {
                "application/problem+json": {
                    "schema": PROBLEM_SCHEMA,
                }
            },
        }
        for code, description in [
            (404, "Invite code or member not found"),
            (409, "At least one owner must remain"),
            (429, "Too many join attempts"),
        ]
    }
)


@router.post(
    "",
    response_model=HouseholdOut,
    status_code=status.HTTP_201_CREATED,
)
def create_household(
    payload: HouseholdCreate,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a household and its owner membership atomically."""
    return household_service.create_household(db, user.id, payload.name)


@router.post("/join", response_model=HouseholdOut)
def join_household(
    payload: HouseholdJoin,
    user: UserOut = Depends(limit_invite_joins),
    db: Session = Depends(get_db),
):
    """Join using an invite code. Existing members keep their role."""
    return household_service.join_household(
        db,
        user.id,
        payload.invite_code,
    )


@router.get("/me", response_model=list[HouseholdOut])
def my_households(
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List only the current user's households and roles."""
    return household_service.list_households(db, user.id)


@router.post(
    "/{household_id}/invite-code/rotate",
    response_model=HouseholdOut,
)
def rotate_invite_code(
    household_id: UUID,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owners can immediately revoke the current invite code and create a new one."""
    return household_service.rotate_invite_code(
        db,
        str(household_id),
        user.id,
    )


@router.get(
    "/{household_id}/members",
    response_model=list[HouseholdMemberOut],
)
def list_members(
    household_id: UUID,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return household_service.list_members(
        db,
        str(household_id),
        user.id,
    )


@router.patch(
    "/{household_id}/members/{user_id}",
    response_model=HouseholdMemberOut,
)
def update_member_role(
    household_id: UUID,
    user_id: UUID,
    payload: MemberRoleUpdate,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Owners can change roles, preserving at least one owner."""
    return household_service.update_role(
        db,
        str(household_id),
        user.id,
        str(user_id),
        payload.role,
    )


@router.delete(
    "/{household_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    household_id: UUID,
    user_id: UUID,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Leave or remove a member, subject to role and last-owner protection."""
    household_service.remove_member(
        db,
        str(household_id),
        user.id,
        str(user_id),
    )
    return Response(status_code=204)
