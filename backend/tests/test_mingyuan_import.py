import json
from pathlib import Path
from app.data import load_parking
from app.parking_editor import ensure,merge_import_batch,validate_collection
from app.traffic_store import Store

BATCH='mingyuan-20261016'

def test_mingyuan_preserves_provided_ids_capacities_and_locations():
    original=json.loads((Path(__file__).resolve().parents[2]/'data/parking.mingyuan.original.geojson').read_text(encoding='utf-8'))
    collection=load_parking();imported=[f for f in collection['features'] if f['properties'].get('import_batch')==BATCH]
    assert len(original['features'])==len(imported)==17 and len(collection['features'])==24
    lookup={f['properties']['id']:f for f in imported}
    assert len(lookup)==17 and sum(f['properties']['capacity'] for f in imported)==640
    for f in original['features']:
        p=f['properties'];converted=lookup[p['id']]
        assert converted['properties']['name']==p['name']
        assert converted['properties']['capacity']==p['space']
        points=f['geometry']['coordinates'][0] if f['geometry']['type']=='Polygon' else f['geometry']['coordinates']
        normalized=[]
        for point in points:
            if not normalized or normalized[-1]!=point:normalized.append(point)
        if normalized[-1]!=normalized[0]:normalized.append(normalized[0])
        assert converted['geometry']['coordinates']==[normalized]
    assert len(validate_collection({'type':'FeatureCollection','features':imported})['features'])==17

def test_import_append_once_keeps_edits_and_does_not_restore_deleted_areas(tmp_path):
    default=load_parking()
    existing=json.loads(json.dumps(default))
    existing['features']=[f for f in existing['features'] if f['properties'].get('import_batch')!=BATCH]
    existing['features'][0]['properties'].update(name='用户改过的名称',capacity=321)
    store=Store(tmp_path/'existing.sqlite3');ensure(store,existing);store.parking(existing)
    merged=merge_import_batch(store,default,BATCH)
    assert merged['revision']==1 and len(merged['collection']['features'])==24
    assert merged['collection']['features'][0]['properties']['name']=='用户改过的名称'
    assert store.parking(merged['collection'])['features'][0]['properties']['capacity']==321
    assert merge_import_batch(store,default,BATCH)['revision']==1
    # Simulate a later user deletion. A startup must not undo it.
    removed=merged['collection'];removed['features']=[f for f in removed['features'] if f['properties']['id']!='WM1001']
    with store.connect() as db:
        assert json.loads(db.execute('SELECT payload FROM parking_geometry_history WHERE revision=0').fetchone()[0])['features'][0]['properties']['capacity']==321
        db.execute('UPDATE parking_geometry SET revision=2,payload=? WHERE id=1',(json.dumps(removed),))
    after=merge_import_batch(store,default,BATCH)
    assert after['revision']==2 and len(after['collection']['features'])==23
    assert all(f['properties']['id']!='WM1001' for f in after['collection']['features'])

def test_fresh_database_does_not_duplicate_import(tmp_path):
    store=Store(tmp_path/'new.sqlite3');default=load_parking()
    assert len(merge_import_batch(store,default,BATCH)['collection']['features'])==24
    assert len(merge_import_batch(store,default,BATCH)['collection']['features'])==24
