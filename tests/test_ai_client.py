import asyncio
import time
import httpx
import pytest
from app.services import ai_client as ai
from tests.test_household_inventory import inventory_api, HOME


@pytest.fixture(autouse=True)
def fresh_breaker(monkeypatch):
    monkeypatch.setattr(ai, 'breaker', ai.CircuitBreaker())


def mock_transport(monkeypatch, handler):
    factory = httpx.AsyncClient
    monkeypatch.setattr(ai.httpx, 'AsyncClient', lambda **kwargs: factory(transport=httpx.MockTransport(handler), **kwargs))


def test_success_preserves_multipart_and_response(monkeypatch):
    def handle(request):
        assert request.url.path == '/scan/'
        assert b'image-bytes' in request.content and b'receipt' in request.content
        return httpx.Response(200, json={'type': 'receipt', 'items': ['milk'], 'extra': 1})
    mock_transport(monkeypatch, handle)
    assert asyncio.run(ai.detect_food(b'image-bytes', 'receipt'))['extra'] == 1


def test_retry_then_success(monkeypatch):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 1 else 200, json={'items': []})
    mock_transport(monkeypatch, handle)
    assert asyncio.run(ai.detect_food(b'x')) == {'items': []}
    assert len(calls) == 2 and ai.breaker.failures == 0


@pytest.mark.parametrize('kind,status,attempts', [('timeout',504,1), ('connect',503,2), ('503',503,2),
                                               ('400',503,1), ('json',503,1), ('shape',503,1)])
def test_failures_are_safe_and_bounded(monkeypatch, kind, status, attempts):
    calls = []
    def handle(request):
        calls.append(request)
        if kind == 'timeout':
            raise httpx.ReadTimeout('secret upstream error')
        if kind == 'connect':
            raise httpx.ConnectError('secret upstream error')
        if kind == 'json':
            return httpx.Response(200, text='secret invalid json')
        if kind == 'shape':
            return httpx.Response(200, json={'items': [3]})
        return httpx.Response(int(kind), text='secret upstream error')
    mock_transport(monkeypatch, handle)
    with pytest.raises(ai.AIServiceUnavailable) as error:
        asyncio.run(ai.detect_food(b'x'))
    assert error.value.status_code == status
    assert error.value.detail['code'] == 'AI_SERVICE_UNAVAILABLE'
    assert 'secret' not in str(error.value.detail)
    assert len(calls) == attempts


def test_total_deadline_cancels_slow_upstream(monkeypatch):
    monkeypatch.setattr(ai.settings, 'AI_REQUEST_TIMEOUT_SECONDS', 0.03)
    async def handle(request):
        await asyncio.sleep(10)
    mock_transport(monkeypatch, handle)
    start = time.monotonic()
    with pytest.raises(ai.AIServiceUnavailable) as error:
        asyncio.run(ai.detect_food(b'x'))
    assert error.value.status_code == 504
    assert time.monotonic() - start < 1


def test_breaker_opens_then_allows_only_one_recovery_probe(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(ai.time, 'monotonic', lambda: clock[0])
    circuit = ai.CircuitBreaker()
    stale = circuit.acquire()
    for _ in range(3):
        circuit.finish(circuit.acquire(), True)
    circuit.finish(stale, False)
    with pytest.raises(ai.AIServiceUnavailable):
        circuit.acquire()
    clock[0] += 31
    probe = circuit.acquire()
    with pytest.raises(ai.AIServiceUnavailable):
        circuit.acquire()
    circuit.finish(probe, True)
    with pytest.raises(ai.AIServiceUnavailable):
        circuit.acquire()
    clock[0] += 31
    circuit.finish(circuit.acquire(), False)
    assert circuit.acquire()[1] is False


def test_cancelled_probe_releases_circuit(monkeypatch):
    ai.breaker.opened_at = time.monotonic() - 31
    async def cancel(*args):
        raise asyncio.CancelledError()
    monkeypatch.setattr(ai, '_request', cancel)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ai.detect_food(b'x'))
    assert not ai.breaker.probing


def test_scan_api_timeout_has_manual_entry_and_no_database_write(inventory_api, monkeypatch):
    client, _, engine = inventory_api
    def handle(request):
        raise httpx.ReadTimeout('private-host-password')
    mock_transport(monkeypatch, handle)
    response = client.post('/api/v1/scan/', headers={'X-Household-ID': HOME}, data={'mode': 'food'},
                           files={'file': ('food.jpg', b'image', 'image/jpeg')})
    assert response.status_code == 504, response.text
    assert response.headers['content-type'] == 'application/problem+json'
    assert response.json()['action'] == 'manual_entry'
    assert response.json()['code'] == 'AI_SERVICE_UNAVAILABLE'
    from sqlalchemy import text
    with engine.connect() as db:
        assert db.execute(text('SELECT count(*) FROM inventory_items')).scalar() == 0


def test_retry_delay_shares_total_deadline(monkeypatch):
    monkeypatch.setattr(ai.settings, 'AI_REQUEST_TIMEOUT_SECONDS', 0.03)
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(503)
    mock_transport(monkeypatch, handle)
    with pytest.raises(ai.AIServiceUnavailable) as error:
        asyncio.run(ai.detect_food(b'x'))
    assert error.value.status_code == 504
    assert len(calls) == 1


def test_open_circuit_makes_no_network_request(monkeypatch):
    ai.breaker.opened_at = time.monotonic()
    def handle(request):
        pytest.fail('Open circuit must reject before sending an image')
    mock_transport(monkeypatch, handle)
    with pytest.raises(ai.AIServiceUnavailable) as error:
        asyncio.run(ai.detect_food(b'x'))
    assert error.value.status_code == 503
