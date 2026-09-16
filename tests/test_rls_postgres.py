"""Real-role RLS tests in isolated PostgreSQL; no live credentials."""
from pathlib import Path
import pytest
from tests.test_init_db_postgres import container, database, schema, SEED, pytestmark

A='10000000-0000-0000-0000-000000000001'
B='10000000-0000-0000-0000-000000000002'
H1='00000000-0000-0000-0000-000000000001'
H2='00000000-0000-0000-0000-000000000002'
RLS=(Path(__file__).resolve().parents[1]/'scripts/enable_rls.sql').read_text()
TENANT=['households','household_members','storage_locations','inventory_items','recipes','recipe_ingredients','shopping_list_items']
MUTABLE=TENANT[2:]

@pytest.fixture
def secured(schema):
    schema('''DO $$ BEGIN
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
      IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon NOLOGIN; END IF;
    END $$;
    CREATE SCHEMA auth;
    CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
      SELECT nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
    $$;
    GRANT USAGE ON SCHEMA auth, public TO authenticated, anon;
    GRANT EXECUTE ON FUNCTION auth.uid() TO authenticated, anon;
    ''')
    schema(SEED)
    # A full second household graph makes filtering assertions meaningful.
    schema(f"""
    INSERT INTO storage_locations(household_id,name,zone) VALUES ('{H2}','Other fridge','fridge');
    INSERT INTO inventory_items(household_id,food_id) SELECT '{H2}',id FROM foods;
    INSERT INTO recipes(household_id,name) VALUES ('{H2}','Other recipe');
    INSERT INTO recipe_ingredients(household_id,recipe_id,food_id,quantity)
      SELECT '{H2}',r.id,f.id,1 FROM recipes r CROSS JOIN foods f WHERE r.household_id='{H2}';
    INSERT INTO shopping_list_items(household_id,name) VALUES ('{H2}','Other bread');
    INSERT INTO device_push_tokens(user_id,token,platform) VALUES ('{B}','other-token','android');
    """)
    schema(RLS)
    return schema

def as_user(db, sql, user=A, ok=True, role='authenticated'):
    return db(f"BEGIN; SET LOCAL ROLE {role}; SET LOCAL request.jwt.claim.sub='{user}'; {sql}; COMMIT;",ok=ok)

@pytest.mark.parametrize('table',TENANT)
@pytest.mark.parametrize('user,household',[(A,H1),(B,H2)])
def test_only_own_household_visible_without_recursion(secured,table,user,household):
    col='id' if table=='households' else 'household_id'
    assert as_user(secured,f'SELECT {col} FROM {table}',user).stdout.strip()==household

@pytest.mark.parametrize('table',MUTABLE)
def test_cross_tenant_update_delete_and_move(secured,table):
    assert as_user(secured,f"UPDATE {table} SET updated_at=now() WHERE household_id='{H2}' RETURNING household_id").stdout.strip()==''
    assert as_user(secured,f"DELETE FROM {table} WHERE household_id='{H2}' RETURNING household_id").stdout.strip()==''
    err=as_user(secured,f"UPDATE {table} SET household_id='{H2}' WHERE household_id='{H1}'",ok=False)
    assert 'row-level security' in err.stderr
    assert as_user(secured,f"UPDATE {table} SET updated_at=now() WHERE household_id='{H1}' RETURNING household_id").stdout.strip()==H1

