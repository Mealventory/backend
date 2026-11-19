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


def _override_database(engine):
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database


def test_deep_readiness_healthy_reports_latency_and_pool_stats(monkeypatch):
    import httpx
    from datetime import datetime
    from sqlalchemy.pool import QueuePool
    from app.api.v1 import health as health_module

    engine = create_engine(
        "sqlite://", poolclass=QueuePool, pool_size=3, max_overflow=0,
        connect_args={"check_same_thread": False},
    )
    _override_database(engine)
    monkeypatch.setattr(health_module.settings, "AI_SERVICE_URL", "http://ai.internal:8001/")
    calls = []

    def fake_ai_get(url, *, timeout, follow_redirects):
        calls.append((url, timeout, follow_redirects))
        return httpx.Response(200, json={"status": "ready", "checks": {"vision": "configured"}})

    monkeypatch.setattr(health_module.httpx, "get", fake_ai_get)
    try:
        with engine.connect():
            with TestClient(app) as client:
                response = client.get("/api/v1/health/ready")
                assert response.status_code == 200, response.text
                assert response.headers["content-type"] == "application/json"
                body = response.json()
                assert body["status"] == "healthy"
                assert body["components"]["database"]["status"] == "healthy"
                assert body["components"]["database"]["pool_size"] == 3
                assert body["components"]["database"]["checked_out"] >= 1
                assert body["components"]["database"]["latency_ms"] >= 0
                assert body["components"]["ai_service"] == {
                    "status": "ready", "http_status": 200,
                }
                assert datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00")).tzinfo
                assert calls == [("http://ai.internal:8001/ready", 2.0, False)]
                assert "ai.internal" not in response.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_deep_readiness_database_failure_503_does_not_leak_credentials(monkeypatch):
    import httpx
    from app.api.v1 import health as health_module

    class FailedDatabase:
        def execute(self, statement):
            raise OperationalError(
                "SELECT 1", {}, Exception("postgresql://username:secret-password@private-host/database")
            )

    app.dependency_overrides[get_db] = lambda: FailedDatabase()
    monkeypatch.setattr(
        health_module.httpx, "get",
        lambda *args, **kwargs: httpx.Response(200, json={"status": "ready"}),
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["components"]["database"] == {
            "status": "unavailable",
            "latency_ms": None,
            "pool_size": None,
            "checked_out": None,
        }
        assert body["components"]["ai_service"]["status"] == "ready"
        assert "secret-password" not in response.text
        assert "private-host" not in response.text
        assert "username" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_deep_readiness_ai_service_503_preserves_safe_component_breakdown(monkeypatch):
    import httpx
    from app.api.v1 import health as health_module

    engine = create_engine("sqlite://")
    _override_database(engine)
    monkeypatch.setattr(
        health_module.httpx, "get",
        lambda *args, **kwargs: httpx.Response(
            503, json={"status": "degraded", "error": "secret-upstream-dsn"}
        ),
    )
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health/ready")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        assert body["components"]["database"]["status"] == "healthy"
        assert body["components"]["ai_service"] == {"status": "degraded", "http_status": 503}
        assert "secret-upstream-dsn" not in response.text
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_deep_readiness_ai_timeout_and_invalid_200_are_503(monkeypatch):
    import httpx
    from app.api.v1 import health as health_module

    engine = create_engine("sqlite://")
    _override_database(engine)

    def fail(*args, **kwargs):
        raise httpx.ReadTimeout("secret request token from internal host")

    try:
        with TestClient(app) as client:
            for simulated in (fail, lambda *args, **kwargs: httpx.Response(200, text="unready")):
                monkeypatch.setattr(health_module.httpx, "get", simulated)
                response = client.get("/api/v1/health/ready")
                assert response.status_code == 503
                body = response.json()
                assert body["status"] == "degraded"
                assert body["components"]["ai_service"]["status"] == "unavailable"
                assert "secret request token" not in response.text
                assert "internal host" not in response.text
            # The original inexpensive liveness endpoint is independent of AI.
            assert client.get("/api/v1/health").json() == {
                "status": "healthy", "database": "available",
            }
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_deep_readiness_openapi_exposes_structured_503():
    with TestClient(app) as client:
        path = client.get("/openapi.json").json()["paths"]["/api/v1/health/ready"]["get"]
    assert "200" in path["responses"]
    assert "503" in path["responses"]
    assert "ReadinessOut" in str(path["responses"]["503"])
