import hashlib
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix='/parking', tags=['parking'])


def snapshot(collection, now=None):
    now = now or datetime.now(timezone.utc)
    tick = int(now.timestamp()) // 15
    statuses = []
    for feature in collection['features']:
        props = feature['properties']
        # Repeatable within a 15-second window, independent of Python hash seed.
        seed = hashlib.sha256(f"{props['id']}:{tick}".encode()).digest()
        occupied = int.from_bytes(seed[:4], 'big') % (props['capacity'] + 1)
        ratio = occupied / props['capacity']
        statuses.append({
            'id': props['id'], 'capacity': props['capacity'], 'occupied': occupied,
            'available': props['capacity'] - occupied,
            'state': 'full' if ratio >= 1 else 'busy' if ratio >= 0.8 else 'available',
        })
    return {'mode': 'simulated', 'is_example': collection['is_example'],
            'updated_at': now.isoformat(), 'refresh_seconds': 15, 'items': statuses}


@router.get('/areas')
def areas(request: Request):
    return request.app.state.store.parking(request.app.state.parking)


@router.get('/status')
def status(request: Request):
    return snapshot(request.app.state.store.parking(request.app.state.parking))


@router.get('/{area_id}/status')
def area_status(area_id: str, request: Request):
    result = snapshot(request.app.state.store.parking(request.app.state.parking))
    item = next((item for item in result['items'] if item['id'] == area_id), None)
    if item is None:
        raise HTTPException(404, 'Unknown parking area')
    return {**result, 'items': [item]}
