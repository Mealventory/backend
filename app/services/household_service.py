"""Trusted membership writes with explicit authorization and serialized role changes.

Requires a server-owned database connection allowed to manage membership (#41).
Never accepts caller identity or initial membership role from request bodies.
"""
import secrets
import string

from sqlalchemy import bindparam, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth_errors import AuthProblem
from app.models.household import Household
from app.models.household_member import HouseholdMember
from app.schemas.household import HouseholdOut

INVITE_CODE_ATTEMPTS = 5


class InviteCodeCollisionLimit(AuthProblem):
    def __init__(self):
        super().__init__(503, "Unable to generate an invite code; please retry")


def generate_invite_code():
    return "".join(
        secrets.choice(string.ascii_uppercase + string.digits)
        for _ in range(6)
    )


def _is_invite_collision(exc):
    diag = getattr(exc.orig, "diag", None)
    return (
        getattr(diag, "constraint_name", None) == "households_invite_code_key"
        or "UNIQUE constraint failed: households.invite_code" in str(exc.orig)
    )


def _output(household, role):
    return HouseholdOut(
        id=household.id,
        name=household.name,
        invite_code=household.invite_code,
        role=role,
    )


def create_household(db: Session, user_id: str, name: str):
    for _ in range(INVITE_CODE_ATTEMPTS):
        try:
            household = Household(
                name=name,
                created_by=user_id,
                invite_code=generate_invite_code(),
            )
            db.add(household)
            db.flush()
            db.add(
                HouseholdMember(
                    household_id=household.id,
                    user_id=user_id,
                    role="owner",
                )
            )
            db.flush()
            result = _output(household, "owner")
            db.commit()
            return result
        except IntegrityError as exc:
            db.rollback()
            if not _is_invite_collision(exc):
                raise
        except Exception:
            db.rollback()
            raise
    raise InviteCodeCollisionLimit()


def join_household(db: Session, user_id: str, invite_code: str):
    try:
        household = (
            db.query(Household)
            .filter_by(invite_code=invite_code)
            .with_for_update()
            .first()
        )
        if household is None:
            raise AuthProblem(404, "Invalid invite code")
        member = db.get(HouseholdMember, (household.id, user_id))
        if member is None:
            member = HouseholdMember(
                household_id=household.id,
                user_id=user_id,
                role="member",
            )
            db.add(member)
        result = _output(household, member.role)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def list_households(db: Session, user_id: str):
    rows = (
        db.query(Household, HouseholdMember.role)
        .join(HouseholdMember, HouseholdMember.household_id == Household.id)
        .filter(HouseholdMember.user_id == user_id)
        .order_by(Household.created_at, Household.id)
        .all()
    )
    return [_output(household, role) for household, role in rows]


def _household_and_caller(db, household_id, user_id, lock=False):
    query = db.query(Household).filter_by(id=household_id)
    if lock:
        query = query.with_for_update()
    household = query.first()
    caller = (
        db.get(HouseholdMember, (household_id, user_id))
        if household
        else None
    )
    if caller is None:
        raise AuthProblem(403, "You are not a member of this household")
    return household, caller


def _authorize(db, household_id, user_id, lock=False):
    _, caller = _household_and_caller(
        db,
        household_id,
        user_id,
        lock=lock,
    )
    return caller


def rotate_invite_code(db: Session, household_id: str, user_id: str):
    """Replace a household invite code atomically; only current owners may rotate it."""
    for _ in range(INVITE_CODE_ATTEMPTS):
        try:
            household, caller = _household_and_caller(
                db,
                household_id,
                user_id,
                lock=True,
            )
            if caller.role != "owner":
                raise AuthProblem(
                    403,
                    "Only owners can rotate the household invite code",
                )

            new_code = generate_invite_code()
            if new_code == household.invite_code:
                continue

            household.invite_code = new_code
            db.flush()
            result = _output(household, caller.role)
            db.commit()
            return result
        except IntegrityError as exc:
            db.rollback()
            if not _is_invite_collision(exc):
                raise
        except Exception:
            db.rollback()
            raise

    db.rollback()
    raise InviteCodeCollisionLimit()


