"""Opt-in real PostgreSQL 16 tests; never uses DATABASE_URL or a live database.

RUN_POSTGRES_TESTS=1 python -m pytest tests/test_init_db_postgres.py -v
Requires Docker and postgres:16 (downloaded by Docker if absent).
"""
import os
from pathlib import Path
import subprocess
import time
import uuid
import pytest

pytestmark = pytest.mark.skipif(os.getenv('RUN_POSTGRES_TESTS') != '1',
                                reason='Set RUN_POSTGRES_TESTS=1 to run isolated Docker PostgreSQL 16 tests')
MIGRATION = Path(__file__).resolve().parents[1] / 'scripts/init_db.sql'
TABLES = ['households', 'household_members', 'storage_locations', 'foods',
          'inventory_items', 'recipes', 'recipe_ingredients', 'shopping_list_items', 'device_push_tokens']


def docker(*args, input=None):
    return subprocess.run(['docker', *args], input=input, text=True, capture_output=True, timeout=180)


@pytest.fixture(scope='module')
def container():
    name='mealventory-schema-test-'+uuid.uuid4().hex[:12]
    result=docker('run','--detach','--rm','--network','none','--name',name,
                  '--label','purpose=mealventory-schema-test','-e','POSTGRES_HOST_AUTH_METHOD=trust','postgres:16')
    assert result.returncode==0, result.stderr
    try:
        for _ in range(60):
            if docker('exec',name,'pg_isready','-U','postgres').returncode==0:
                break
            time.sleep(0.5)
        else:
            pytest.fail('PostgreSQL did not become ready')
        yield name
    finally:
        result=docker('stop',name)
        assert result.returncode==0, result.stderr


@pytest.fixture
def database(container):
    name='schema_'+uuid.uuid4().hex
    result=docker('exec',container,'createdb','-U','postgres',name)
    assert result.returncode==0,result.stderr
    def execute(sql, *, ok=True):
        result=docker('exec','-i',container,'psql','-X','-qAt','-v','ON_ERROR_STOP=1',
                      '-U','postgres','-d',name,input=sql)
        if ok:
            assert result.returncode==0,result.stderr
        else:
            assert result.returncode!=0,'Expected SQL rejection'
        return result
    yield execute
    result=docker('exec',container,'dropdb','-U','postgres',name)
    assert result.returncode==0,result.stderr


@pytest.fixture
def schema(database):
    database(MIGRATION.read_text())
    return database


SEED = """
INSERT INTO households (id,name,created_by,invite_code) VALUES
 ('00000000-0000-0000-0000-000000000001','A','10000000-0000-0000-0000-000000000001','ABC123'),
 ('00000000-0000-0000-0000-000000000002','B','10000000-0000-0000-0000-000000000002','DEF456');
INSERT INTO household_members (household_id,user_id,role)
 SELECT id,created_by,'owner' FROM households;
INSERT INTO storage_locations (id,household_id,name,zone) VALUES
 ('20000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001','Fridge','fridge');
INSERT INTO foods (id,name,avg_shelf_life_days) VALUES
 ('30000000-0000-0000-0000-000000000001','Milk',7);
INSERT INTO inventory_items (household_id,food_id,storage_location_id)
 VALUES ('00000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001','20000000-0000-0000-0000-000000000001');
INSERT INTO recipes (id,household_id,name) VALUES
 ('40000000-0000-0000-0000-000000000001','00000000-0000-0000-0000-000000000001','Milk drink');
INSERT INTO recipe_ingredients (household_id,recipe_id,food_id,quantity)
 VALUES ('00000000-0000-0000-0000-000000000001','40000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',1);
INSERT INTO shopping_list_items (household_id,name)
 VALUES ('00000000-0000-0000-0000-000000000001','Bread');
INSERT INTO device_push_tokens (user_id,token,platform)
 VALUES ('10000000-0000-0000-0000-000000000001','test-token','ios');
"""


def test_creates_all_tables_enums_and_required_indices(schema):
    assert schema('SHOW server_version_num').stdout.strip().startswith('16')
    tables=schema("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").stdout.splitlines()
    assert tables==sorted(TABLES)
    assert schema("SELECT count(*) FROM pg_type WHERE typnamespace='public'::regnamespace AND typtype='e'").stdout.strip()=='3'
    for index,columns in [('idx_inventory_tenant','(household_id, status, expiry_date)'),
                          ('idx_household_members','(user_id, household_id)')]:
        assert columns in schema(f"SELECT indexdef FROM pg_indexes WHERE indexname='{index}'").stdout
    assert schema("SELECT count(*) FROM pg_constraint WHERE connamespace='public'::regnamespace AND contype='p'").stdout.strip()=='9'


