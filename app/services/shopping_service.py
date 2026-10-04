"""Shopping list persistence against the shared household DDL."""
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.core.auth_errors import AuthProblem
from app.services import activity_service

COLUMNS = 'id, household_id, food_id, name, quantity, unit, is_checked AS checked, created_at, updated_at'


def list_items(db, household_id):
    return db.execute(text(f'SELECT {COLUMNS} FROM shopping_list_items WHERE household_id=:home '
                           'ORDER BY is_checked, created_at, id'),
                      {'home': str(household_id)}).mappings().all()


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
        result = dict(row)
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
        result = dict(row)
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
