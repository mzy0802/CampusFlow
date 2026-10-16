"""A single capacity and occupancy contract for navigation and dashboards."""
from .parking import snapshot
from .vision_metrics import congestion


def area_states(request):
    collection=request.app.state.store.parking(request.app.state.parking)
    simulated=snapshot(collection)
    observations={o['area_id']:o for o in request.app.state.vision.observations()}
    result=[]
    for f in collection['features']:
        p=f['properties']; status=next(s for s in simulated['items'] if s['id']==p['id'])
        observation=observations.get(p['id'])
        count=(observation or {}).get('two_wheeler',{}).get('count')
        if count is None: count=status['occupied']; observation=None
        metric=congestion(count,p['capacity'])
        result.append({**p,**metric,'occupied':count,'available':max(0,p['capacity']-count),
                       'source':'qwen_estimate' if observation else 'simulated',
                       'updated_at':observation['updated_at'] if observation else simulated['updated_at'],
                       'illegal_count':observation.get('illegal_count') if observation else None,
                       'legal_count':observation.get('legal_count') if observation else None,
                       'unknown_location_count':observation.get('unknown_location_count') if observation else None,
                       'job_id':observation.get('job_id') if observation else None,
                       'geometry':f['geometry']})
    return {'items':result,'is_live':False,'formula':'total_unique_two_wheelers_including_assigned_illegal / map_area_capacity * 100'}
