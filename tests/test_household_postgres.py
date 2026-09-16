"""Disposable PostgreSQL 16 on an ephemeral loopback port; never DATABASE_URL."""
import secrets
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from app.services import household_service as service
from app.core.auth_errors import AuthProblem
from tests.test_init_db_postgres import docker, pytestmark

A='10000000-0000-0000-0000-000000000001'
B='10000000-0000-0000-0000-000000000002'
ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def postgres_engine():
    name='mealventory-household-test-'+uuid.uuid4().hex[:12]
    password=secrets.token_hex(24)
    result=docker('run','--detach','--rm','--name',name,'--publish','127.0.0.1::5432',
                 '-e','POSTGRES_PASSWORD='+password,'postgres:16')
    assert result.returncode==0,result.stderr
    engine=None
    try:
        for _ in range(60):
            if docker('exec',name,'pg_isready','-U','postgres').returncode==0:
                break
            time.sleep(.5)
        else:
            pytest.fail('PostgreSQL startup timed out')
        result=docker('port',name,'5432/tcp')
        assert result.returncode==0,result.stderr
        port=int(result.stdout.strip().rsplit(':',1)[1])
        engine=create_engine(URL.create('postgresql+psycopg2',username='postgres',password=password,
                                       host='127.0.0.1',port=port,database='postgres'))
        with engine.begin() as connection:
            connection.exec_driver_sql((ROOT/'scripts/init_db.sql').read_text())
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        assert docker('stop',name).returncode==0


def test_postgres_create_join_and_roles(postgres_engine):
    with Session(postgres_engine) as db:
        household=service.create_household(db,A,'Postgres family')
        hid=str(household.id)
        assert household.role=='owner'
        assert service.join_household(db,B,household.invite_code).role=='member'
        assert service.join_household(db,B,household.invite_code).role=='member'
        assert any(h.id==household.id for h in service.list_households(db,B))
        assert service.update_role(db,hid,A,B,'admin').role=='admin'
        service.remove_member(db,hid,A,B)
        with pytest.raises(AuthProblem) as error:
            service.remove_member(db,hid,A,A)
        assert error.value.status_code==409


def test_postgres_unique_code_retry(postgres_engine,monkeypatch):
    with Session(postgres_engine) as db:
        monkeypatch.setattr(service,'generate_invite_code',lambda:'PG0001')
        service.create_household(db,A,'First')
        values=iter(['PG0001','PG0002'])
        monkeypatch.setattr(service,'generate_invite_code',lambda:next(values))
        assert service.create_household(db,A,'Second').invite_code=='PG0002'


def test_concurrent_owner_demotions_preserve_one_owner(postgres_engine):
    with Session(postgres_engine) as db:
        hh=service.create_household(db,A,'Concurrent owners');hid=str(hh.id)
        service.join_household(db,B,hh.invite_code)
        service.update_role(db,hid,A,B,'owner')
    def demote(user):
        with Session(postgres_engine) as db:
            try:
                service.update_role(db,hid,user,user,'member')
                return 200
            except AuthProblem as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(demote,[A,B]))==[200,409]
    with postgres_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM household_members WHERE household_id=:hid AND role='owner'"),{'hid':hid}).scalar()==1


def test_concurrent_join_is_idempotent(postgres_engine):
    with Session(postgres_engine) as db:
        hh=service.create_household(db,A,'Concurrent joins');hid=str(hh.id)
    def join(_):
        with Session(postgres_engine) as db:
            return service.join_household(db,B,hh.invite_code).role
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(join,range(2)))==['member','member']
    with postgres_engine.connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM household_members WHERE household_id=:hid AND user_id=:uid'),{'hid':hid,'uid':B}).scalar()==1