def _member_identity(email: str | None, metadata: dict | None) -> tuple[str | None, str | None]:
    """Use the selected username, then display name, then the email local part."""
    data = metadata if isinstance(metadata, dict) else {}

    def clean(value):
        return value.strip()[:120] or None if isinstance(value, str) else None

    username = clean(data.get("username"))
    explicit_name = clean(data.get("display_name"))
    email_prefix = clean(email.split("@", 1)[0]) if isinstance(email, str) and "@" in email else None
    display_name = username or explicit_name or email_prefix
    return display_name, username


def _auth_member_profiles(db: Session, user_ids: list[str]) -> dict[str, dict]:
    """Read display-only identities from the server-side Supabase Auth table.

    Never expose the raw email or Auth metadata in household responses. Local
    databases without the Supabase Auth schema simply return no profiles.
    """
    if not user_ids or db.get_bind().dialect.name != "postgresql":
        return {}
    if db.execute(text("SELECT to_regclass('auth.users')")).scalar() is None:
        return {}
    if not db.execute(
        text("SELECT has_table_privilege(current_user, 'auth.users', 'SELECT')")
    ).scalar():
        return {}

    query = text("""
        SELECT CAST(id AS TEXT) AS user_id, email, raw_user_meta_data
        FROM auth.users
        WHERE CAST(id AS TEXT) IN :user_ids
    """).bindparams(bindparam("user_ids", expanding=True))

    profiles = {}
    for row in db.execute(query, {"user_ids": user_ids}).mappings():
        display_name, username = _member_identity(
            row["email"], row["raw_user_meta_data"]
        )
        profiles[row["user_id"]] = {
            "display_name": display_name,
            "username": username,
        }
    return profiles


def list_members(db: Session, household_id: str, user_id: str):
    _authorize(db, household_id, user_id)
    members = (
        db.query(HouseholdMember)
        .filter_by(household_id=household_id)
        .order_by(HouseholdMember.user_id)
        .all()
    )
    profiles = _auth_member_profiles(db, [str(m.user_id) for m in members])
    return [
        {
            "household_id": member.household_id,
            "user_id": member.user_id,
            "role": member.role,
            **profiles.get(str(member.user_id), {}),
        }
        for member in members
    ]


def _protect_last_owner(db, household_id, target):
    if (
        target.role == "owner"
        and db.query(HouseholdMember)
        .filter_by(household_id=household_id, role="owner")
        .count()
        <= 1
    ):
        raise AuthProblem(
            409,
            "The last owner cannot leave or be demoted; appoint another owner first",
        )


def update_role(
    db: Session,
    household_id: str,
    user_id: str,
    target_id: str,
    role: str,
):
    try:
        caller = _authorize(db, household_id, user_id, lock=True)
        if caller.role != "owner":
            raise AuthProblem(403, "Only owners can change member roles")
        target = db.get(HouseholdMember, (household_id, target_id))
        if target is None:
            raise AuthProblem(404, "Member not found")
        if role != "owner":
            _protect_last_owner(db, household_id, target)
        target.role = role
        db.commit()
        return target
    except Exception:
        db.rollback()
        raise


def remove_member(
    db: Session,
    household_id: str,
    user_id: str,
    target_id: str,
):
    try:
        caller = _authorize(db, household_id, user_id, lock=True)
        target = db.get(HouseholdMember, (household_id, target_id))
        if target is None:
            raise AuthProblem(404, "Member not found")
        if user_id != target_id and not (
            caller.role == "owner"
            or (caller.role == "admin" and target.role == "member")
        ):
            raise AuthProblem(403, "You cannot remove this member")
        _protect_last_owner(db, household_id, target)
        db.delete(target)
        db.commit()
    except Exception:
        db.rollback()
        raise
