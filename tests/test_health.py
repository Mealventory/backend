from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from app.main import app
from app.dependencies.database import get_db


def test_health_checks_database_without_auth():
    engine = create_engine('sqlite://')
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    try:
        with TestClient(app) as client:
            response = client.get('/api/v1/health')
            assert response.status_code == 200
            assert response.json() == {'status': 'healthy', 'database': 'available'}
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_database_failure_is_503_without_connection_details():
    class FailedDatabase:
        def execute(self, statement):
            raise OperationalError('SELECT 1', {}, Exception('password=do-not-expose host=private'))
    app.dependency_overrides[get_db] = lambda: FailedDatabase()
    try:
        with TestClient(app) as client:
            response = client.get('/api/v1/health')
            assert response.status_code == 503
            assert response.headers['content-type'] == 'application/problem+json'
            assert response.json() == {
                'type': 'about:blank',
                'title': 'Service Unavailable',
                'status': 503,
                'detail': 'Database unavailable',
                'instance': '/api/v1/health',
            }
            assert 'do-not-expose' not in response.text
            assert client.get('/').json() == {'status': 'API running'}
    finally:
        app.dependency_overrides.clear()
