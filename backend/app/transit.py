"""Editable transit geometry and camera-ready passenger observations."""
import json
from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field, model_validator
from .navigation import Point
from .vision_metrics import congestion
from .traffic_store import now

router=APIRouter(prefix='/transit',tags=['transit'])

class Stop(Point):
    id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=1,max_length=100)

class Line(BaseModel):
    id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=1,max_length=100)
    points:list[Point]=Field(min_length=2,max_length=2000)
    stop_ids:list[str]=Field(default_factory=list,max_length=200)
    color:str=Field('#8b5cf6',pattern=r'^#[0-9a-fA-F]{6}$')

class Vehicle(BaseModel):
    id:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    name:str=Field(min_length=1,max_length=100)
    route_id:str
    capacity:int=Field(ge=1,le=1000)
    camera_id:str=Field('',max_length=100)

class TransitSet(BaseModel):
    revision:int=Field(ge=0)
    stops:list[Stop]=Field(default_factory=list,max_length=500)
    routes:list[Line]=Field(default_factory=list,max_length=100)
    vehicles:list[Vehicle]=Field(default_factory=list,max_length=300)
    @model_validator(mode='after')
    def references(self):
        for values in (self.stops,self.routes,self.vehicles):
            if len({v.id for v in values})!=len(values):raise ValueError('ID不能重复')
        stops={s.id for s in self.stops};routes={r.id for r in self.routes}
        if any(len({(p.longitude,p.latitude) for p in r.points})<2 for r in self.routes):raise ValueError('线路至少需要两个不同的坐标点')
        if any(len(set(r.stop_ids))!=len(r.stop_ids) for r in self.routes):raise ValueError('本线站点ID不能重复；环线无需重复填写首站')
        if any(s not in stops for r in self.routes for s in r.stop_ids):raise ValueError('线路引用了不存在的站点')
        if any(v.route_id not in routes for v in self.vehicles):raise ValueError('车辆引用了不存在的线路')
        return self

class PassengerObservation(BaseModel):
    count:int=Field(ge=0,le=10000,strict=True)
    captured_at:datetime
    source:Literal['camera','manual_test']='camera'
    camera_id:str=Field('',max_length=100)
    @model_validator(mode='after')
    def valid_time(self):
        if self.captured_at.tzinfo is None:raise ValueError('采集时间必须带时区')
        if self.captured_at>datetime.now(timezone.utc)+timedelta(minutes=5):raise ValueError('采集时间不能在未来')
        return self

def ensure(store):
    with store.connect() as db:
        db.executescript('''CREATE TABLE IF NOT EXISTS transit_config(id INTEGER PRIMARY KEY,revision INTEGER,payload TEXT);
        CREATE TABLE IF NOT EXISTS transit_history(revision INTEGER PRIMARY KEY,payload TEXT);
        CREATE TABLE IF NOT EXISTS bus_observations(vehicle_id TEXT PRIMARY KEY,payload TEXT);''')
        db.execute('INSERT OR IGNORE INTO transit_config VALUES(1,0,?)',(json.dumps({'stops':[],'routes':[],'vehicles':[]}),))

@router.get('')
def get(request:Request):
    store=request.app.state.store;ensure(store)
    with store.connect() as db:
        row=db.execute('SELECT * FROM transit_config WHERE id=1').fetchone()
        observations={r['vehicle_id']:json.loads(r['payload']) for r in db.execute('SELECT * FROM bus_observations')}
    data=json.loads(row['payload'])
    for v in data['vehicles']:
        obs=observations.get(v['id'])
        v['observation']={**obs,**congestion(obs['count'],v['capacity'])} if obs else None
    return {**data,'revision':row['revision'],'status':'configured' if data['routes'] else 'not_configured','message':'已保存公交线路与站点' if data['routes'] else '请在公交工作台绘制线路与站点'}

@router.put('')
def save(body:TransitSet,request:Request):
    store=request.app.state.store;ensure(store)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM transit_config WHERE id=1').fetchone()
        if row['revision']!=body.revision:raise HTTPException(409,'公交数据已修改，请重新加载')
        db.execute('INSERT INTO transit_history VALUES(?,?)',(row['revision'],row['payload']))
        db.execute('UPDATE transit_config SET revision=revision+1,payload=? WHERE id=1',(json.dumps(body.model_dump(exclude={'revision'}),ensure_ascii=False),))
    return get(request)

@router.post('/vehicles/{vehicle_id}/observations')
def observe(vehicle_id:str,body:PassengerObservation,request:Request):
    data=get(request);vehicle=next((v for v in data['vehicles'] if v['id']==vehicle_id),None)
    if not vehicle:raise HTTPException(404,'公交车辆不存在')
    if body.source=='camera' and (not vehicle['camera_id'] or vehicle['camera_id']!=body.camera_id):
        raise HTTPException(422,'摄像头ID与该车辆配置不一致')
    payload=body.model_dump(mode='json');payload['received_at']=now()
    with request.app.state.store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        old=db.execute('SELECT payload FROM bus_observations WHERE vehicle_id=?',(vehicle_id,)).fetchone()
        if old and datetime.fromisoformat(json.loads(old['payload'])['captured_at'])>=body.captured_at:
            raise HTTPException(409,'已存在相同或更新的采集结果')
        db.execute('INSERT OR REPLACE INTO bus_observations VALUES(?,?)',(vehicle_id,json.dumps(payload)))
    return {**payload,**congestion(body.count,vehicle['capacity'])}
