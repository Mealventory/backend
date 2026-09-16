"""Household inventory using the PostgreSQL schema from scripts/init_db.sql.

The old per-user inventory routes remain separate for existing clients.
Every statement is scoped to the household verified by the route dependency.
"""
from uuid import uuid4
from sqlalchemy import text
from app.core.auth_errors import AuthProblem


ITEM_SELECT = '''SELECT i.id, i.household_id, f.name, f.category,
    i.quantity, i.unit, i.expiry_date, i.status
    FROM inventory_items i JOIN foods f ON f.id = i.food_id
    WHERE i.household_id = :household_id'''


def list_items(db, household_id):
    return db.execute(text(ITEM_SELECT + " AND i.status = 'active' ORDER BY i.created_at, i.id"),
                      {'household_id': str(household_id)}).mappings().all()


def add_item(db, household_id, item):
    food_id, item_id = str(uuid4()), str(uuid4())
    try:
        db.execute(text('''INSERT INTO foods (id, name, category, default_unit)
            VALUES (:id, :name, :category, :unit)'''),
                   dict(id=food_id, name=item.name, category=item.category, unit=item.unit))
        db.execute(text('''INSERT INTO inventory_items
            (id, household_id, food_id, quantity, unit, expiry_date, status)
            VALUES (:id, :household_id, :food_id, :quantity, :unit, :expiry_date, 'active')'''),
                   dict(id=item_id, household_id=str(household_id), food_id=food_id,
                        quantity=str(item.quantity), unit=item.unit, expiry_date=item.expiry_date))
        result = dict(db.execute(text(ITEM_SELECT + ' AND i.id = :id'),
                                dict(household_id=str(household_id), id=item_id)).mappings().one())
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def delete_item(db, household_id, item_id):
    try:
        result = db.execute(text('''DELETE FROM inventory_items
            WHERE id = :id AND household_id = :household_id'''),
                            dict(id=str(item_id), household_id=str(household_id)))
        if result.rowcount == 0:
            raise AuthProblem(404, 'Item not found in this household')
        db.commit()
    except Exception:
        db.rollback()
        raise
