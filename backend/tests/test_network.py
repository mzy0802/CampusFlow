import pytest
from app.traffic_store import Store, example_network, Conflict
from app.network_models import TripRequest, Network
from app.trip_planner import plan

def example():
    graph=example_network().model_dump()
    status={n['id']:{'capacity':n['capacity'],'available':n['available']} for n in graph['nodes'] if n['kind']=='parking'}
    return graph,status

def test_preferences_change_recommendation():
    g,s=example()
    fast=plan(g,TripRequest(dataset='example',origin_id='start',destination_id='goal'),s)
    short=plan(g,TripRequest(dataset='example',origin_id='start',destination_id='goal',preference='less_walking'),s)
    assert fast['recommended']['parking_node_id']=='p_fast'
    assert short['recommended']['parking_node_id']=='p_near'
    assert short['recommended']['walk_distance_m']<fast['recommended']['walk_distance_m']
    assert short['recommended']['total_minutes']>fast['recommended']['total_minutes']
    for r in [fast,short]:
        ride,walk=r['recommended']['segments']
        assert ride['node_ids'][0]=='start'
        assert walk['node_ids'][-1]=='goal'
        assert ride['node_ids'][-1]==walk['node_ids'][0]

def test_full_and_disconnected_parking_excluded():
    g,s=example();s['p_fast']['available']=0
    g['edges']=[e for e in g['edges'] if e['id'] not in ('e4','e5')]
    result=plan(g,TripRequest(origin_id='start',destination_id='goal'),s)
    assert result['status']=='no_route'
    assert result['recommended'] is None
    assert len(result['excluded'])==2

def test_unverified_and_one_way_not_traversed_backwards():
    g,s=example()
    for e in g['edges']: e['verified']=False
    assert plan(g,TripRequest(origin_id='start',destination_id='goal'),s)['status']=='no_route'
    g,s=example()
    g['edges'][0].update(source='cross',target='start',bidirectional=False)
    assert plan(g,TripRequest(origin_id='start',destination_id='goal'),s)['status']=='no_route'

def test_zero_distance_leg_is_valid():
    g,s=example()
    r=plan(g,TripRequest(origin_id='p_fast',destination_id='p_fast'),s)
    assert r['recommended']['total_minutes']==1
    assert r['recommended']['segments'][0]['geojson']['geometry']['type']=='Point'

def test_store_survives_reopen_and_rejects_stale_write(tmp_path):
    store=Store(tmp_path/'db.sqlite3');a=store.get('example');b=Network.model_validate(a)
    b.nodes[0].name='changed';saved=store.save(b)
    assert saved['revision']==1
    assert Store(tmp_path/'db.sqlite3').get('example')['nodes'][0]['name']=='changed'
    with pytest.raises(Conflict):store.save(Network.model_validate(a))
    assert store.get('campus')['nodes']==[]

@pytest.mark.parametrize('fault',['duplicate','missing','loop','nonfinite','capacity'])
def test_bad_network_rejected(fault):
    g,_=example()
    if fault=='duplicate':g['nodes'].append(g['nodes'][0])
    if fault=='missing':g['edges'][0]['target']='absent'
    if fault=='loop':g['edges'][0]['target']=g['edges'][0]['source']
    if fault=='nonfinite':g['nodes'][0]['latitude']=float('nan')
    if fault=='capacity':g['nodes'][0]['available']=999999
    with pytest.raises(ValueError):Network.model_validate(g)

def test_capacity_and_vision_persist(tmp_path):
    from app.data import load_parking
    store=Store(tmp_path/'db.sqlite3');data=store.parking(load_parking());area=data['features'][0]['properties']['id']
    assert store.set_capacity(area,123)
    assert store.parking(data)['features'][0]['properties']['capacity']==123
    job={'id':'abc','area_id':area,'updated_at':'2026-10-16T00:00:00+00:00','result':{'count':7}}
    store.record_vision(job);store.record_vision(job)
    assert len(store.vision_history())==1
    assert store.vision_history()[0]['result']['count']==7
