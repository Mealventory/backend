"""Explicitly opt-in local PostgreSQL demo seeder; never reads DATABASE_URL."""
import argparse
from datetime import date, timedelta
import os
from uuid import UUID
from sqlalchemy import create_engine, text, bindparam
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from app.db.fixtures.demo import USERS, HOUSEHOLDS, FOODS, RECIPES, fixture_id

MAX_ITEMS = 10000


def validate_target(value):
    if not value:
        raise ValueError('Set SEED_DATABASE_URL to a dedicated local database ending in _demo or _test')
    url = make_url(value)
    if (url.get_backend_name() != 'postgresql' or url.host not in ('localhost', '127.0.0.1', '::1')
            or not url.database or not url.database.endswith(('_demo', '_test')) or url.query):
        raise ValueError('Seeding requires local PostgreSQL, a _demo/_test database name, and no URL query overrides')
    if any(os.getenv(key) for key in ('PGHOST', 'PGHOSTADDR', 'PGSERVICE', 'PGSERVICEFILE')):
        raise ValueError('Unset PostgreSQL host/service overrides before seeding')
    return url


def seed(connection, *, items=50, reset=False, user_ids=None, today=None):
    """Caller owns the transaction; reset modifies only deterministic fixture rows."""
    if not 50 <= items <= MAX_ITEMS:
        raise ValueError('items must be between 50 and 10000')
    user_ids = [str(UUID(str(value))) for value in (user_ids or [u.id for u in USERS])]
    if len(user_ids) != 4 or len(set(user_ids)) != 4:
        raise ValueError('Provide exactly four distinct test-user UUIDs')
    today = today or date.today()
    connection.execute(text('SELECT pg_advisory_xact_lock(600060)'))

    def insert(table, row, key='id'):
        columns = ', '.join(row)
        values = ', '.join(':' + column for column in row)
        conflict = 'DO NOTHING'
        if reset:
            updates = ', '.join(f'{column}=EXCLUDED.{column}' for column in row if column not in key.split(', '))
            conflict = 'DO UPDATE SET ' + updates
        connection.execute(text(f'INSERT INTO {table} ({columns}) VALUES ({values}) ON CONFLICT ({key}) {conflict}'), row)

    # Refuse invite-code collisions rather than attaching fixtures to an existing household.
    for i, (name, code) in enumerate(HOUSEHOLDS):
        home = fixture_id(f'home:{i}')
        existing = connection.execute(text('SELECT id FROM households WHERE invite_code=:code'), {'code': code}).scalar()
        if existing and str(existing) != home:
            raise ValueError(f'Demo invite code {code} is already in use; no data was changed')
        existing_owner = connection.execute(text('SELECT created_by FROM households WHERE id=:id'), {'id': home}).scalar()
        owner = user_ids[0 if i == 0 else 3]
        if existing_owner and str(existing_owner) != owner:
            raise ValueError('Demo household already uses a different owner; use the original user mapping')
        insert('households', dict(id=home, name=name, invite_code=code, created_by=owner))
        for j in (range(3) if i == 0 else (3,)):
            insert('household_members', dict(household_id=home, user_id=user_ids[j],
                    role='owner' if j in (0, 3) else 'member'), key='household_id, user_id')
        for zone, label in [('fridge','Fridge'), ('freezer','Freezer'), ('pantry','Pantry'), ('spicerack','Spice Rack')]:
            insert('storage_locations', dict(id=fixture_id(f'zone:{i}:{zone}'), household_id=home, name=label, zone=zone))
    for i, (name, category, unit, _) in enumerate(FOODS):
        insert('foods', dict(id=fixture_id(f'food:{i}'), name=name, category=category, default_unit=unit))
    if reset:
        statement = text('DELETE FROM inventory_items WHERE id IN :ids').bindparams(bindparam('ids', expanding=True))
        connection.execute(statement, {'ids': [fixture_id(f'item:{i}') for i in range(MAX_ITEMS)]})
    for i in range(items):
        food = i % len(FOODS)
        home_index = i % 2
        _, _, unit, zone = FOODS[food]
        # Each household gets all four zones and multiple expiry states.
        status = 'consumed' if i % 13 == 11 else 'discarded' if i % 13 == 12 else 'active'
        insert('inventory_items', dict(id=fixture_id(f'item:{i}'), household_id=fixture_id(f'home:{home_index}'),
            food_id=fixture_id(f'food:{food}'), storage_location_id=fixture_id(f'zone:{home_index}:{zone}'),
            quantity=1 + i % 3, unit=unit, purchase_date=today - timedelta(days=7),
            expiry_date=today + timedelta(days=(-5, 0, 2, 7, 30)[(i // 2) % 5]), status=status))
    for i, (name, ingredients) in enumerate(RECIPES):
        home = fixture_id(f'home:{i % 2}')
        recipe = fixture_id(f'recipe:{i}')
        insert('recipes', dict(id=recipe, household_id=home, name=name,
            description='Demo recipe for interface testing', instructions='Prepare ingredients and combine. Demo fixture only.',
            servings=2, prep_time_minutes=10, cook_time_minutes=15))
        for food in ingredients:
            insert('recipe_ingredients', dict(id=fixture_id(f'ingredient:{i}:{food}'), household_id=home,
                recipe_id=recipe, food_id=fixture_id(f'food:{food}'), quantity=1, unit=FOODS[food][2], optional=False))
    return {'households': 2, 'identity_references': 4, 'requested_inventory_items': items, 'recipes': len(RECIPES)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reset', action='store_true', help='Replace demo inventory and refresh fixture values; preserve other rows')
    parser.add_argument('--items', type=int, default=50)
    parser.add_argument('--user-ids', nargs=4, metavar='UUID', help='Four existing Supabase TEST-account UUIDs; no accounts are created')
    args = parser.parse_args()
    engine = None
    try:
        url = validate_target(os.getenv('SEED_DATABASE_URL'))
        engine = create_engine(url, connect_args={'connect_timeout': 5})
        with engine.begin() as connection:
            result = seed(connection, items=args.items, reset=args.reset, user_ids=args.user_ids)
        print('Demo fixtures ready:', result)
        print('Invite codes: DEMO01, STUD02. UUID fixtures are not login accounts.')
    except (ValueError, SQLAlchemyError):
        parser.exit(1, 'Seeding refused or failed. Check the local _demo/_test target, initialized schema, UUID mapping and fixture collisions. Transaction rolled back.\n')
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == '__main__':
    main()
