"""Real signed JWTs and real dependencies; no network or production credentials."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID
import jwt
import pytest
from pydantic import SecretStr
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core.dependencies import get_current_user, get_current_household
from app.models.household_member import HouseholdMember
from app.models.user import User

UID = "10000000-0000-0000-0000-000000000001"
OTHER = "10000000-0000-0000-0000-000000000002"
HOME = "00000000-0000-0000-0000-000000000001"
OTHER_HOME = "00000000-0000-0000-0000-000000000002"
SECRET = "test-secret-with-at-least-32-bytes"


def claims(**changes):
    now = int(datetime.now(timezone.utc).timestamp())
    return {"sub": UID, "email": "alice@example.com", "iat": now, "exp": now + 300,
            "iss": "https://test.supabase.co/auth/v1", "aud": "authenticated",
            "role": "authenticated", **changes}


def token(payload=None, key=SECRET, algorithm="HS256"):
    return jwt.encode(claims() if payload is None else payload, key, algorithm=algorithm)


def headers(value=None, household=HOME):
    result = {"Authorization": "Bearer " + (token() if value is None else value)}
    if household is not None:
        result["X-Household-ID"] = household
    return result


@pytest.fixture
def secured_client(client, db, monkeypatch):
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_household)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", SecretStr(SECRET))
    monkeypatch.setattr(settings, "SUPABASE_JWT_ALGORITHM", "HS256")
    db.add_all([HouseholdMember(household_id=HOME, user_id=UID, role="member"),
                HouseholdMember(household_id=OTHER_HOME, user_id=OTHER, role="owner")])
    db.commit()
    return client


@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/users/me"), ("post", "/api/v1/users/register"),
    ("get", "/api/v1/inventory/"), ("post", "/api/v1/inventory/"),
    ("delete", "/api/v1/inventory/1"), ("get", "/api/v1/recipes/"),
    ("post", "/api/v1/scan/"), ("post", "/api/v1/scan/sample"),
    ("post", "/api/v1/food/predict-expiry/1"),
])
@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer garbage"])
def test_every_data_route_requires_valid_token(secured_client, method, path, authorization):
    request_headers = {} if authorization is None else {"Authorization": authorization}
    response = getattr(secured_client, method)(path, headers=request_headers)
    assert response.status_code == 401, response.text
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"type": "about:blank", "title": "Unauthorized", "status": 401,
                               "detail": response.json()["detail"], "instance": path}


@pytest.mark.parametrize("change", [
    {"exp": 1}, {"iat": 4102444800}, {"nbf": 4102444800},
    {"iss": "https://other.supabase.co/auth/v1"}, {"aud": "wrong"},
    {"sub": "not-a-uuid"}, {"sub": 123}, {"role": "service_role"},
    {"role": "anon"}, {"email": "invalid"},
])
def test_invalid_claims(secured_client, change):
    response = secured_client.get("/api/v1/users/me", headers=headers(token(claims(**change))))
    assert response.status_code == 401


@pytest.mark.parametrize("field", ["sub", "exp", "iat", "iss", "aud", "role"])
def test_required_claims(secured_client, field):
    payload = claims(); payload.pop(field)
    assert secured_client.get("/api/v1/users/me", headers=headers(token(payload))).status_code == 401


def test_bad_signature_and_algorithm(secured_client):
    for value in [token(key="another-secret-with-at-least-32-bytes"),
                  token(key="test-key-" * 8, algorithm="HS384"), token(key="", algorithm="none")]:
        assert secured_client.get("/api/v1/users/me", headers=headers(value)).status_code == 401


def test_verified_profile_does_not_require_legacy_registration(secured_client, db):
    assert db.get(User, UID) is None
    response = secured_client.get("/api/v1/users/me", headers=headers())
    assert response.json() == {"id": UID, "email": "alice@example.com"}
    assert db.get(User, UID) is None
    assert secured_client.get("/api/v1/users/me", headers=headers(token(claims(email=None)))).json()["email"] is None


@pytest.mark.parametrize("household,status", [(None,400), ("bad",400), (OTHER_HOME,403)])
def test_household_header_and_membership(secured_client, household, status):
    response = secured_client.get("/api/v1/inventory/", headers=headers(household=household))
    assert response.status_code == status
    assert response.json()["status"] == status
    assert response.headers["content-type"] == "application/problem+json"


def test_own_membership_and_revocation(secured_client, db):
    assert secured_client.get("/api/v1/inventory/", headers=headers()).json() == []
    assert secured_client.get("/api/v1/inventory/", headers=headers(token(claims(sub=OTHER)))).status_code == 403
    db.query(HouseholdMember).filter_by(user_id=UID).delete(); db.commit()
    assert secured_client.get("/api/v1/inventory/", headers=headers()).status_code == 403


def test_sample_cannot_target_another_user(secured_client, monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_SAMPLE_SCAN", True)
    response = secured_client.post("/api/v1/scan/sample", headers=headers(), json={
        "sample_name": "test.jpeg", "mode": "receipt", "persist_to_db": True, "user_id": OTHER})
    assert response.status_code == 403


def test_missing_configuration_is_unavailable(secured_client, monkeypatch):
    monkeypatch.setattr(settings, "SUPABASE_JWT_SECRET", None)
    assert secured_client.get("/api/v1/users/me", headers=headers()).status_code == 503
    monkeypatch.setattr(settings, "SUPABASE_URL", None)
    assert secured_client.get("/api/v1/users/me", headers=headers()).status_code == 503


@pytest.mark.parametrize("algorithm", ["RS256", "ES256"])
def test_asymmetric_signature_verification(secured_client, monkeypatch, algorithm):
    from cryptography.hazmat.primitives.asymmetric import rsa, ec
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048) if algorithm == "RS256" else ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(settings, "SUPABASE_JWT_ALGORITHM", algorithm)
    monkeypatch.setattr("app.core.security.jwks_client", lambda issuer: SimpleNamespace(
        get_signing_key_from_jwt=lambda value: SimpleNamespace(key=key.public_key())))
    signed = token(key=key, algorithm=algorithm)
    assert secured_client.get("/api/v1/users/me", headers=headers(signed)).status_code == 200
    assert secured_client.get("/api/v1/users/me", headers=headers()).status_code == 401


def test_jwks_outage_fails_closed(secured_client, monkeypatch):
    from jwt.exceptions import PyJWKClientConnectionError
    from cryptography.hazmat.primitives.asymmetric import ec
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(settings, "SUPABASE_JWT_ALGORITHM", "ES256")
    def unavailable(issuer):
        raise PyJWKClientConnectionError("unavailable")
    monkeypatch.setattr("app.core.security.jwks_client", unavailable)
    response = secured_client.get("/api/v1/users/me", headers=headers(token(key=key, algorithm="ES256")))
    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"


def test_real_token_registration_and_legacy_inventory(secured_client, db):
    auth = headers(token(claims(email="new@example.com")))
    for _ in range(2):
        response = secured_client.post("/api/v1/users/register", headers=auth)
        assert response.status_code == 201, response.text
        assert response.json() == {"id": UID, "email": "new@example.com"}
    response = secured_client.post("/api/v1/inventory/", headers=auth, json={"food_id": 1})
    assert response.status_code == 201, response.text
    item = response.json()
    assert item["user_id"] == UID
    assert secured_client.get("/api/v1/inventory/", headers=auth).json() == [item]
    assert secured_client.delete(f"/api/v1/inventory/{item['id']}", headers=auth).status_code == 204