def test_defaults_and_full_relational_graph(schema):
    schema(SEED)
    assert schema('SELECT status,quantity,unit FROM inventory_items').stdout.strip()=='active|1.000|units'
    assert schema("SELECT count(*) FROM households WHERE created_at IS NOT NULL AND updated_at IS NOT NULL").stdout.strip()=='2'
    assert schema("INSERT INTO foods(name) VALUES ('Eggs') RETURNING id IS NOT NULL").stdout.strip()=='t'


def test_all_mutable_tables_update_timestamp(schema):
    schema(SEED)
    for table in TABLES:
        result=schema(f"UPDATE {table} SET updated_at='2000-01-01'; SELECT count(*) FROM {table} WHERE updated_at <= '2000-01-01';")
        assert result.stdout.strip()=='0',table
        assert schema(f"SELECT count(*) FROM pg_trigger WHERE tgrelid='public.{table}'::regclass AND NOT tgisinternal").stdout.strip()=='1'


@pytest.mark.parametrize('table,assignment',[
 ('inventory_items',"household_id='00000000-0000-0000-0000-000000000002'"),
 ('recipe_ingredients',"household_id='00000000-0000-0000-0000-000000000002'"),
 ('inventory_items',"food_id='99999999-0000-0000-0000-000000000000'"),
])
def test_foreign_keys_reject_invalid_links(schema,table,assignment):
    schema(SEED)
    assert 'foreign key constraint' in schema(f'UPDATE {table} SET {assignment}',ok=False).stderr


@pytest.mark.parametrize('statement',[
 "UPDATE inventory_items SET quantity=-1",
 "UPDATE inventory_items SET quantity='NaN'",
 "UPDATE shopping_list_items SET quantity=0",
 "UPDATE recipe_ingredients SET quantity=-1",
 "UPDATE households SET invite_code='bad'",
 "UPDATE foods SET avg_shelf_life_days=-1",
 "UPDATE recipes SET servings=0",
 "UPDATE storage_locations SET zone='unknown'",
 "UPDATE device_push_tokens SET platform='unknown'",
 "INSERT INTO household_members SELECT * FROM household_members",
 "INSERT INTO device_push_tokens(user_id,token,platform) SELECT user_id,token,platform FROM device_push_tokens",
])
def test_invalid_values_and_duplicates_are_rejected(schema,statement):
    schema(SEED)
    schema(statement,ok=False)


def test_delete_behaviour(schema):
    schema(SEED)
    schema('DELETE FROM foods',ok=False)
    schema('DELETE FROM storage_locations',ok=False)
    schema("DELETE FROM households WHERE name='A'")
    for table in ['inventory_items','recipes','recipe_ingredients','shopping_list_items','storage_locations']:
        assert schema(f'SELECT count(*) FROM {table}').stdout.strip()=='0'
    assert schema('SELECT count(*) FROM foods').stdout.strip()=='1'
    assert schema('SELECT count(*) FROM device_push_tokens').stdout.strip()=='1'
    assert schema('SELECT count(*) FROM household_members').stdout.strip()=='1'


def test_rerun_fails_without_destroying_data(schema):
    schema(SEED)
    schema(MIGRATION.read_text(),ok=False)
    assert schema('SELECT count(*) FROM households').stdout.strip()=='2'
    assert schema("SELECT count(*) FROM pg_tables WHERE schemaname='public'").stdout.strip()=='9'


def test_mid_migration_failure_rolls_back(database):
    database('CREATE TABLE public.foods (original integer); INSERT INTO public.foods VALUES (42)')
    database(MIGRATION.read_text(),ok=False)
    assert database('SELECT original FROM foods').stdout.strip()=='42'
    assert database("SELECT count(*) FROM pg_tables WHERE schemaname='public'").stdout.strip()=='1'
    assert database("SELECT count(*) FROM pg_type WHERE typnamespace='public'::regnamespace AND typtype='e'").stdout.strip()=='0'
    assert database("SELECT count(*) FROM pg_proc WHERE pronamespace='public'::regnamespace AND proname='update_updated_at_column'").stdout.strip()=='0'
