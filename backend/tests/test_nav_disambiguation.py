"""Deterministic disambiguation and preference weights of the navigation chat."""
from fastapi.testclient import TestClient

from app import navigation, place_disambig
from app.main import app
from app.navigation import PREFERENCE_WEIGHTS, parking_cost, preference_key
from app.place_search import aliases

LESS_WALK = PREFERENCE_WEIGHTS['less_walk']
AVOID_CROWD = PREFERENCE_WEIGHTS['avoid_crowd']


def item(key, name, kind, longitude, latitude):
    base = {'id': key, 'name': name, 'longitude': longitude, 'latitude': latitude,
            'location_type': kind, 'source': 'OpenStreetMap'}
    return {**base, 'aliases': aliases(base)}


def catalog():
    return [
        item('m1', '明远教学楼A栋', 'building_center', 108.0000, 34.0000),
        item('m2', '明远教学楼B栋', 'building_center', 108.0005, 34.0000),
        item('m3', '明远教学楼C栋', 'building_center', 108.0010, 34.0000),
        item('m4', '明远教学楼D栋', 'building_center', 108.0015, 34.0000),
        item('m5', '明远教学楼E栋', 'building_center', 108.0020, 34.0000),
        item('x1', '修远教学楼一区', 'building_center', 108.0030, 34.0010),
        item('x2', '修远教学楼二区', 'building_center', 108.0035, 34.0010),
        item('cafe', '明远创客咖啡', 'poi', 108.0012, 34.0002),
        item('z1', '滋兰苑餐厅', 'building_center', 108.0040, 34.0000),
        item('z2', '滋兰苑西', 'parking_center', 108.0042, 34.0003),
        item('z3', '滋兰苑东', 'parking_center', 108.0044, 34.0003),
        item('n1', '北门', 'poi', 107.9990, 34.0020),
        item('n2', '北门', 'poi', 108.0050, 34.0020),
        item('dorm', '23号宿舍楼', 'building_center', 107.9995, 34.0005),
    ]


def by_id(items, key):
    return next(place for place in items if place['id'] == key)


def test_family_without_the_building_is_asked():
    reply = place_disambig.clarify('我要去明远楼', catalog())
    assert '5个可选位置' in reply
    assert 'A栋' in reply and 'E栋' in reply


def test_explicit_building_is_not_asked():
    items = catalog()
    assert place_disambig.clarify('我要去明远C栋', items, by_id(items, 'm3')) == ''
    assert place_disambig.clarify('我要去明远3', items, by_id(items, 'm3')) == ''


def test_numeric_areas_stay_in_readable_order():
    reply = place_disambig.clarify('去修远楼', catalog())
    assert '2个可选位置' in reply
    assert reply.index('一区') < reply.index('二区')


def test_repeated_names_are_asked_with_distinct_positions():
    reply = place_disambig.clarify('我在北门', catalog())
    assert '同名地点' in reply
    assert '偏西' in reply and '偏东' in reply


def test_one_cafe_chain_keeps_single_position_labels():
    items = [item('c1', '瑞幸咖啡', 'poi', 108.9000, 34.3700),
             item('c2', '瑞幸咖啡', 'poi', 108.9060, 34.3700),
             item('c3', '瑞幸咖啡', 'poi', 108.8880, 34.3690)]
    reply = place_disambig.clarify('我要去瑞幸咖啡', items)
    assert '3个同名地点' in reply
    assert len(reply.split('、')) >= 3


def test_duplicate_survey_nodes_do_not_become_a_question():
    gate = [item('g1', '北门', 'poi', 108.900000, 34.370000),
            item('g2', '北门', 'poi', 108.900050, 34.370010)]
    assert place_disambig.clarify('我在北门', gate) == ''


def test_a_longer_name_outside_the_family_is_not_hijacked():
    assert place_disambig.clarify('我要去滋兰苑餐厅', catalog()) == ''


def test_unique_place_never_asks():
    assert place_disambig.clarify('我在23号宿舍楼', catalog()) == ''
    assert place_disambig.clarify('我在23号宿舍楼', catalog(), by_id(catalog(), 'dorm')) == ''


def test_default_weights_keep_the_original_formula():
    assert parking_cost(4, 3, 50) == 4 + 2 * 3 + 5 * 50 / 100
    assert parking_cost(4, 3, 50, None) == parking_cost(4, 3, 50)


def test_less_walk_can_flip_the_ranking():
    assert parking_cost(1, 4, 0) < parking_cost(6, 2, 0)
    assert parking_cost(1, 4, 0, LESS_WALK) > parking_cost(6, 2, 0, LESS_WALK)


def test_avoid_crowd_can_flip_the_ranking():
    assert parking_cost(2, 1, 100) < parking_cost(9, 1, 0)
    assert parking_cost(2, 1, 100, AVOID_CROWD) > parking_cost(9, 1, 0, AVOID_CROWD)


def test_less_walk_compares_walking_time_alone():
    assert preference_key({'duration_minutes': 8}, 'less_walk') == 8
    assert preference_key({'duration_minutes': 6, 'walk_minutes': 0.4}, 'less_walk') == 0.4


def test_chat_asks_which_building_instead_of_guessing(monkeypatch):
    items = catalog()
    monkeypatch.setattr(navigation, 'campus_places', lambda request: items)
    monkeypatch.setattr(navigation, 'parse_trip', lambda messages, places: (
        {'origin_id': 'dorm', 'destination_id': 'm3', 'mode': 'auto', 'preference': None, 'reply': ''}, 'test'))
    response = TestClient(app).post('/api/navigation/chat', json={
        'messages': [{'role': 'user', 'content': '我在23号宿舍楼，要去明远楼'}]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['status'] == 'clarification'
    assert '5个可选位置' in body['reply']


def test_chat_passes_preference_weights_to_the_shared_cost_function(monkeypatch):
    import app.traffic_snapshot as traffic_snapshot

    items = catalog()
    seen = []
    monkeypatch.setattr(navigation, 'campus_places', lambda request: items)
    monkeypatch.setattr(navigation, 'parse_trip', lambda messages, places: (
        {'origin_id': 'dorm', 'destination_id': 'm3', 'mode': 'bike', 'preference': 'less_walk', 'reply': ''}, 'test'))
    monkeypatch.setattr(navigation, 'compute_parking', lambda body, request, graph, areas=None, weights=None: (
        seen.append(weights) or {'items': []}))
    monkeypatch.setattr(navigation, 'route', lambda graph, body, mode: {
        'id': mode, 'mode': mode, 'distance_m': 100.0, 'duration_minutes': 5.0,
        'geojson': {'type': 'FeatureCollection', 'features': []}})
    monkeypatch.setattr(traffic_snapshot, 'snapshot', lambda request, context: (
        {}, [], {'time_seconds': 0, 'road_users': 0, 'busy_segments': 0}))

    response = TestClient(app).post('/api/navigation/chat', json={
        'messages': [{'role': 'user', 'content': '我在23号宿舍楼，骑车去明远C栋，少走路'}]})
    assert response.status_code == 200, response.text
    assert seen == [LESS_WALK]
    assert response.json()['preference'] == 'less_walk'
