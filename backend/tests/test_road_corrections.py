import json
from pathlib import Path
from app.data import DEFAULT_FILE
from app.navigation import route, NavigationRequest
from app.road_corrections import correct_xiuyuan_roundabout,BAD_CHORD
from app.traffic_store import Store


def graph():return json.loads((DEFAULT_FILE.parent/'network.osm.json').read_text(encoding='utf-8'))
def plan(g,a,b):
    ns={n['id']:n for n in g['nodes']}
    return route(g,NavigationRequest(origin={k:ns[a][k] for k in ('longitude','latitude')},destination={k:ns[b][k] for k in ('longitude','latitude')},mode='bike'),'bike')['geojson']['geometry']['coordinates']


def test_roundabout_repairs_only_bad_chord_once_retains_history(tmp_path):
    g=graph();g['edges'].append({'id':BAD_CHORD,'source':'osm_n2613667540','target':'osm_n2613667577','modes':['bike','walk'],'bidirectional':True,'verified':True,'congestion':1})
    store=Store(tmp_path/'db.sqlite3')
    with store.connect() as db:db.execute("UPDATE networks SET payload=? WHERE dataset='campus'",(json.dumps(g),))
    correct_xiuyuan_roundabout(store);repaired=store.get('campus')
    assert len(repaired['edges'])==len(g['edges'])-1
    assert len([e for e in repaired['edges'] if e['id'].startswith('osm_w277529726_')])==20
    assert repaired['revision']==1
    correct_xiuyuan_roundabout(store)
    assert store.get('campus')==repaired
    with store.connect() as db:assert db.execute("SELECT count(*) FROM network_history WHERE dataset='campus'").fetchone()[0]==1
    coords=plan(repaired,'osm_n2613667609','osm_n4362729272')
    assert len(coords)>=9
    assert [108.8953802,34.370248] in coords # traverses existing southern arc


def test_mid_avenue_uturn_uses_existing_connector():
    coords=plan(graph(),'osm_n11144005109','osm_n2613667578')
    assert [108.8995404,34.3715713] in coords
    assert [108.8992917,34.3716159] in coords
    assert len(coords)<10 # does not detour to either end roundabout


def test_requested_cycleway_connects_saved_nodes_and_survives_restart(tmp_path):
    from app.road_corrections import connect_owner_cycleway,RECIPE
    g=graph();store=Store(tmp_path/'cycle.sqlite3')
    with store.connect() as db:db.execute("UPDATE networks SET payload=? WHERE dataset='campus'",(json.dumps(g),))
    connect_owner_cycleway(store);updated=store.get('campus')
    recipe=json.loads(RECIPE.read_text(encoding='utf-8'));lookup={e['id']:e for e in updated['edges']}
    for e in recipe['edges']:
        assert lookup[e['id']]['modes']==['walk','bike']
        assert lookup[e['id']]['bidirectional']
    coords=plan(updated,recipe['nodes'][0]['id'],recipe['nodes'][-1]['id'])
    assert len(coords)>=2
    revision=updated['revision'];connect_owner_cycleway(store)
    assert store.get('campus')['revision']==revision
