"""Owner-corrected Hongyuan identities, retaining saved links and revision history."""
import json
from pathlib import Path
from .parking_editor import ensure
from .traffic_store import now

ALIASES = {'X'+n: 'WH'+n for n in ('1001','1002','1003','1004','1005','2001','2002','2003','2004')}


def migrate_hongyuan(store, default, storage):
    ensure(store, default)
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)')
        db.execute('BEGIN IMMEDIATE')
        if not db.execute("SELECT 1 FROM settings WHERE key='hongyuan_identity_20261016'").fetchone():
            row = db.execute('SELECT * FROM parking_geometry WHERE id=1').fetchone()
            collection = json.loads(row['payload'])
            changed = False
            ids = {f['properties']['id'] for f in collection['features']}
            for f in collection['features']:
                p = f['properties']; old = p['id']
                if old not in ALIASES:
                    continue
                new = ALIASES[old]
                if new in ids:
                    raise ValueError('鸿远ID迁移冲突：' + new)
                p.update(id=new, name='鸿远'+p.get('original_name', p['name'].removeprefix('修远')),
                         import_batch='hongyuan-20261016', source_id=old)
                changed = True
            if changed:
                db.execute('INSERT INTO parking_geometry_history VALUES(?,?,?)', (row['revision'], row['payload'], now()))
                db.execute('UPDATE parking_geometry SET revision=revision+1,payload=? WHERE id=1', (json.dumps(collection, ensure_ascii=False),))
            names = {f['properties']['id']: f['properties']['name'] for f in collection['features']}
            for old, new in ALIASES.items():
                existing = db.execute('SELECT * FROM parking_config WHERE id=?', (old,)).fetchone()
                if existing:
                    if db.execute('SELECT 1 FROM parking_config WHERE id=?', (new,)).fetchone():
                        raise ValueError('鸿远容量配置迁移冲突：' + new)
                    db.execute('UPDATE parking_config SET id=?,name=?,updated_at=? WHERE id=?', (new, names.get(new, existing['name'].replace('修远','鸿远',1)), now(), old))
            for graph in db.execute('SELECT * FROM networks').fetchall():
                payload = json.loads(graph['payload']); edited = False
                for node in payload.get('nodes', []):
                    if node.get('parking_id') in ALIASES:
                        node['parking_id'] = ALIASES[node['parking_id']]; edited = True
                if edited:
                    db.execute('INSERT OR IGNORE INTO network_history VALUES(?,?,?,?)', (graph['dataset'], graph['revision'], graph['payload'], graph['updated_at']))
                    payload['revision'] = graph['revision']+1
                    db.execute('UPDATE networks SET revision=?,payload=?,updated_at=? WHERE dataset=?', (payload['revision'], json.dumps(payload, ensure_ascii=False), now(), graph['dataset']))
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='annotation_media'").fetchone():
                for media in db.execute('SELECT id,payload FROM annotation_media').fetchall():
                    payload = json.loads(media['payload'])
                    if isinstance(payload, dict) and payload.get('area_id') in ALIASES:
                        payload['area_id'] = ALIASES[payload['area_id']]
                        db.execute('UPDATE annotation_media SET revision=revision+1,payload=? WHERE id=?', (json.dumps(payload, ensure_ascii=False), media['id']))
            for record in db.execute('SELECT job_id,area_id,payload FROM vision_records').fetchall():
                if record['area_id'] in ALIASES:
                    payload = json.loads(record['payload']); payload['area_id'] = ALIASES[record['area_id']]
                    db.execute('UPDATE vision_records SET area_id=?,payload=? WHERE job_id=?', (payload['area_id'], json.dumps(payload, ensure_ascii=False), record['job_id']))
            db.execute("INSERT INTO settings VALUES('hongyuan_identity_20261016',?)", (now(),))
    # Files are also used to reconstruct observations; repeat safely after any interrupted startup.
    for path in Path(storage).glob('*/job.json'):
        payload = json.loads(path.read_text(encoding='utf-8'))
        if payload.get('area_id') in ALIASES:
            backup = path.with_name('job.before-hongyuan.json')
            if not backup.exists():
                backup.write_bytes(path.read_bytes())
            payload['area_id'] = ALIASES[payload['area_id']]
            temp = path.with_name('job.identity.tmp')
            temp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            temp.replace(path)
