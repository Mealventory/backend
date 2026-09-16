"""Opt-in persistence check against the actual DDL in disposable PostgreSQL 16."""
from sqlalchemy.orm import Session
from app.services import household_service
from app.services import household_inventory_service as inventory
from app.schemas.household_inventory import ItemCreate, ItemOut
from tests.test_household_postgres import postgres_engine, A
from tests.test_init_db_postgres import pytestmark


def test_inventory_commit_visible_between_sessions(postgres_engine):
    with Session(postgres_engine) as owner:
        home = household_service.create_household(owner, A, 'Inventory test')
        created = inventory.add_item(owner, home.id, ItemCreate(name='Rice', quantity='2.5', unit='kg'))
        ItemOut.model_validate(created)
    with Session(postgres_engine) as phone:
        assert len(inventory.list_items(phone, home.id)) == 1
        inventory.delete_item(phone, home.id, created['id'])
    with Session(postgres_engine) as other_phone:
        assert inventory.list_items(other_phone, home.id) == []
