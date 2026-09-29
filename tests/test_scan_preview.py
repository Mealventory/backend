import pytest
from app.services import scan_service
from app.models.inventory import InventoryItem

@pytest.mark.parametrize('mode,detection,expected', [
    ('food', {'items': ['yogurt'], 'type': 'food'}, [('yogurt', 1, None)]),
    ('receipt', {'items': ['milk', 'milk', 'bread'], 'type': 'receipt', 'expiry_dates': ['2027-01-25']}, [('milk', 2, None), ('bread', 1, None)]),
    ('tag', {'items': [], 'type': 'tag', 'expiry_dates': ['2027 JA 25']}, [('', 1, '2027-01-25')]),
])
def test_preview_returns_candidates_without_saving(client, db, monkeypatch, mode, detection, expected):
    async def detect(content, requested):
        assert content == b'image-bytes'
        assert requested == mode
        return detection
    monkeypatch.setattr(scan_service, 'detect_food', detect)
    response = client.post('/api/v1/scan/preview', data={'mode': mode}, files={'file': ('scan.jpg', b'image-bytes', 'image/jpeg')})
    assert response.status_code == 200, response.text
    assert [(i['name'], i['quantity'], i['expiry_date']) for i in response.json()['items']] == expected
    assert db.query(InventoryItem).count() == 0

@pytest.mark.parametrize('detection', [{'items': [], 'type': 'unknown'}, {'items': ['milk'], 'type': 'mismatch'}])
def test_preview_rejects_empty_or_mismatched_detection(client, monkeypatch, detection):
    async def detect(*args): return detection
    monkeypatch.setattr(scan_service, 'detect_food', detect)
    assert client.post('/api/v1/scan/preview', data={'mode': 'food'}, files={'file': ('scan.jpg', b'photo', 'image/jpeg')}).status_code == 422
