"""Household inventory using the PostgreSQL schema from scripts/init_db.sql.

The old per-user inventory routes remain separate for existing clients.
Every statement is scoped to the household verified by the route dependency.
"""
import logging
from uuid import uuid4
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import text
from app.core.auth_errors import AuthProblem
from app.services.notification_service import send_low_stock_notification
from app.services import activity_service

logger = logging.getLogger(__name__)


ITEM_SELECT = '''SELECT i.id, i.household_id, f.name, f.category,
    i.quantity, i.initial_quantity, i.unit, i.expiry_date, i.status, i.storage_location_id, i.image_ref,
    (SELECT s.zone FROM storage_locations s WHERE s.id = i.storage_location_id
        AND s.household_id = i.household_id) AS storage_zone
    FROM inventory_items i JOIN foods f ON f.id = i.food_id
    WHERE i.household_id = :household_id'''


def _decorate_item(row):
    item = dict(row)
    initial = item.get('initial_quantity')
    if initial is not None and Decimal(str(initial)) > 0:
        percent = (
            Decimal(str(item['quantity'])) * Decimal('100') / Decimal(str(initial))
        ).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)
        # A correction/restock can temporarily exceed the original amount;
        # user-facing "remaining" should never read above 100%.
        item['remaining_percent'] = min(percent, Decimal('100.0'))
        item['is_low_stock'] = percent <= Decimal('10')
    else:
        item['remaining_percent'] = None
        item['is_low_stock'] = False
    return item


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
    rows = db.execute(text(sql + ' ORDER BY i.created_at, i.id'), params).mappings().all()
    return [_decorate_item(row) for row in rows]


def _check_image_ref_household(household_id, image_ref):
    if image_ref and not str(image_ref).startswith('https://'):
        owner = str(image_ref).split('/', 1)[0]
        if owner != str(household_id):
            raise AuthProblem(400, 'Image path must belong to the selected household')


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
    return _decorate_item(row)


def add_item(db, household_id, item, *, commit=True, actor=None):
    food_id, item_id = str(uuid4()), str(uuid4())
    try:
        _check_location(db, household_id, item.storage_location_id)
        _check_image_ref_household(household_id, item.image_ref)
        location = str(item.storage_location_id) if item.storage_location_id else _zone_location(db, household_id, item.storage_zone)
        db.execute(text('''INSERT INTO foods (id, name, category, default_unit)
            VALUES (:id, :name, :category, :unit)'''),
                   dict(id=food_id, name=item.name, category=item.category, unit=item.unit))
        db.execute(text('''INSERT INTO inventory_items
            (id, household_id, food_id, quantity, quantity_tracking_enabled, initial_quantity,
             low_stock_threshold_percent, unit, expiry_date, status, storage_location_id, image_ref)
            VALUES (:id, :household_id, :food_id, :quantity, :tracking, :initial_quantity,
                    :threshold, :unit, :expiry_date, 'active', :location, :image_ref)'''),
                   dict(id=item_id, household_id=str(household_id), food_id=food_id,
                        quantity=str(item.quantity), tracking=True,
                        initial_quantity=str(item.quantity),
                        threshold='10', unit=item.unit,
                        expiry_date=item.expiry_date, location=location,
                        image_ref=item.image_ref))
        result = get_item(db, household_id, item_id)
        activity_service.record_event(db, household_id, actor, 'added', result['name'], entity_id=item_id)
        if commit:
            db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def add_batch(db, household_id, items, actor=None, *, commit=True):
    try:
        rows = [add_item(db, household_id, item, commit=False, actor=actor) for item in items]
        if commit:
            db.commit()
        return rows
    except Exception:
        db.rollback()
        raise


def _zone_location(db, household_id, zone):
    name = f'Default {zone}'
    params = dict(id=str(uuid4()), household_id=str(household_id), name=name, zone=zone)
    db.execute(text("""INSERT INTO storage_locations (id, household_id, name, zone)
        VALUES (:id, :household_id, :name, :zone)
        ON CONFLICT (household_id, name) DO NOTHING"""), params)
    row = db.execute(text('SELECT id, zone FROM storage_locations WHERE household_id=:household_id AND name=:name'), params).mappings().one()
    if row['zone'] != zone:
        raise AuthProblem(409, 'Default storage location has a different zone; choose a storage_location_id')
    return str(row['id'])


