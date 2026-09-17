"""Verify the unmodified PostgreSQL 16 DDL and commits across phone sessions."""
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services import household_service, shopping_service as shopping
from app.schemas.shopping import ShoppingItemCreate, ShoppingItemUpdate, ShoppingItemOut
from app.models.shopping import ShoppingListItem
from tests.test_household_postgres import postgres_engine, A, B
from tests.test_init_db_postgres import pytestmark


def test_shopping_ddl_persistence_and_trigger(postgres_engine):
    with Session(postgres_engine) as db:
        home = household_service.create_household(db, A, 'Shopping test')
        other = household_service.create_household(db, B, 'Other household')
        foreign = shopping.add_item(db, other.id, ShoppingItemCreate(name='Other rice'))
        shopping.update_item(db, other.id, foreign['id'], ShoppingItemUpdate(checked=True))
        food_id = db.execute(text("INSERT INTO foods(name,default_unit) VALUES ('Milk','bottles') RETURNING id")).scalar()
        item = shopping.add_item(db, home.id, ShoppingItemCreate(name='Milk', food_id=food_id, quantity='2.125'))
        ShoppingItemOut.model_validate(item)
        assert item['quantity'] == ShoppingItemCreate(name='x', quantity='2.125').quantity
        # ORM mapping uses the real UUID food link and is_checked column.
        assert db.get(ShoppingListItem, str(item['id'])).checked is False
    with Session(postgres_engine) as phone:
        assert len(shopping.list_items(phone, home.id)) == 1
        edited = shopping.update_item(phone, home.id, item['id'], ShoppingItemUpdate(checked=True, unit='bottles'))
        assert edited['updated_at'] > item['updated_at']
        assert edited['food_id'] == food_id
    with Session(postgres_engine) as phone:
        assert shopping.list_items(phone, home.id)[0]['checked'] is True
        assert shopping.clear_checked(phone, home.id) == {'deleted_count': 1}
    with Session(postgres_engine) as phone:
        assert shopping.list_items(phone, home.id) == []
        assert shopping.list_items(phone, other.id)[0]['id'] == foreign['id']
        row = shopping.add_item(phone, home.id, ShoppingItemCreate(name='Free text'))
        shopping.delete_item(phone, home.id, row['id'])
    with Session(postgres_engine) as phone:
        assert shopping.list_items(phone, home.id) == []
