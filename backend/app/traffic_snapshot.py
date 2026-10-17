"""Navigation snapshots derived from the same deterministic agents as the map."""
import copy
import json
from functools import lru_cache
from datetime import datetime, timezone


@lru_cache(maxsize=4)
def scenario_document(graph_json, parking_json, places_json, count, seed):
    from .simulation import generate
    return generate(json.loads(graph_json), json.loads(parking_json), json.loads(places_json), count, seed)


def apply_density(graph, people):
    """Attach each road user to their nearest segment, then apply a density cost."""
    from .navigation import project
    from .trip_planner import distance
    result=copy.deepcopy(graph);nodes={n['id']:n for n in graph['nodes']}
    edges=[e for e in result['edges'] if e['verified']]
    totals={e['id']:{'walk':0,'bike':0} for e in edges}
    grid={};cell=.0005
    for e in edges:
        a,b=nodes[e['source']],nodes[e['target']]
        for x in range(int(min(a['longitude'],b['longitude'])//cell),int(max(a['longitude'],b['longitude'])//cell)+1):
            for y in range(int(min(a['latitude'],b['latitude'])//cell),int(max(a['latitude'],b['latitude'])//cell)+1):
                grid.setdefault((x,y),[]).append(e)
    for point,mode in people:
        x,y=int(point['longitude']//cell),int(point['latitude']//cell)
        nearby={e['id']:e for dx in (-1,0,1) for dy in (-1,0,1) for e in grid.get((x+dx,y+dy),[]) if mode in e['modes']}
        eligible=list(nearby.values()) or [e for e in edges if mode in e['modes']]
        if not eligible:continue
        e=min(eligible,key=lambda e:project(point,nodes[e['source']],nodes[e['target']])[2])
        totals[e['id']][mode]+=1
    for e in edges:
        n=totals[e['id']];length=distance(nodes[e['source']],nodes[e['target']])
        density=(n['walk']+2*n['bike'])/max(3,length/12)
        e['congestion']*=1+min(3,density)
    return result,totals


def snapshot(request,context):
    from .navigation import read_data
    graph=request.app.state.store.get('campus')
    if context is None:return graph,None,None
    collection=request.app.state.store.parking(request.app.state.parking)
    doc=scenario_document(json.dumps(graph,sort_keys=True),json.dumps(collection,sort_keys=True),
                          json.dumps(read_data('places.osm.json',{'items':[]})['items'],sort_keys=True),context.population,context.seed)
    agents=doc['cases'][context.scenario];people=[];all_areas=doc['areas']+doc.get('canteen_areas',[]);loads={a['id']:0 for a in all_areas};illegal=dict(loads)
    def at(path_id,progress):
        from .trip_planner import distance
        coords=doc['paths'][path_id]['coordinates'];lengths=[];total=0
        for a,b in zip(coords,coords[1:]):
            total+=distance({'longitude':a[0],'latitude':a[1]},{'longitude':b[0],'latitude':b[1]});lengths.append(total)
        target=max(0,min(1,progress))*total;before=0
        for i,length in enumerate(lengths):
            if target<=length or i==len(lengths)-1:
                t=(target-before)/(length-before or 1);a,b=coords[i:i+2]
                return {'longitude':a[0]+(b[0]-a[0])*t,'latitude':a[1]+(b[1]-a[1])*t}
            before=length
        return {'longitude':coords[0][0],'latitude':coords[0][1]}
    from .scenario_dynamics import state_at
    for a in agents:
        elapsed=context.time_seconds-a['start'];duration=a['travel_seconds']
        if a['area_id'] and elapsed>=duration+a.get('parking_seconds',18):
            loads[a['area_id']]+=1
            if a.get('illegal'):illegal[a['area_id']]+=1
        first=a.get('leg1_seconds',0)
        if a.get('via_area_id') and first+18<=elapsed<first+a.get('dwell_seconds',0):loads[a['via_area_id']]+=1
        state=state_at(a,context.time_seconds,doc['paths'])
        if state['kind'] in ('moving','walking'):
            mode='walk' if state['kind']=='walking' or a['mode']=='walk' else 'bike'
            people.append((at(state['path'],state['progress']),mode))
    from .building_walk import walking_network
    weighted,counts=apply_density(walking_network(graph),people)
    active_accidents=[e for e in doc.get('accidents',{}).get(context.scenario,[]) if e['start']<=context.time_seconds<=e['end']]
    for edge in weighted['edges']:
        if any(edge['id']==event['road_id'] for event in active_accidents):edge['congestion']*=3.5
    areas=[]
    for a in all_areas:
        n=loads[a['id']]
        areas.append({**a,'count':n,'free':max(0,a['capacity']-n),'percent':round(n/a['capacity']*100,1),
                      'illegal_count':illegal[a['id']],'source':'scenario_simulation','updated_at':datetime.now(timezone.utc).isoformat()})
    return weighted,areas,{'source':'scenario_simulation',**context.model_dump(),'road_users':len(people),'active_accidents':len(active_accidents),
                          'busy_segments':sum(bool(n['walk']+n['bike']) for n in counts.values()),
                          'density_formula':'base_seconds * (1 + min(3, (walkers + 2 * riders) / max(3, segment_m / 12)))',
                          'notice':'按所选时刻的人车位置及停车数量计算；采用当前截面路况，不预测途中未来变化。'}
