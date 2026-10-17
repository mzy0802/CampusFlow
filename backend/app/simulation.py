"""Reproducible morning counterfactual on the saved campus road graph."""
import random
from fastapi import APIRouter, Request, Query, HTTPException
from .navigation import read_data, route, NavigationRequest
from .trip_planner import distance

router=APIRouter(prefix='/simulation',tags=['simulation'])
HOTSPOTS={'修远3东','修远大停车场','修远4北','修远2东','明远1西侧','明远4东北角','明远1中1','明远1中2','明远4南侧','明远4东南2','鸿远2区东','鸿远1区东','鸿远1区北'}
# Share of riders/walkers starting at a canteen or stopping by the nearest one.
CANTEEN_START_SHARE=.13
CANTEEN_STOP_SHARE=.22


def generate(graph, collection, places, count=600, seed=20261016):
    rng=random.Random(seed)
    dorms=[p for p in places if any(k in p['name'] for k in ('宿舍','公寓')) and not any(k in p['name'] for k in ('教师','安保'))]
    teaching=[p for p in places if '教学楼' in p['name']]
    canteens=sorted((p for p in places if any(k in p['name'] for k in ('餐厅','食堂'))),key=lambda p:str(p['id']))
    if not dorms or not teaching or not graph['edges']:raise ValueError('缺少宿舍、教学楼或路网数据')
    areas=[];canteen_areas=[]
    for f in collection['features']:
        ring=f['geometry']['coordinates'][0][:-1]; p=f['properties']
        center={'longitude':sum(v[0] for v in ring)/len(ring),'latitude':sum(v[1] for v in ring)/len(ring)}
        if p.get('zone')=='canteen' or p.get('import_batch')=='canteen-20261017':
            canteen_areas.append({**p,**center,'geometry':f['geometry']});continue
        group='明远' if p['name'].startswith('明远') else '鸿远' if p['name'].startswith('鸿远') else '修远'
        choices=[t for t in teaching if group in t['name']]
        goal=min(choices or teaching,key=lambda t:distance(center,t))
        areas.append({**p,**center,'geometry':f['geometry'],'goal':goal,'hotspot':p['name'] in HOTSPOTS})
    if not areas:raise ValueError('没有停车区')
    def nearest_canteen(point):return min(canteens,key=lambda c:distance(point,c)) if canteens else None
    def canteen_area(canteen):
        if not canteen or not canteen_areas:return None
        return min(canteen_areas,key=lambda a:distance(canteen,a))['id']
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
    people=[]
    # Teaching demand is a separate input from parking popularity. Otherwise
    # Hongyuan's large capacities and three hotspots attract most of campus.
    shares={'修远':.50,'明远':.30,'鸿远':.20}
    raw=[a['capacity']*(8 if a['hotspot'] else .22) for a in areas]
    totals={g:sum(w for a,w in zip(areas,raw) if a['name'].startswith(g)) for g in shares}
    weights=[w*shares.get(a['name'][:2],1)/max(1,totals.get(a['name'][:2],1)) for a,w in zip(areas,raw)]
    # Exact destination quotas: 800 Hongyuan students in the default 4000.
    groups=['修远']*round(count*.50)+['鸿远']*round(count*.20)
    groups+=['明远']*(count-len(groups));rng.shuffle(groups)
    demand=[]
    for i,g in enumerate(groups):
        candidates=[a for a in areas if a['name'].startswith(g)]
        demand.append((dorms[i%len(dorms)],rng.choices(candidates,weights=[a['capacity']*(8 if a['hotspot'] else .22) for a in candidates])[0]))
    # Fixed 85% riders, with the walking quota biased toward shorter trips.
    walk_scores=[]
    for i,(origin,target) in enumerate(demand):
        gap=distance(origin,target['goal']);weight=.87 if gap<450 else .45 if gap<900 else .13
        walk_scores.append((rng.random()**(1/weight),i))
    walkers={i for _,i in sorted(walk_scores,reverse=True)[:round(count*.15)]}
    for i,(origin,target) in enumerate(demand):
        mode='walk' if i in walkers else ('bicycle' if rng.random()<.52 else 'electric')
        ride='walk' if mode=='walk' else 'bike'
        speed=1 if mode!='electric' else 12/16
        canteen=None;behavior=None
        if canteens:
            roll=rng.random()
            if roll<CANTEEN_START_SHARE:behavior='start'
            elif roll<CANTEEN_START_SHARE+CANTEEN_STOP_SHARE:behavior='stop'
            if behavior:canteen=nearest_canteen(origin)
        board=canteen if canteen else origin
        pid=path(board,target['goal'] if mode=='walk' else target,ride)
        if pid is None:
            excluded.append({'origin':origin['name'],'area':target['name'],'reason':'路网不可达或距可通行道路超过150米'});continue
        leg2=paths[pid]['seconds']*speed
        via_path=None;leg1=0.;dwell=0.;via_name=None;via_area=None
        if behavior=='stop':
            pid1=path(origin,canteen,ride)
            if pid1 is not None:
                leg1=paths[pid1]['seconds']*speed;dwell=round(rng.triangular(240,540,360),1)
                if leg1+dwell+leg2>1500:leg1=0.;dwell=0.;behavior=None
                else:via_path=pid1;via_name=canteen['name'];via_area=canteen_area(canteen) if mode!='walk' else None
            else:behavior=None
            if behavior is None:
                board=origin;pid=path(origin,target['goal'] if mode=='walk' else target,ride)
                if pid is None:excluded.append({'origin':origin['name'],'area':target['name'],'reason':'食堂经停取消后直达路网不可达'});continue
                leg2=paths[pid]['seconds']*speed
        seconds=leg1+dwell+leg2
        start=round(rng.triangular(0,max(1,min(1050,1750-seconds)),500 if seconds<1200 else 0),1)
        person={'id':i,'origin_id':origin['id'],'origin_name':origin['name'],'destination_id':target['goal']['id'],'destination_name':target['goal']['name'],'mode':mode,'start':start,'area_id':None if mode=='walk' else target['id'],'path':pid,'travel_seconds':seconds,'_o':board}
        if behavior=='start':person.update(board_at=canteen['name'],dorm_id=origin['id'],dorm_name=origin['name'],origin_id=canteen['id'],origin_name=canteen['name'])
        if via_path is not None:person.update(via_path=via_path,leg1_seconds=round(leg1,1),dwell_seconds=dwell,via_name=via_name,via_area_id=via_area)
        people.append(person)
    riders=[p for p in people if p['mode']!='walk']
    # Coverage strata keep quiet areas occupied too, without inventing a background stock.
    coverage_used=set()
    for target in areas:
        person=next((p for p in riders if p['id'] not in coverage_used and p['destination_name'].startswith(target['name'][:2])),None)
        if person is None:continue
        coverage_used.add(person['id'])
        pid=path(person['_o'],target,'bike')
        if pid is None:continue
        seconds=paths[pid]['seconds']*(12/16 if person['mode']=='electric' else 1)
        extra=(person.get('leg1_seconds',0) or 0)+(person.get('dwell_seconds',0) or 0)
        person.update(area_id=target['id'],destination_id=target['goal']['id'],destination_name=target['goal']['name'],path=pid,travel_seconds=extra+seconds,start=min(person['start'],max(0,700-seconds)))
    # One rider owns one vehicle; display count never scales parking demand.
    cohort=1
    load={a['id']:0 for a in areas}; lookup={a['id']:a for a in areas}
    cases={'baseline':[],'guided':[]}
    for p in people:
        base=dict(p); guided=dict(p)
        if p['area_id']:
            a=lookup[p['area_id']]; base['walk_path']=path(a,a['goal'],'walk')
            choices=[b for b in areas if load[b['id']]<b['capacity']]
            choices.sort(key=lambda b:(distance(b,a['goal'])>800, distance(b,a['goal'])/75*1.8+distance(p['_o'],b)/200+((load[b['id']]+1)/b['capacity'])**4*1.5))
            for b in choices:
                pid=path(p['_o'],b,'bike'); tail=path(b,a['goal'],'walk')
                if pid is not None and tail is not None:
                    extra=(p.get('leg1_seconds',0) or 0)+(p.get('dwell_seconds',0) or 0)
                    guided.update(area_id=b['id'],path=pid,walk_path=tail,travel_seconds=extra+paths[pid]['seconds']*(12/16 if p['mode']=='electric' else 1)); break
            if load[guided['area_id']]>=lookup[guided['area_id']]['capacity']:
                raise ValueError('当前需求超过可达停车容量，请减少出行人口或补充可达停车区')
            load[guided['area_id']]+=cohort
        base.pop('_o',None);guided.pop('_o',None)
        cases['baseline'].append(base);cases['guided'].append(guided)
    from .scenario_dynamics import apply_motion
    accidents,metrics,timeline=apply_motion(cases,paths,graph,seed,areas)
    for name, case in cases.items():
        legal={a['id']:0 for a in areas}
        for person in sorted(case,key=lambda p:(p['start']+p['travel_seconds'],p['id'])):
            area=lookup.get(person['area_id'])
            if not area:continue
            habitual=name=='baseline' and area['hotspot'] and (person['id']*17+seed)%100<10
            person['illegal']=habitual or legal[area['id']]+cohort>area['capacity']
            if not person['illegal']:legal[area['id']]+=cohort
        assigned={a['id']:sum(p['area_id']==a['id'] for p in case) for a in areas}
        metrics[name]['over']=sum(assigned[a['id']]>a['capacity'] for a in areas)
    return {'source':'scenario_simulation' ,'is_observed':False,'start_time':'08:00','end_time':'08:30','duration_seconds':1800,'seed':seed,'requested_agents':count,'generated_agents':len(people),'cohort_per_vehicle':round(cohort,5),'dorm_count':len(dorms),'covered_dorms':len({p.get('dorm_id',p['origin_id']) for p in people}),'areas':areas,'canteens':[{'id':c['id'],'name':c['name'],'longitude':c['longitude'],'latitude':c['latitude']} for c in canteens],'canteen_areas':canteen_areas,'origins':dorms,'destinations':teaching,'paths':paths,'cases':cases,'accidents':accidents,'metrics':metrics,'timeline':timeline,'excluded':excluded,'network_revision':graph['revision'],'assumptions':{'walk_kmh':4.5,'bicycle_kmh':12,'electric_kmh':16,'initial_occupancy':0,'parking_seconds':18,'parking_queue_seconds':'min(720,360*max(0,arrival_count/capacity-.75)^2)','dismount_seconds':18,'parking_exit_seconds':24,'max_guided_walk_radius_m':800,'teaching_demand_shares':shares,'guided_capacity_constraint':'strict; no overflow assigned','vehicles_per_rider':1,'canteen_start_share':CANTEEN_START_SHARE,'canteen_stopover_share':CANTEEN_STOP_SHARE,'canteen_dwell_seconds':'240-540三角分布','slowdown':'22米空间网格人车密度缓行，包含个体速度波动；不压缩行程时间','accident':'展示配置01四起/02一起，教学区附近有车流的通用道路；28米内减速至自由速度23%—32%，非真实事故预测'},'notice':'情景仿真，非实采流量；相同起点、教学目的地、出发时间和出行方式，仅改变停车分配。每个出行对象代表一人，每个骑行者对应一辆车，非实测人数。路线按保存路网计算，建筑中心到路网的接驳未建模；优先800米内可达空位，容量严格约束，必要时跨教学片区停车；步行轨迹来自路网。食堂经停、缓行与事故均为情景模型，非实测或真实事件。'}


@router.get('/morning')
def morning(request:Request,count:int=Query(1000,ge=100,le=1000),seed:int=Query(20261016,ge=0,le=2147483647),population:int=Query(4000,ge=100,le=8000)):
    store=request.app.state.store
    try:
        from .traffic_snapshot import scenario_document
        import json
        doc=scenario_document(json.dumps(store.get('campus'),sort_keys=True),json.dumps(store.parking(request.app.state.parking),sort_keys=True),json.dumps(read_data('places.osm.json',{'items':[]})['items'],sort_keys=True),population,seed)
        return {**doc,'render_limit':count,'population':population,'vehicle_count':sum(p['mode']!='walk' for p in doc['cases']['baseline'])}
    except ValueError as exc:raise HTTPException(422,str(exc)) from None
