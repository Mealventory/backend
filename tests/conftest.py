"""Offline API fixtures: no production database, tokens, or paid AI requests."""
import os
os.environ.update(DATABASE_URL='sqlite://', AI_SERVICE_URL='http://127.0.0.1:8001',
                  FIREBASE_PROJECT_ID='mealventory-test')
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app
from app.db.base import Base
from app.models.user import User
from app.models.food import Food
from app.models.inventory import InventoryItem
from app.dependencies.database import get_db
from app.dependencies.auth import get_current_user


@pytest.fixture
def db():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as session:
        session.add_all([User(id='alice', email='alice@example.com'),
                         User(id='bob', email='bob@example.com'),
                         Food(id=1, name='chicken', avg_shelf_life_days=7)])
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr('app.main.get_firebase_app', lambda: None)
    def database():
        yield db
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: db.get(User, 'alice')
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
