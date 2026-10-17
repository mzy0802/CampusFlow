"""Restore the supplied roundabout topology without replacing unrelated edits."""
import json
from pathlib import Path
from .traffic_store import now

BAD_CHORD='efe3cb6759cc6'
CHORD_ENDS={'osm_n2613667540','osm_n2613667577'}

RECIPE = Path(__file__).resolve().parents[2] / 'data/cycleway.owner.json'


def connect_owner_cycleway(store):
    recipe=json.loads(RECIPE.read_text(encoding='utf-8'))
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)')
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM settings WHERE key=?',(recipe['version'],)).fetchone():return
        row=db.execute("SELECT * FROM networks WHERE dataset='campus'").fetchone()
        graph=json.loads(row['payload']);ids={n['id'] for n in graph['nodes']}
        # Avoid adding a campus connection into intentionally empty/custom non-OSM networks.
        anchors=[n['id'] for n in recipe['nodes'] if n['id'].startswith('osm_n')]
        if not set(anchors)<=ids:return
        graph['nodes'].extend(n for n in recipe['nodes'] if n['id'] not in ids)
        edges={e['id']:e for e in graph['edges']}
        for edge in recipe['edges']:
            if edge['id'] in edges:edges[edge['id']].update(edge)
            else:graph['edges'].append(edge)
        db.execute('INSERT INTO network_history VALUES(?,?,?,?)',('campus',row['revision'],row['payload'],row['updated_at']))
        graph['revision']=row['revision']+1
        db.execute("UPDATE networks SET revision=?,payload=?,updated_at=? WHERE dataset='campus'",(graph['revision'],json.dumps(graph,ensure_ascii=False),now()))
        db.execute('INSERT INTO settings VALUES(?,?)',(recipe['version'],now()))


def correct_xiuyuan_roundabout(store):
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)')
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM settings WHERE key='xiuyuan_roundabout_20261017'").fetchone():return
        row=db.execute("SELECT * FROM networks WHERE dataset='campus'").fetchone()
        graph=json.loads(row['payload'])
        repaired=[e for e in graph['edges'] if not (e['id']==BAD_CHORD and {e['source'],e['target']}==CHORD_ENDS)]
        if len(repaired)!=len(graph['edges']):
            db.execute('INSERT INTO network_history VALUES(?,?,?,?)',('campus',row['revision'],row['payload'],row['updated_at']))
            graph['edges']=repaired;graph['revision']=row['revision']+1
            db.execute("UPDATE networks SET revision=?,payload=?,updated_at=? WHERE dataset='campus'",(graph['revision'],json.dumps(graph,ensure_ascii=False),now()))
        db.execute("INSERT INTO settings VALUES('xiuyuan_roundabout_20261017',?)",(now(),))
