"""Reproducible morning counterfactual on the saved campus road graph."""
import random
import math
from fastapi import APIRouter, Request, Query, HTTPException
from .navigation import read_data, route, NavigationRequest
from .trip_planner import distance

router=APIRouter(prefix='/simulation',tags=['simulation'])
HOTSPOTS={'修远3东','修远大停车场','修远4北','修远2东','明远1西侧','明远4东北角','明远1中1','明远1中2','明远4南侧','明远4东南2','鸿远2区东','鸿远1区东','鸿远1区北'}


def generate(graph, collection, places, count=600, seed=20261016):
    rng=random.Random(seed)
    dorms=[p for p in places if any(k in p['name'] for k in ('宿舍','公寓')) and not any(k in p['name'] for k in ('教师','安保'))]
    teaching=[p for p in places if '教学楼' in p['name']]
    if not dorms or not teaching or not graph['edges']:raise ValueError('缺少宿舍、教学楼或路网数据')
    areas=[]
    for f in collection['features']:
        ring=f['geometry']['coordinates'][0][:-1]; p=f['properties']
        center={'longitude':sum(v[0] for v in ring)/len(ring),'latitude':sum(v[1] for v in ring)/len(ring)}
        group='明远' if p['name'].startswith('明远') else '鸿远' if p['name'].startswith('鸿远') else '修远'
        choices=[t for t in teaching if group in t['name']]
        goal=min(choices or teaching,key=lambda t:distance(center,t))
        areas.append({**p,**center,'geometry':f['geometry'],'goal':goal,'hotspot':p['name'] in HOTSPOTS})
    if not areas:raise ValueError('没有停车区')
    cache={}; paths={}; excluded=[]
    def path(a,b,mode):
        key=(round(a['longitude'],7),round(a['latitude'],7),round(b['longitude'],7),round(b['latitude'],7),mode)
        if key not in cache:
            try:
                result=route(graph,NavigationRequest(origin={k:a[k] for k in ('longitude','latitude')},destination={k:b[k] for k in ('longitude','latitude')},mode=mode),mode)
                geometry=result['geojson']['geometry']; coords=geometry['coordinates'] if geometry['type']=='LineString' else [geometry['coordinates'],geometry['coordinates']]
                pid=str(len(paths)); paths[pid]={'coordinates':coords,'seconds':max(12,result['duration_minutes']*60),'distance_m':result['distance_m'],'access_m':result['origin_access_distance_m']+result['destination_access_distance_m']}; cache[key]=pid
            except ValueError:cache[key]=None
        return cache[key]
    people=[]; weights=[a['capacity']*(8 if a['hotspot'] else .22) for a in areas]
    demand=[(dorms[i%len(dorms)],rng.choices(areas,weights=weights)[0]) for i in range(count)]
    # Fixed 85% riders, with the walking quota biased toward shorter trips.
    walk_scores=[]
    for i,(origin,target) in enumerate(demand):
        gap=distance(origin,target['goal']);weight=.87 if gap<450 else .45 if gap<900 else .13
        walk_scores.append((rng.random()**(1/weight),i))
    walkers={i for _,i in sorted(walk_scores,reverse=True)[:round(count*.15)]}
    for i,(origin,target) in enumerate(demand):
        mode='walk' if i in walkers else ('bicycle' if rng.random()<.52 else 'electric')
        pid=path(origin,target['goal'] if mode=='walk' else target,'walk' if mode=='walk' else 'bike')
        if pid is None:
            excluded.append({'origin':origin['name'],'area':target['name'],'reason':'路网不可达或距可通行道路超过150米'});continue
        speed=1 if mode!='electric' else 12/16
        seconds=paths[pid]['seconds']*speed
        start=round(rng.triangular(0,max(1,min(1050,1750-seconds)),500 if seconds<1200 else 0),1)
        people.append({'id':i,'origin_id':origin['id'],'origin_name':origin['name'],'destination_id':target['goal']['id'],'destination_name':target['goal']['name'],'mode':mode,'start':start,'area_id':None if mode=='walk' else target['id'],'path':pid,'travel_seconds':seconds})
    riders=[p for p in people if p['mode']!='walk']
    # Coverage strata keep quiet areas occupied too, without inventing a background stock.
    for person, target in zip(riders, areas):
        origin=next(d for d in dorms if d['id']==person['origin_id'])
        pid=path(origin,target,'bike')
        if pid is None:continue
        seconds=paths[pid]['seconds']*(12/16 if person['mode']=='electric' else 1)
        person.update(area_id=target['id'],destination_id=target['goal']['id'],destination_name=target['goal']['name'],path=pid,travel_seconds=seconds,start=min(person['start'],max(0,700-seconds)))
    # One rider owns one vehicle; display count never scales parking demand.
    cohort=1
    load={a['id']:0 for a in areas}; lookup={a['id']:a for a in areas}
    cases={'baseline':[],'guided':[]}
    for p in people:
        base=dict(p); guided=dict(p)
        if p['area_id']:
            a=lookup[p['area_id']]; base['walk_path']=path(a,a['goal'],'walk')
            choices=[b for b in areas if distance(b,a['goal'])<=650 and b['name'][:2]==a['name'][:2]]
            choices.sort(key=lambda b:(load[b['id']]+cohort)/b['capacity']*10+distance(b,a['goal'])/180)
            for b in choices:
                pid=path(next(d for d in dorms if d['id']==p['origin_id']),b,'bike'); tail=path(b,a['goal'],'walk')
                if pid is not None and tail is not None:
                    guided.update(area_id=b['id'],path=pid,walk_path=tail,travel_seconds=paths[pid]['seconds']*(12/16 if p['mode']=='electric' else 1)); break
            load[guided['area_id']]+=cohort
        cases['baseline'].append(base);cases['guided'].append(guided)
    for name, case in cases.items():
        legal={a['id']:0 for a in areas}
        for person in sorted(case,key=lambda p:(p['start']+p['travel_seconds'],p['id'])):
            area=lookup.get(person['area_id'])
            if not area:continue
            habitual=name=='baseline' and area['hotspot'] and (person['id']*17+seed)%100<10
            person['illegal']=habitual or legal[area['id']]+cohort>area['capacity']
            if not person['illegal']:legal[area['id']]+=cohort
    return {'source':'scenario_simulation' ,'is_observed':False,'start_time':'08:00','end_time':'08:30','duration_seconds':1800,'seed':seed,'requested_agents':count,'generated_agents':len(people),'cohort_per_vehicle':round(cohort,5),'dorm_count':len(dorms),'covered_dorms':len({p['origin_id'] for p in people}),'areas':areas,'origins':dorms,'destinations':teaching,'paths':paths,'cases':cases,'excluded':excluded,'network_revision':graph['revision'],'assumptions':{'walk_kmh':4.5,'bicycle_kmh':12,'electric_kmh':16,'initial_occupancy':0,'parking_seconds':18,'dismount_seconds':18,'parking_exit_seconds':24,'max_guided_walk_radius_m':650,'vehicles_per_rider':1},'notice':'情景仿真，非实采流量；相同起点、教学目的地、出发时间和出行方式，仅改变停车分配。每个出行对象代表一人，每个骑行者对应一辆车，非实测人数。路线按保存路网计算，建筑中心到路网的接驳未建模；650米仅为候选直线筛选，步行轨迹来自路网。'}


@router.get('/morning')
def morning(request:Request,count:int=Query(1000,ge=100,le=1000),seed:int=Query(20261016,ge=0,le=2147483647),population:int=Query(4000,ge=100,le=8000)):
    store=request.app.state.store
    try:
        from .traffic_snapshot import scenario_document
        import json
        doc=scenario_document(json.dumps(store.get('campus'),sort_keys=True),json.dumps(store.parking(request.app.state.parking),sort_keys=True),json.dumps(read_data('places.osm.json',{'items':[]})['items'],sort_keys=True),population,seed)
        return {**doc,'render_limit':count,'population':population,'vehicle_count':sum(p['mode']!='walk' for p in doc['cases']['baseline'])}
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
