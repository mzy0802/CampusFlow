from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(tags=['mobility'])


@router.get('/roads')
def roads(request: Request):
    graph = request.app.state.store.get('campus')
    nodes = {n['id']: n for n in graph['nodes']}
    features = [{'type': 'Feature', 'properties': edge,
                 'geometry': {'type': 'LineString', 'coordinates': [
                     [nodes[key]['longitude'], nodes[key]['latitude']]
                     for key in (edge['source'], edge['target'])]}}
                for edge in graph['edges']]
    return {'type': 'FeatureCollection', 'features': features,
            'status': 'configured' if features else 'not_configured',
            'revision': graph['revision'],
            'message': '已保存的校园路网；仅 verified=true 的道路参与计算。'}


class Coordinate(BaseModel):
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)


class RouteRequest(BaseModel):
    origin: Coordinate
    destination: Coordinate


@router.post('/routing/plan')
def plan_route(body: RouteRequest):
    raise HTTPException(501, detail={
        'code': 'ROUTING_NOT_CONFIGURED',
        'message': '坐标自动吸附尚未实现；请通过 /api/places 选择节点，再调用 /api/trips/plan。',
    })
