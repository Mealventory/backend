"""Atomic, replay-safe deductions of explicitly reviewed pantry quantities."""
import hashlib
import json
from decimal import Decimal
from sqlalchemy import text
from app.core.auth_errors import AuthProblem


def complete_recipe(db, household_id, request):
    payload = request.model_dump(mode='json', exclude={'completion_id'})
    payload['items'].sort(key=lambda item: item['item_id'])
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    params = dict(household_id=str(household_id), completion_id=request.completion_id,
                  fingerprint=fingerprint)
    try:
        # The unique key also serializes simultaneous retries before any item changes.
        inserted = db.execute(text('''INSERT INTO household_recipe_completions
            (household_id, completion_id, fingerprint, result)
            VALUES (:household_id, :completion_id, :fingerprint, NULL)
            ON CONFLICT (household_id, completion_id) DO NOTHING'''), params)
        if inserted.rowcount == 0:
            previous = db.execute(text('''SELECT fingerprint, result FROM household_recipe_completions
                WHERE household_id=:household_id AND completion_id=:completion_id'''), params).mappings().one()
            if previous['fingerprint'] != fingerprint:
                raise AuthProblem(409, 'This meal was already submitted with different amounts. Retry the original review.')
            result = json.loads(previous['result'])
            db.commit()
            return result

        result = {'completion_id': request.completion_id, 'recipe_name': request.recipe_name, 'items': []}
        lock = ' FOR UPDATE' if db.get_bind().dialect.name == 'postgresql' else ''
        # Stable lock ordering avoids deadlocks when two meals use the same ingredients.
        for item in sorted(request.items, key=lambda item: str(item.item_id)):
            item_params = dict(household_id=str(household_id), id=str(item.item_id))
            row = db.execute(text('''SELECT quantity, unit, status, (SELECT name FROM foods WHERE foods.id=inventory_items.food_id) AS name FROM inventory_items
                WHERE household_id=:household_id AND id=:id''' + lock), item_params).mappings().first()
            if row is None:
                raise AuthProblem(404, 'A reviewed item is no longer in this household. Reload your review.')
            available = Decimal(str(row['quantity']))
            if row['status'] != 'active' or available != item.expected_quantity or row['unit'] != item.unit:
                raise AuthProblem(409, 'Your pantry changed. Reload the review and check the amounts again.')
            if item.quantity > available:
                raise AuthProblem(409, 'The amount used is greater than the amount in your pantry.')
            remaining = available - item.quantity
            # Preserve the consumed amount on terminal rows for existing history/analytics.
            if remaining == 0:
                db.execute(text("UPDATE inventory_items SET status='consumed' WHERE household_id=:household_id AND id=:id"), item_params)
            else:
                db.execute(text('UPDATE inventory_items SET quantity=:quantity WHERE household_id=:household_id AND id=:id'),
                           dict(item_params, quantity=str(remaining)))
            result['items'].append({'item_id': str(item.item_id), 'name': row['name'], 'used': str(item.quantity),
                                    'remaining': str(remaining), 'unit': item.unit,
                                    'status': 'consumed' if remaining == 0 else 'active'})
        db.execute(text('''UPDATE household_recipe_completions SET result=:result
            WHERE household_id=:household_id AND completion_id=:completion_id'''),
            dict(params, result=json.dumps(result)))
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
