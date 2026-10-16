import json
import math
import re
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,Field
from .annotations import Polygon
from .traffic_store import now

router=APIRouter(prefix='/parking-editor',tags=['parking-editor'])

def ensure(store,default):
    with store.connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS parking_geometry(id INTEGER PRIMARY KEY,revision INTEGER,payload TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS parking_geometry_history(revision INTEGER PRIMARY KEY,payload TEXT,updated_at TEXT)')
        db.execute('INSERT OR IGNORE INTO parking_geometry VALUES(1,0,?)',(json.dumps(default,ensure_ascii=False),))
        row=db.execute('SELECT * FROM parking_geometry WHERE id=1').fetchone()
    return {'revision':row['revision'],'collection':json.loads(row['payload'])}

def validate_collection(collection,existing=None):
    if collection.get('type')!='FeatureCollection' or not isinstance(collection.get('features'),list) or len(collection['features'])>500:raise ValueError('需要最多500个区域的GeoJSON FeatureCollection')
    ids=set();features=[]
    for f in collection['features']:
        props=f.get('properties',{});geo=f.get('geometry',{});pid=props.get('id');name=props.get('name');capacity=props.get('capacity')
        if not isinstance(pid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',pid) or pid in ids:raise ValueError('区域ID为空、重复或含非法字符')
        ids.add(pid)
        if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('区域名称长度为1～100')
        if type(capacity)!=int or not 1<=capacity<=100000:raise ValueError('容量必须为1～100000的整数')
        if geo.get('type')!='Polygon' or len(geo.get('coordinates',[]))!=1:raise ValueError('暂支持无孔洞的Polygon')
        ring=geo['coordinates'][0]
        if not 4<=len(ring)<=201 or ring[0]!=ring[-1]:raise ValueError('边界至少3个顶点且必须闭合')
        if any(not isinstance(p,list) or len(p)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in p) or not -180<=p[0]<=180 or not -85<=p[1]<=85 for p in ring):raise ValueError('经纬度不合法')
        xs=[p[0] for p in ring];ys=[p[1] for p in ring];w=max(xs)-min(xs);h=max(ys)-min(ys)
        if not w or not h:raise ValueError('区域不能退化成直线')
        unchanged=any(old['properties']['id']==pid and old['geometry']==geo for old in (existing or {}).get('features',[]))
        validation='valid'
        try:Polygon(id=pid,label='allowed',points=[((x-min(xs))/w,(y-min(ys))/h) for x,y in ring[:-1]])
        except ValueError:
            if not unchanged:raise ValueError(f'{name}：区域边界自相交或有重复顶点，请重画')
            validation='legacy_boundary_needs_review'
        features.append({'type':'Feature','properties':{'id':pid,'name':name.strip(),'capacity':capacity,'source':'manual_map_annotation','geometry_validation':validation},'geometry':geo})
    return {'type':'FeatureCollection','is_example':False,'features':features,'source':'manual_map_annotation'}

class SaveRequest(BaseModel):
    revision:int=Field(ge=0)
    collection:dict

@router.get('')
def get(request:Request):
    data=ensure(request.app.state.store,request.app.state.parking)
    data['collection']=request.app.state.store.parking(data['collection'])
    return data

@router.put('')
def save(body:SaveRequest,request:Request):
    try:collection=validate_collection(body.collection,request.app.state.parking)
    except (ValueError,TypeError,KeyError,IndexError) as e:raise HTTPException(422,str(e))
    store=request.app.state.store;ensure(store,request.app.state.parking)
    ids={f['properties']['id'] for f in collection['features']}
    linked={n['parking_id'] for n in store.get('campus')['nodes'] if n.get('parking_id')}
    if not linked<=ids:raise HTTPException(422,'待删除区域仍关联道路入口，请先在道路编辑中解除关联')
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='annotation_media'").fetchone():
            assigned=set()
            for row in db.execute('SELECT payload FROM annotation_media'):
                payload=json.loads(row['payload'])
                if isinstance(payload,dict) and payload.get('area_id'):assigned.add(payload['area_id'])
            if not assigned<=ids:raise HTTPException(422,'待删除停车区仍关联标注素材，请先在标注工作台解除关联')
        old=db.execute('SELECT * FROM parking_geometry WHERE id=1').fetchone()
        if old['revision']!=body.revision:raise HTTPException(409,'区域已由其他页面修改，请导出草稿后重新加载')
        db.execute('INSERT INTO parking_geometry_history VALUES(?,?,?)',(old['revision'],old['payload'],now()))
        db.execute('UPDATE parking_geometry SET revision=revision+1,payload=? WHERE id=1',(json.dumps(collection,ensure_ascii=False),))
        for f in collection['features']:
            p=f['properties'];db.execute('INSERT OR REPLACE INTO parking_config VALUES(?,?,?,?)',(p['id'],p['name'],p['capacity'],now()))
    request.app.state.parking=collection
    return get(request)
