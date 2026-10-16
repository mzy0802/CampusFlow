import json
from pathlib import Path
from app.data import load_parking
from app.parking_editor import ensure,merge_import_batch
from app.traffic_store import Store

def test_xiuyuan_original_geometry_capacity_and_ids_preserved():
    original=json.loads((Path(__file__).resolve().parents[2]/'data/parking.xiuyuan.original.geojson').read_text(encoding='utf-8'))
    collection=load_parking();lookup={f['properties']['id']:f for f in collection['features']}
    assert len(original['features'])==9 and len(lookup)==len(collection['features'])==33
    assert sum(f['properties']['capacity'] for f in original['features'])==1779
    for f in original['features']:
        imported=lookup[f['properties']['id']]
        assert imported['geometry']==f['geometry']
        assert imported['properties']['capacity']==f['properties']['capacity']
        assert imported['properties']['original_name']==f['properties']['name']
        assert imported['properties']['name']=='修远'+f['properties']['name']
    # Case-sensitive IDs come from different supplied areas; never overwrite one with the other.
    assert 'X2001' in lookup and 'x2001' in lookup
    assert lookup['X2001']['geometry']!=lookup['x2001']['geometry']

def test_existing_mingyuan_database_gains_nine_xiuyuan_areas_once(tmp_path):
    default=load_parking();old=json.loads(json.dumps(default))
    old['features']=[f for f in old['features'] if f['properties'].get('import_batch')!='xiuyuan-20261016']
    assert len(old['features'])==24
    old['features'][0]['properties']['capacity']=456
    store=Store(tmp_path/'existing.sqlite3');ensure(store,old);store.parking(old)
    result=merge_import_batch(store,default,'xiuyuan-20261016')
    assert len(result['collection']['features'])==33 and result['revision']==1
    assert store.parking(result['collection'])['features'][0]['properties']['capacity']==456
    assert merge_import_batch(store,default,'xiuyuan-20261016')['revision']==1
