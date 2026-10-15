from datetime import datetime, timezone
import json
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.data import load_parking
from app.parking import snapshot


def test_parking_contract():
    with TestClient(app) as client:
        assert client.get('/api/health').status_code == 200
        areas = client.get('/api/parking/areas').json()
        status = client.get('/api/parking/status').json()
        assert areas['is_example'] is False
        assert len(areas['features']) == 7
        assert status['mode'] == 'simulated'
        assert {f['properties']['id'] for f in areas['features']} == {s['id'] for s in status['items']}
        for item in status['items']:
            assert 0 <= item['occupied'] <= item['capacity']
            assert item['available'] + item['occupied'] == item['capacity']
            assert client.get(f"/api/parking/{item['id']}/status").status_code == 200
        assert client.get('/api/parking/missing/status').status_code == 404


def test_snapshot_repeatable_and_bounded():
    data = load_parking()
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert snapshot(data, when) == snapshot(data, when)
    for second in range(0, 900, 15):
        for item in snapshot(data, datetime.fromtimestamp(second, timezone.utc))['items']:
            assert 0 <= item['available'] <= item['capacity']


def test_modules_do_not_invent_routes():
    with TestClient(app) as client:
        assert client.get('/api/roads').json()['features'] == []
        assert client.get('/api/transit').json()['stops'] == []
        assert client.post('/api/routing/plan', json={'origin': {'longitude': 0, 'latitude': 0}, 'destination': {'longitude': 1, 'latitude': 1}}).status_code == 501
        assert client.post('/api/routing/plan', json={'origin': {'longitude': 181, 'latitude': 0}, 'destination': {'longitude': 1, 'latitude': 1}}).status_code == 422


@pytest.mark.parametrize('fault', ['duplicate', 'capacity', 'ring', 'range'])
def test_bad_geojson_rejected(tmp_path, monkeypatch, fault):
    data = load_parking()
    feature = data['features'][0]
    if fault == 'duplicate': data['features'].append(feature)
    if fault == 'capacity': feature['properties']['capacity'] = -1
    if fault == 'ring': feature['geometry']['coordinates'][0].pop()
    if fault == 'range': feature['geometry']['coordinates'][0][1] = [190, 0]
    path = tmp_path / 'bad.geojson'
    path.write_text(json.dumps(data), encoding='utf-8')
    monkeypatch.setenv('PARKING_DATA_FILE', str(path))
    with pytest.raises(ValueError): load_parking()
