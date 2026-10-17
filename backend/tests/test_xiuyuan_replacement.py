import copy
import json
from pathlib import Path
from app.data import load_parking
from app.parking_editor import ensure, replace_import_batch
from app.traffic_store import Store

BATCH = 'xiuyuan-v2-20261016'


def test_replacement_source_capacities_and_unique_ids():
    default = load_parking()
    incoming = [f for f in default['features'] if f['properties'].get('import_batch') == BATCH]
    raw = json.loads((Path(__file__).resolve().parents[2] / 'data/parking.xiuyuan.v2.original.geojson').read_text(encoding='utf-8-sig'))
    valid = [f for f in raw['features'] if f.get('geometry')]
    assert len(incoming) == len(valid) == 15
    assert sum(f['properties']['capacity'] for f in incoming) == 1208
    assert len({f['properties']['id'] for f in default['features']}) == 52
    for source, result in zip(valid, incoming):
        assert result['properties']['capacity'] == source['properties']['space']
        assert set(map(tuple, result['geometry']['coordinates'][0])) == set(map(tuple, source['geometry']['coordinates']))


def test_replace_once_updates_capacity_preserves_links_and_other_edits(tmp_path):
    default = load_parking()
    old = copy.deepcopy(default)
    old['features'] = [f for f in old['features'] if f['properties'].get('import_batch') != BATCH or f['properties']['id'] == 'x2001']
    for f in old['features']:
        f['properties']['capacity'] = 777
    store = Store(tmp_path / 'replace.sqlite3')
    ensure(store, old)
    store.parking(old)
    result = replace_import_batch(store, default, BATCH)
    lookup = {f['properties']['id']: f for f in store.parking(result['collection'])['features']}
    assert lookup['x2001']['properties']['name'] == '修远2东面'
    assert lookup['x2001']['properties']['capacity'] == 50
    assert lookup['WM1001']['properties']['capacity'] == 777
    assert len(lookup) == 52
    store.set_capacity('x2001', 123)
    again = replace_import_batch(store, default, BATCH)
    assert again['revision'] == result['revision']
    lookup = {f['properties']['id']: f for f in store.parking(again['collection'])['features']}
    assert lookup['x2001']['properties']['capacity'] == 123
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM parking_geometry_history').fetchone()[0] == 1
