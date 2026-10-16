from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Literal
from .network_models import Network,TripRequest
from .traffic_store import Conflict
from .trip_planner import plan
from .parking import snapshot
router=APIRouter(tags=['network-and-trips'])

@router.get('/network/{dataset}')
def get_network(dataset:Literal['campus','example'],request:Request):
    return request.app.state.store.get(dataset)

@router.put('/network/{dataset}')
def save_network(dataset:Literal['campus','example'],body:Network,request:Request):
    if body.dataset!=dataset:raise HTTPException(422,'场景与数据不一致')
    ids={f['properties']['id'] for f in request.app.state.parking['features']}
    if dataset=='campus' and any(n.kind=='parking' and n.parking_id not in ids for n in body.nodes):
        raise HTTPException(422,'停车入口关联的区域不存在')
    try:return request.app.state.store.save(body)
    except Conflict as e:raise HTTPException(409,str(e))

@router.get('/places')
def places(request:Request,dataset:Literal['campus','example']='campus'):
    g=request.app.state.store.get(dataset)
    return {'dataset':dataset,'is_example':dataset=='example','items':g['nodes'],'revision':g['revision']}

@router.post('/trips/plan')
def plan_trip(body:TripRequest,request:Request):
    g=request.app.state.store.get(body.dataset)
    if not g['nodes']:raise HTTPException(409,'请先录入并保存道路节点和入口')
    if body.dataset=='example':
        status={'mode':'simulated','updated_at':None,'items':[{'id':n['id'],'capacity':n['capacity'],'available':n['available']} for n in g['nodes'] if n['kind']=='parking']}
    else:status=snapshot(request.app.state.store.parking(request.app.state.parking))
    try:result=plan(g,body,{i['id']:i for i in status['items']})
    except ValueError as e:raise HTTPException(422,str(e))
    result['parking_source']={'mode':status['mode'],'updated_at':status['updated_at']}
    return result

class Capacity(BaseModel):
    capacity:int=Field(ge=1,le=100000)

@router.put('/parking/{area_id}/capacity')
def capacity(area_id:str,body:Capacity,request:Request):
    if area_id not in {f['properties']['id'] for f in request.app.state.parking['features']}:raise HTTPException(404,'停车区域不存在')
    request.app.state.store.set_capacity(area_id,body.capacity)
    return {'id':area_id,'capacity':body.capacity,'source':'manual_configuration','verified':False}

@router.get('/vision/history')
def history(request:Request,limit:int=Query(50,ge=1,le=100)):
    return {'items':request.app.state.store.vision_history(limit),'source':'upload_test','is_live':False}
