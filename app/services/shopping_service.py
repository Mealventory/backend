"""Shopping list persistence against the shared household DDL."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from sqlalchemy import DateTime, bindparam, inspect, text
from sqlalchemy.exc import IntegrityError
from app.core.auth_errors import AuthProblem
from app.models.household_member import HouseholdMember
from app.services import activity_service

COLUMNS = (
    'id, household_id, food_id, name, quantity, unit, is_checked AS checked, '
    'claimed_by, claimed_at, claim_expires_at, created_at, updated_at'
)

DEFAULT_CLAIM_TTL_MINUTES = 120


def _utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    return now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)


def _as_utc(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        text_val = value.strip()
        if text_val.endswith('Z'):
            text_val = text_val[:-1] + '+00:00'
        value = datetime.fromisoformat(text_val)
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return None


def _normalize_claim(row, now: datetime | None = None) -> dict:
    item = dict(row)
    current = _utc_now(now)
    expires = _as_utc(item.get('claim_expires_at'))
    if expires is not None and expires <= current:
        item['claimed_by'] = None
        item['claimed_at'] = None
        item['claim_expires_at'] = None
    return item


def list_items(db, household_id, now: datetime | None = None):
    rows = db.execute(
        text(
            f'SELECT {COLUMNS} FROM shopping_list_items WHERE household_id=:home '
            'ORDER BY is_checked, created_at, id'
        ),
        {'home': str(household_id)},
    ).mappings().all()
    current = _utc_now(now)
    return [_normalize_claim(row, current) for row in rows]


def add_item(db, household_id, item, actor=None):
    try:
        if item.food_id and not db.execute(text('SELECT 1 FROM foods WHERE id=:id'),
                                           {'id': str(item.food_id)}).first():
            raise AuthProblem(404, 'Food not found')
        row = db.execute(text(f"""INSERT INTO shopping_list_items
            (id, household_id, food_id, name, quantity, unit, is_checked)
            VALUES (:id, :home, :food, :name, :quantity, :unit, false)
            RETURNING {COLUMNS}"""), dict(id=str(uuid4()), home=str(household_id),
            food=str(item.food_id) if item.food_id else None, name=item.name,
            quantity=str(item.quantity), unit=item.unit)).mappings().one()
        result = _normalize_claim(row)
        activity_service.record_event(
            db,
            household_id,
            actor,
            'shopping_added',
            result['name'],
            entity_type='shopping',
            entity_id=result['id'],
        )
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        raise AuthProblem(409, 'Referenced food or household changed; refresh and retry') from None
    except Exception:
        db.rollback()
        raise


def update_item(db, household_id, item_id, update):
    fields = update.model_dump(exclude_unset=True)
    columns = {'checked': 'is_checked', 'quantity': 'quantity', 'unit': 'unit'}
    assignments = ', '.join(f'{columns[key]}=:{key}' for key in fields)
    params = {key: str(value) if key == 'quantity' else value for key, value in fields.items()}
    params.update(home=str(household_id), id=str(item_id))
    try:
        row = db.execute(text(f'UPDATE shopping_list_items SET {assignments}, updated_at=CURRENT_TIMESTAMP '
                              f'WHERE household_id=:home AND id=:id RETURNING {COLUMNS}'), params).mappings().first()
        if row is None:
            raise AuthProblem(404, 'Shopping item not found in this household')
        result = _normalize_claim(row)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def delete_item(db, household_id, item_id):
    try:
        row = db.execute(text('DELETE FROM shopping_list_items WHERE household_id=:home AND id=:id RETURNING id'),
                         dict(home=str(household_id), id=str(item_id))).first()
        if row is None:
            raise AuthProblem(404, 'Shopping item not found in this household')
        db.commit()
    except Exception:
        db.rollback()
        raise


def clear_checked(db, household_id):
    try:
        result = db.execute(text('DELETE FROM shopping_list_items WHERE household_id=:home AND is_checked=true'),
                            {'home': str(household_id)})
        count = result.rowcount
        db.commit()
        return {'deleted_count': count}
    except Exception:
        db.rollback()
        raise


def _caller_role(db, household_id, user_id) -> str | None:
    member = db.get(HouseholdMember, (str(household_id), str(user_id)))
    return member.role if member is not None else None


def _item_exists_in_household(db, household_id, item_id) -> bool:
    return db.execute(
        text('SELECT 1 FROM shopping_list_items WHERE household_id=:home AND id=:id'),
        {'home': str(household_id), 'id': str(item_id)},
    ).first() is not None


def claim_item(
    db,
    household_id,
    item_id,
    user_id,
    ttl_minutes: int | None = DEFAULT_CLAIM_TTL_MINUTES,
    now: datetime | None = None,
):
    current = _utc_now(now)
    expires = current + timedelta(minutes=ttl_minutes) if ttl_minutes is not None else None
    try:
        stmt = text(
            f'UPDATE shopping_list_items '
            f'SET claimed_by=:user, claimed_at=:now, claim_expires_at=:expires, '
            f'updated_at=CURRENT_TIMESTAMP '
            f'WHERE household_id=:home AND id=:id '
            f'AND (claimed_by IS NULL OR claimed_by=:user '
            f'OR (claim_expires_at IS NOT NULL AND claim_expires_at <= :now)) '
            f'RETURNING {COLUMNS}'
        ).bindparams(
            bindparam('now', type_=DateTime(timezone=True)),
            bindparam('expires', type_=DateTime(timezone=True)),
        )
        row = db.execute(
            stmt,
            {
                'home': str(household_id),
                'id': str(item_id),
                'user': str(user_id),
                'now': current,
                'expires': expires,
            },
        ).mappings().first()
        if row is None:
            if not _item_exists_in_household(db, household_id, item_id):
                raise AuthProblem(404, 'Shopping item not found in this household')
            raise AuthProblem(
                409,
                {
                    'message': 'Shopping item is already claimed by another shopper',
                    'code': 'shopping_item_already_claimed',
                },
            )
        result = _normalize_claim(row, current)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def release_claim(
    db,
    household_id,
    item_id,
    user_id,
    now: datetime | None = None,
):
    current = _utc_now(now)
    try:
        role = _caller_role(db, household_id, user_id)
        can_override = role in ('owner', 'admin')
        if can_override:
            stmt = text(
                f'UPDATE shopping_list_items '
                f'SET claimed_by=NULL, claimed_at=NULL, claim_expires_at=NULL, '
                f'updated_at=CURRENT_TIMESTAMP '
                f'WHERE household_id=:home AND id=:id '
                f'RETURNING {COLUMNS}'
            )
            params = {'home': str(household_id), 'id': str(item_id)}
        else:
            stmt = text(
                f'UPDATE shopping_list_items '
                f'SET claimed_by=NULL, claimed_at=NULL, claim_expires_at=NULL, '
                f'updated_at=CURRENT_TIMESTAMP '
                f'WHERE household_id=:home AND id=:id '
                f'AND (claimed_by IS NULL OR claimed_by=:user '
                f'OR (claim_expires_at IS NOT NULL AND claim_expires_at <= :now)) '
                f'RETURNING {COLUMNS}'
            ).bindparams(bindparam('now', type_=DateTime(timezone=True)))
            params = {
                'home': str(household_id),
                'id': str(item_id),
                'user': str(user_id),
                'now': current,
            }

        row = db.execute(stmt, params).mappings().first()
        if row is None:
            if not _item_exists_in_household(db, household_id, item_id):
                raise AuthProblem(404, 'Shopping item not found in this household')
            raise AuthProblem(
                409,
                {
                    'message': 'Shopping item is currently claimed by another shopper',
                    'code': 'shopping_item_claimed_by_other',
                },
            )
        result = _normalize_claim(row, current)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def handoff_claim(
    db,
    household_id,
    item_id,
    user_id,
    target_user_id,
    ttl_minutes: int | None = DEFAULT_CLAIM_TTL_MINUTES,
    now: datetime | None = None,
):
    current = _utc_now(now)
    expires = current + timedelta(minutes=ttl_minutes) if ttl_minutes is not None else None
    try:
        if _caller_role(db, household_id, target_user_id) is None:
            raise AuthProblem(404, 'Target shopper is not a member of this household')

        role = _caller_role(db, household_id, user_id)
        can_override = role in ('owner', 'admin')
        if can_override:
            stmt = text(
                f'UPDATE shopping_list_items '
                f'SET claimed_by=:target, claimed_at=:now, claim_expires_at=:expires, '
                f'updated_at=CURRENT_TIMESTAMP '
                f'WHERE household_id=:home AND id=:id '
                f'RETURNING {COLUMNS}'
            ).bindparams(
                bindparam('now', type_=DateTime(timezone=True)),
                bindparam('expires', type_=DateTime(timezone=True)),
            )
            params = {
                'home': str(household_id),
                'id': str(item_id),
                'target': str(target_user_id),
                'now': current,
                'expires': expires,
            }
        else:
            stmt = text(
                f'UPDATE shopping_list_items '
                f'SET claimed_by=:target, claimed_at=:now, claim_expires_at=:expires, '
                f'updated_at=CURRENT_TIMESTAMP '
                f'WHERE household_id=:home AND id=:id '
                f'AND (claimed_by IS NULL OR claimed_by=:user '
                f'OR (claim_expires_at IS NOT NULL AND claim_expires_at <= :now)) '
                f'RETURNING {COLUMNS}'
            ).bindparams(
                bindparam('now', type_=DateTime(timezone=True)),
                bindparam('expires', type_=DateTime(timezone=True)),
            )
            params = {
                'home': str(household_id),
                'id': str(item_id),
                'user': str(user_id),
                'target': str(target_user_id),
                'now': current,
                'expires': expires,
            }

        row = db.execute(stmt, params).mappings().first()
        if row is None:
            if not _item_exists_in_household(db, household_id, item_id):
                raise AuthProblem(404, 'Shopping item not found in this household')
            raise AuthProblem(
                409,
                {
                    'message': 'Shopping item is already claimed by another shopper',
                    'code': 'shopping_item_already_claimed',
                },
            )
        result = _normalize_claim(row, current)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def end_trip(db, household_id, user_id, scope: str = 'mine'):
    try:
        if scope == 'all':
            result = db.execute(
                text(
                    'UPDATE shopping_list_items '
                    'SET claimed_by=NULL, claimed_at=NULL, claim_expires_at=NULL, '
                    'updated_at=CURRENT_TIMESTAMP '
                    'WHERE household_id=:home AND claimed_by IS NOT NULL'
                ),
                {'home': str(household_id)},
            )
        else:
            result = db.execute(
                text(
                    'UPDATE shopping_list_items '
                    'SET claimed_by=NULL, claimed_at=NULL, claim_expires_at=NULL, '
                    'updated_at=CURRENT_TIMESTAMP '
                    'WHERE household_id=:home AND claimed_by=:user'
                ),
                {'home': str(household_id), 'user': str(user_id)},
            )
        count = result.rowcount or 0
        db.commit()
        return {'released_count': count}
    except Exception:
        db.rollback()
        raise


def clear_member_claims(db, household_id, user_id) -> None:
    """Clear active shopping claims held by a departing household member inside the caller's transaction."""
    if not inspect(db.get_bind()).has_table('shopping_list_items'):
        return
    db.execute(
        text(
            'UPDATE shopping_list_items '
            'SET claimed_by=NULL, claimed_at=NULL, claim_expires_at=NULL, '
            'updated_at=CURRENT_TIMESTAMP '
            'WHERE household_id=:home AND claimed_by=:user'
        ),
        {'home': str(household_id), 'user': str(user_id)},
    )
