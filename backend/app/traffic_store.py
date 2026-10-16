"""SQLite persistence with transactional revision checks and retained history."""
import json, sqlite3, os
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
from .network_models import Network

def now(): return datetime.now(timezone.utc).isoformat()

def example_network():
    # Fictional schematic near (0,0), never placed on the campus basemap.
    return Network.model_validate({'dataset':'example','nodes':[
        {'id':'start','name':'示例起点','longitude':0,'latitude':0},
        {'id':'cross','name':'示例路口','longitude':0.002,'latitude':0},
        {'id':'p_fast','name':'示例停车A','longitude':0.003,'latitude':0,'kind':'parking','capacity':30,'available':8},
        {'id':'p_near','name':'示例停车B','longitude':0.004,'latitude':0.0003,'kind':'parking','capacity':20,'available':5},
        {'id':'goal','name':'示例教学楼入口','longitude':0.004,'latitude':0,'kind':'entrance'}],
        'edges':[
        {'id':'e1','source':'start','target':'cross','verified':True},
        {'id':'e2','source':'cross','target':'p_fast','verified':True},
        {'id':'e3','source':'p_fast','target':'goal','modes':['walk'],'verified':True},
        {'id':'e4','source':'cross','target':'p_near','congestion':3,'verified':True},
        {'id':'e5','source':'p_near','target':'goal','modes':['walk'],'verified':True}]})

class Conflict(Exception): pass

class Store:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv('TRAFFIC_DB', str(Path(__file__).resolve().parents[1]/'storage'/'traffic.sqlite3')))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS networks(dataset TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS network_history(dataset TEXT, revision INTEGER, payload TEXT, updated_at TEXT, PRIMARY KEY(dataset,revision));
            CREATE TABLE IF NOT EXISTS parking_config(id TEXT PRIMARY KEY, name TEXT NOT NULL, capacity INTEGER NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS vision_records(job_id TEXT PRIMARY KEY, area_id TEXT, payload TEXT NOT NULL, updated_at TEXT NOT NULL);
            PRAGMA user_version=1;''')
            for graph in (Network(dataset='campus'), example_network()):
                db.execute('INSERT OR IGNORE INTO networks VALUES(?,?,?,?)',(graph.dataset,0,graph.model_dump_json(),now()))
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10)
        db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()
    def get(self,dataset):
        with self.connect() as db:
            row=db.execute('SELECT * FROM networks WHERE dataset=?',(dataset,)).fetchone()
        result=json.loads(row['payload']);result['revision']=row['revision']
        return result
    def save(self,graph):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM networks WHERE dataset=?',(graph.dataset,)).fetchone()
            if old['revision'] != graph.revision: raise Conflict('数据已由其他页面修改，请导出本地草稿后重新加载')
            db.execute('INSERT OR IGNORE INTO network_history VALUES(?,?,?,?)',(graph.dataset,old['revision'],old['payload'],old['updated_at']))
            graph=graph.model_copy(update={'revision':graph.revision+1})
            db.execute('UPDATE networks SET revision=?,payload=?,updated_at=? WHERE dataset=?',(graph.revision,graph.model_dump_json(),now(),graph.dataset))
        return graph.model_dump()
    def parking(self,collection):
        with self.connect() as db:
            for f in collection['features']:
                p=f['properties'];db.execute('INSERT OR IGNORE INTO parking_config VALUES(?,?,?,?)',(p['id'],p['name'],p['capacity'],now()))
            records={r['id']:dict(r) for r in db.execute('SELECT * FROM parking_config')}
        copied=json.loads(json.dumps(collection))
        for f in copied['features']:
            f['properties']['capacity']=records[f['properties']['id']]['capacity']
        return copied
    def set_capacity(self,area_id,capacity):
        with self.connect() as db:
            changed=db.execute('UPDATE parking_config SET capacity=?,updated_at=? WHERE id=?',(capacity,now(),area_id)).rowcount
        return changed
    def record_vision(self,job):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO vision_records VALUES(?,?,?,?)',(job['id'],job.get('area_id'),json.dumps(job,ensure_ascii=False),job['updated_at']))
    def vision_history(self,limit=50):
        with self.connect() as db:
            return [json.loads(r['payload']) for r in db.execute('SELECT payload FROM vision_records ORDER BY updated_at DESC LIMIT ?',(limit,))]
