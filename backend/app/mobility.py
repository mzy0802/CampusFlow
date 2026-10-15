from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=['mobility'])


@router.get('/roads')
def roads():
    return {'type': 'FeatureCollection', 'features': [], 'status': 'not_configured',
            'message': '道路模块预留：等待核验后的道路 GeoJSON。'}


@router.get('/transit')
def transit():
    return {'status': 'not_configured', 'stops': [], 'routes': [],
            'message': '公交模块预留：等待站点、线路和时刻数据。'}


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
        'message': '路径规划尚未接入真实路网与路由引擎。',
    })
