from fastapi.testclient import TestClient
from app.main import app


def test_network_roundtrip_conflict_and_road_export():
    with TestClient(app) as client:
        graph = client.get('/api/network/campus').json()
        graph['nodes'] = [
            {'id': 'a', 'name': 'A', 'longitude': 0, 'latitude': 0},
            {'id': 'b', 'name': 'B', 'longitude': .001, 'latitude': 0}]
        graph['edges'] = [{'id': 'ab', 'source': 'a', 'target': 'b', 'verified': True}]
        saved = client.put('/api/network/campus', json=graph)
        assert saved.status_code == 200
        assert saved.json()['revision'] == graph['revision'] + 1
        assert client.put('/api/network/campus', json=graph).status_code == 409
        roads = client.get('/api/roads').json()
        assert roads['status'] == 'configured'
        assert roads['features'][0]['geometry']['coordinates'] == [[0, 0], [.001, 0]]
        assert len(client.get('/api/places').json()['items']) == 2
        body = {'dataset': 'example', 'origin_id': 'start', 'destination_id': 'goal'}
        result = client.post('/api/trips/plan', json=body).json()
        assert result['recommended']['parking_node_id'] == 'p_fast'
        body['preference'] = 'less_walking'
        assert client.post('/api/trips/plan', json=body).json()['recommended']['parking_node_id'] == 'p_near'
