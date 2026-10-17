import json
from app.data import load_parking
from app.parking_editor import ensure
from app.parking_identity import migrate_hongyuan
from app.traffic_store import Store


def test_hongyuan_identity_links_and_idempotence(tmp_path):
    default = load_parking()
    old = json.loads(json.dumps(default))
    for f in old['features']:
        p = f['properties']
        if p['id'].startswith('WH'):
            p['id'] = 'X'+p['id'][2:]
            p['name'] = p['name'].replace('鸿远', '修远')
            p['capacity'] = 321
    store = Store(tmp_path/'db.sqlite3'); ensure(store, old); store.parking(old)
    with store.connect() as db:
        db.execute('CREATE TABLE annotation_media(id TEXT PRIMARY KEY,metadata TEXT,revision INTEGER,payload TEXT)')
        db.execute('INSERT INTO annotation_media VALUES(?,?,?,?)', ('media','{}',3,json.dumps({'area_id':'X1001','polygons':[]})))
    job = {'id':'a'*32,'area_id':'X1001','updated_at':'2026-10-16','result':{}}
    store.record_vision(job)
    folder=tmp_path/('a'*32);folder.mkdir(); path=folder/'job.json';path.write_text(json.dumps(job),encoding='utf-8')
    migrate_hongyuan(store, default, tmp_path)
    migrate_hongyuan(store, default, tmp_path)
    assert json.loads(path.read_text(encoding='utf-8'))['area_id']=='WH1001'
    assert (folder/'job.before-hongyuan.json').exists()
    assert store.vision_history()[0]['area_id']=='WH1001'
    with store.connect() as db:
        media=db.execute('SELECT * FROM annotation_media').fetchone()
        assert json.loads(media['payload'])['area_id']=='WH1001' and media['revision']==4
        geometry=json.loads(db.execute('SELECT payload FROM parking_geometry').fetchone()[0])
        assert len(geometry['features'])==41
        assert {f['properties']['name'] for f in geometry['features'] if f['properties']['id']=='WH1001'}=={'鸿远1区北'}
        assert db.execute("SELECT capacity FROM parking_config WHERE id='WH1001'").fetchone()[0]==321
        assert db.execute('SELECT count(*) FROM parking_geometry_history').fetchone()[0]==1
