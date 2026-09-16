from uuid import UUID
from pydantic import ValidationError
from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.auth_errors import AuthProblem
from app.core.security import verify_supabase_token
from app.dependencies.database import get_db
from app.models.household_member import HouseholdMember
from app.schemas.user import UserOut

bearer_scheme = HTTPBearer(auto_error=False, description="Supabase user access token")


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> UserOut:
    if credentials is None:
        raise AuthProblem(401, "Bearer token required")
    claims = verify_supabase_token(credentials.credentials)
    # Identity comes only from a verified token, never request payloads or headers.
    try:
        return UserOut(id=claims["sub"], email=claims.get("email") or None)
    except ValidationError:
        raise AuthProblem(401, "Invalid user identity claims") from None


def get_current_household(
    request: Request,
    current_user: UserOut = Depends(get_current_user),
    x_household_id: str | None = Header(default=None, alias="X-Household-ID"),
    db: Session = Depends(get_db),
) -> UUID:
    try:
        household_id = UUID(x_household_id) if x_household_id else None
    except (ValueError, TypeError):
        raise AuthProblem(400, "X-Household-ID must be a UUID") from None
    if household_id is None:
        raise AuthProblem(400, "X-Household-ID is required")
    member = db.query(HouseholdMember).filter(
        HouseholdMember.user_id == current_user.id,
        HouseholdMember.household_id == str(household_id),
    ).first()
    if member is None:
        raise AuthProblem(403, "You are not a member of this household")
    request.state.user_id = current_user.id
    request.state.household_id = household_id
    return household_id