@pytest.mark.parametrize('table,columns,values',[
 ('storage_locations','name,zone',"'New','pantry'"),
 ('inventory_items','food_id',"'30000000-0000-0000-0000-000000000001'"),
 ('recipes','name',"'New'"),
 ('recipe_ingredients','recipe_id,food_id,quantity',"'40000000-0000-0000-0000-000000000001','30000000-0000-0000-0000-000000000001',1"),
 ('shopping_list_items','name',"'New'"),
])
def test_insert_checks_and_own_delete(secured,table,columns,values):
    assert 'row-level security' in as_user(secured,f"INSERT INTO {table}(household_id,{columns}) VALUES ('{H2}',{values})",ok=False).stderr
    # Remove existing own ingredients to avoid their recipe/food unique constraint.
    if table=='recipe_ingredients':
        as_user(secured,f"DELETE FROM {table} WHERE household_id='{H1}'")
    result=as_user(secured,f"INSERT INTO {table}(household_id,{columns}) VALUES ('{H1}',{values}) RETURNING id").stdout.strip()
    # New rows have no dependent children.
    assert as_user(secured,f"DELETE FROM {table} WHERE id='{result}' RETURNING id").stdout.strip()==result

@pytest.mark.parametrize('table',TENANT+['foods','device_push_tokens'])
def test_anonymous_denied_and_missing_identity_empty(secured,table):
    as_user(secured,f'SELECT * FROM {table}',role='anon',user='',ok=False)
    assert as_user(secured,f'SELECT count(*) FROM {table}',user='').stdout.strip()=='0'
    as_user(secured,f'TRUNCATE {table} CASCADE',ok=False)

def test_membership_escalation_and_household_controls(secured):
    for statement in [
        f"INSERT INTO household_members(household_id,user_id) VALUES ('{H2}','{A}')",
        "UPDATE household_members SET role='owner'",
        "DELETE FROM household_members",
        f"UPDATE households SET created_by='{A}'",
        f"INSERT INTO households(name,created_by) VALUES ('Mine','{A}')",
        'DELETE FROM households',
    ]:
        as_user(secured,statement,ok=False)
    assert as_user(secured,f"UPDATE households SET name='Allowed' WHERE id='{H1}' RETURNING name").stdout.strip()=='Allowed'
    assert as_user(secured,f"UPDATE households SET name='Blocked' WHERE id='{H2}' RETURNING name").stdout.strip()==''
    assert as_user(secured,f"SELECT mealventory_private.is_household_member('{B}','{H2}')").stdout.strip()=='f'
    secured(f"DELETE FROM household_members WHERE user_id='{A}'")
    assert as_user(secured,'SELECT count(*) FROM inventory_items').stdout.strip()=='0'

def test_device_ownership_and_global_catalogue(secured):
    assert as_user(secured,'SELECT token FROM device_push_tokens').stdout.strip()=='test-token'
    assert as_user(secured,'SELECT name FROM foods').stdout.strip()=='Milk'
    as_user(secured,"UPDATE foods SET name='Changed'",ok=False)
    as_user(secured,f"UPDATE device_push_tokens SET user_id='{B}'",ok=False)
    as_user(secured,f"INSERT INTO device_push_tokens(user_id,token,platform) VALUES ('{B}','stolen','ios')",ok=False)
    assert as_user(secured,f"DELETE FROM device_push_tokens WHERE user_id='{B}' RETURNING id").stdout.strip()==''
    as_user(secured,f"INSERT INTO device_push_tokens(user_id,token,platform) VALUES ('{A}','new','ios')")
    assert as_user(secured,"UPDATE device_push_tokens SET platform='web' WHERE token='new' RETURNING platform").stdout.strip()=='web'
    assert as_user(secured,"DELETE FROM device_push_tokens WHERE token='new' RETURNING token").stdout.strip()=='new'

def test_rls_configuration_and_transactional_rerun(secured):
    assert secured("SELECT count(*) FROM pg_class WHERE relnamespace='public'::regnamespace AND relkind='r' AND relrowsecurity").stdout.strip()=='9'
    assert secured("SELECT prosecdef AND 'search_path=\"\"'=ANY(proconfig) FROM pg_proc WHERE proname='is_household_member'").stdout.strip()=='t'
    secured(RLS,ok=False)
    assert as_user(secured,'SELECT count(*) FROM household_members').stdout.strip()=='1'