def update_item(db, household_id, item_id, patch, actor=None):
    try:
        values = patch.model_dump(exclude_unset=True)
        params = dict(id=str(item_id), household_id=str(household_id))
        # Serialize all edits against status transitions before copying catalogue data.
        lock = ' FOR UPDATE' if db.get_bind().dialect.name == 'postgresql' else ''
        current = db.execute(text('''SELECT food_id, status, storage_location_id
            FROM inventory_items WHERE id=:id AND household_id=:household_id''' + lock),
            params).mappings().first()
        if current is None:
            raise AuthProblem(404, 'Item not found in this household')
        if current['status'] != 'active':
            if values == {'status': current['status']}:
                row = get_item(db, household_id, item_id)
                db.commit()
                return row
            raise AuthProblem(409, 'Only active items can be edited')
        if 'storage_location_id' in values:
            _check_location(db, household_id, values['storage_location_id'])
        if 'image_ref' in values:
            _check_image_ref_household(household_id, values['image_ref'])
        if 'storage_zone' in values:
            values['storage_location_id'] = _zone_location(db, household_id, values.pop('storage_zone'))
        if 'name' in values or 'category' in values:
            # Food rows can be shared by other households and recipe ingredients.
            food = db.execute(text('SELECT name, category, default_unit, avg_shelf_life_days FROM foods WHERE id=:food_id'),
                              {'food_id': str(current['food_id'])}).mappings().one()
            name = values.pop('name', food['name'])
            category = values.pop('category', food['category'])
            if (name, category) != (food['name'], food['category']):
                food_id = str(uuid4())
                db.execute(text('INSERT INTO foods (id, name, category, default_unit, avg_shelf_life_days) VALUES (:id, :name, :category, :unit, :shelf_life)'),
                           dict(id=food_id, name=name, category=category, unit=food['default_unit'], shelf_life=food['avg_shelf_life_days']))
                values['food_id'] = food_id
        for key in ('quantity', 'storage_location_id'):
            if values.get(key) is not None:
                values[key] = str(values[key])
        if values:
            # Keys come exclusively from ItemUpdate and the internal food replacement.
            assignments = ', '.join(f'{key} = :{key}' for key in values)
            db.execute(text(f'UPDATE inventory_items SET {assignments} WHERE id=:id AND household_id=:household_id'),
                       dict(values, **params))
        row = get_item(db, household_id, item_id)
        quantity_changed = 'quantity' in values
        activity_action = (
            'moved'
            if str(current['storage_location_id'] or '') != str(row['storage_location_id'] or '')
            else 'updated'
        )
        activity_service.record_event(
            db, household_id, actor, activity_action, row['name'], entity_id=item_id
        )
        db.commit()
        if quantity_changed:
            try:
                send_low_stock_notification(db, str(household_id), str(item_id))
            except Exception:
                db.rollback()
                logger.exception("Low-stock notification failed after inventory update")
        return row
    except Exception:
        db.rollback()
        raise


def transition_item(db, household_id, item_id, target, actor=None):
    if target not in ('consumed', 'discarded'):
        raise ValueError('Unsupported item transition')
    try:
        # Conditional update serializes competing transitions without overwriting history.
        result = db.execute(text('''UPDATE inventory_items SET status = :target
            WHERE id = :id AND household_id = :household_id AND status = 'active' '''),
            dict(target=target, id=str(item_id), household_id=str(household_id)))
        row = get_item(db, household_id, item_id)
        if result.rowcount == 0:
            raise AuthProblem(400, 'Item is not active')
        activity_service.record_event(
            db, household_id, actor, target, row['name'], entity_id=item_id
        )
        db.commit()
        return row
    except Exception:
        db.rollback()
        raise


def delete_item(db, household_id, item_id, actor=None):
    try:
        item = get_item(db, household_id, item_id)
        result = db.execute(text('''DELETE FROM inventory_items
            WHERE id = :id AND household_id = :household_id'''),
                            dict(id=str(item_id), household_id=str(household_id)))
        if result.rowcount == 0:
            raise AuthProblem(404, 'Item not found in this household')
        activity_service.record_event(
            db, household_id, actor, 'deleted', item['name'], entity_id=item_id
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
