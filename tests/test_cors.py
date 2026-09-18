"""Configuration validation and actual-app browser preflight behavior."""
import os
import subprocess
import sys
import pytest
from pydantic import ValidationError
from app.core.config import Settings


def settings(**kwargs):
    return Settings(_env_file=None, DATABASE_URL='sqlite://', AI_SERVICE_URL='http://ai', **kwargs)


def test_comma_separated_origins(monkeypatch):
    monkeypatch.setenv('CORS_ORIGINS', ' http://localhost:8082,https://APP.example.com/,http://localhost:8082 ')
    assert settings().CORS_ORIGINS == ['http://localhost:8082', 'https://app.example.com']
    monkeypatch.delenv('CORS_ORIGINS')
    assert settings().CORS_ORIGINS == ['*']
    assert settings(CORS_ORIGINS='').CORS_ORIGINS == []


@pytest.mark.parametrize('value', ['*,https://app.example.com', 'https://*.trycloudflare.com',
    'exp://example.com', 'https://example.com/path', 'https://user:password@example.com',
    'https://example.com?query=1', 'https://example.com#hash', 'example.com', 'https://example.com:bad'])
def test_invalid_origins(value):
    with pytest.raises(ValidationError):
        settings(CORS_ORIGINS=value)


@pytest.mark.parametrize('origins', ['*', 'http://localhost:8082,https://app.example.com', ''])
def test_actual_app_cors(origins):
    # Isolate environment/app import so other tests keep their existing app instance.
    code = '''
import os
from fastapi.testclient import TestClient
from app.main import app
with TestClient(app) as client:
    configured = os.environ['CORS_ORIGINS']
    allowed = bool(configured)
    origin = 'http://localhost:8082'
    response = client.options('/api/v1/items', headers={
        'Origin': origin, 'Access-Control-Request-Method': 'PATCH',
        'Access-Control-Request-Headers': 'authorization,content-type,x-household-id'})
    assert response.status_code == (200 if allowed else 400), response.text
    expected = '*' if configured == '*' else origin if allowed else None
    assert response.headers.get('access-control-allow-origin') == expected
    assert response.headers.get('access-control-allow-credentials') == (None if configured == '*' else 'true')
    foreign = client.options('/api/v1/items', headers={
        'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'GET'})
    assert foreign.status_code == (200 if configured == '*' else 400)
    if configured != '*':
        assert 'access-control-allow-origin' not in foreign.headers
        assert 'access-control-allow-origin' not in client.get('/', headers={'Origin': 'https://untrusted.example'}).headers
    # Native-style requests have no Origin; authentication still applies.
    assert client.get('/').status_code == 200
    assert client.get('/api/v1/items').status_code == 401
    assert client.get('/api/v1/items', headers={'Origin': origin}).status_code == 401
'''
    env = dict(os.environ, CORS_ORIGINS=origins, DATABASE_URL='sqlite://', AI_SERVICE_URL='http://ai')
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
