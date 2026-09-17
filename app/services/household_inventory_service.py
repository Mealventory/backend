"""Household inventory using the PostgreSQL schema from scripts/init_db.sql.

The old per-user inventory routes remain separate for existing clients.
Every statement is scoped to the household verified by the route dependency.
"""
from uuid import uuid4
from datetime import date, timedelta
from sqlalchemy import text
from app.core.auth_errors import AuthProblem


ITEM_SELECT = '''SELECT i.id, i.household_id, f.name, f.category,
    i.quantity, i.unit, i.expiry_date, i.status, i.storage_location_id
    FROM inventory_items i JOIN foods f ON f.id = i.food_id
    WHERE i.household_id = :household_id'''


def list_items(db, household_id, status='active', zone=None, expiring_days=None, search=None):
    params = {'household_id': str(household_id), 'status': status}
    sql = ITEM_SELECT + ' AND i.status = :status'
    if zone:
        sql += ''' AND EXISTS (SELECT 1 FROM storage_locations s WHERE s.id = i.storage_location_id
            AND s.household_id = i.household_id AND s.zone = :zone)'''
        params['zone'] = zone
    if expiring_days is not None:
        sql += ' AND i.expiry_date <= :cutoff'
        params['cutoff'] = date.today() + timedelta(days=expiring_days)
    if search:
        sql += " AND lower(f.name) LIKE :search ESCAPE '!'"
        params['search'] = '%' + search.lower().replace('!', '!!').replace('%', '!%').replace('_', '!_') + '%'
    return db.execute(text(sql + ' ORDER BY i.created_at, i.id'), params).mappings().all()


def _check_location(db, household_id, location_id):
    if location_id and not db.execute(text('''SELECT 1 FROM storage_locations
        WHERE id = :id AND household_id = :household_id'''),
        dict(id=str(location_id), household_id=str(household_id))).first():
        raise AuthProblem(404, 'Storage location not found in this household')


def get_item(db, household_id, item_id):
    row = db.execute(text(ITEM_SELECT + ' AND i.id = :id'),
                     dict(household_id=str(household_id), id=str(item_id))).mappings().first()
    if row is None:
        raise AuthProblem(404, 'Item not found in this household')
    return dict(row)


def add_item(db, household_id, item, *, commit=True):
    food_id, item_id = str(uuid4()), str(uuid4())
    try:
        _check_location(db, household_id, item.storage_location_id)
        db.execute(text('''INSERT INTO foods (id, name, category, default_unit)
            VALUES (:id, :name, :category, :unit)'''),
                   dict(id=food_id, name=item.name, category=item.category, unit=item.unit))
        db.execute(text('''INSERT INTO inventory_items
            (id, household_id, food_id, quantity, unit, expiry_date, status, storage_location_id)
            VALUES (:id, :household_id, :food_id, :quantity, :unit, :expiry_date, 'active', :location)'''),
                   dict(id=item_id, household_id=str(household_id), food_id=food_id,
                        quantity=str(item.quantity), unit=item.unit, expiry_date=item.expiry_date,
                        location=str(item.storage_location_id) if item.storage_location_id else None))
        result = dict(db.execute(text(ITEM_SELECT + ' AND i.id = :id'),
                                dict(household_id=str(household_id), id=item_id)).mappings().one())
        if commit:
            db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def add_batch(db, household_id, items):
    try:
        rows = [add_item(db, household_id, item, commit=False) for item in items]
        db.commit()
        return rows
    except Exception:
        db.rollback()
        raise


def update_item(db, household_id, item_id, patch):
    try:
        values = patch.model_dump(exclude_unset=True)
        if 'storage_location_id' in values:
            _check_location(db, household_id, values['storage_location_id'])
        # Field names originate only from the validated schema, never raw request keys.
        columns = {'quantity', 'unit', 'expiry_date', 'storage_location_id'}
        values = {key: value for key, value in values.items() if key in columns}
        for key in ('quantity', 'storage_location_id'):
            if values.get(key) is not None:
                values[key] = str(values[key])
        assignments = ', '.join(f'{key} = :{key}' for key in values)
        result = db.execute(text(f'''UPDATE inventory_items SET {assignments}
            WHERE id = :id AND household_id = :household_id AND status = 'active' '''),
            dict(values, id=str(item_id), household_id=str(household_id)))
        if result.rowcount == 0:
            get_item(db, household_id, item_id)
            raise AuthProblem(409, 'Only active items can be edited')
        row = get_item(db, household_id, item_id)
        db.commit()
        return row
    except Exception:
        db.rollback()
        raise


def transition_item(db, household_id, item_id, target):
    if target not in ('consumed', 'discarded'):
        raise ValueError('Unsupported item transition')
    try:
        # Conditional update serializes competing transitions without overwriting history.
        result = db.execute(text('''UPDATE inventory_items SET status = :target
            WHERE id = :id AND household_id = :household_id AND status = 'active' '''),
            dict(target=target, id=str(item_id), household_id=str(household_id)))
        row = get_item(db, household_id, item_id)
        if result.rowcount == 0 and row['status'] != target:
            raise AuthProblem(409, 'Item already has a different final status')
        db.commit()
        return row
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
