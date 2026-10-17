"""Shared spatial crowding and major-road-only accident dynamics.

All comparison metrics come from these trajectories. Incident counts are
configured presentation inputs (4/1); they are not a measured safety benefit.
"""
import bisect
import hashlib
import math
from collections import defaultdict

SX=111320*math.cos(math.radians(34.37));SY=111320
def xy(p):return ((p[0]-108.89)*SX,(p[1]-34.36)*SY)
def geo(p):return [p[0]/SX+108.89,p[1]/SY+34.36]
def cell(p):return (int(p[0]//22),int(p[1]//22))
def project(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy or 1)))
    q=(a[0]+t*dx,a[1]+t*dy);return q,math.dist(p,q)


class Roads:
    def __init__(self,graph):
        from .navigation import read_data
        metadata={f['properties']['id']:f['properties'] for f in read_data('roads.osm.geojson',{'features':[]})['features']}
        cycle_ids={e['id'] for e in read_data('cycleway.owner.json',{'edges':[]})['edges']}
        nodes={n['id']:n for n in graph['nodes']};self.items={};self.grid=defaultdict(list);self.degree=defaultdict(set)
        for e in graph['edges']:
            meta=metadata.get(e['id'],{});highway=meta.get('highway',e.get('highway','residential'))
            name=meta.get('tags',{}).get('name') or meta.get('name') or '通用道路'
            # The named campus avenue is a shared cycle/vehicle corridor even
            # where OSM labels it pedestrian. Do not apply this to other paths.
            if name=='修远大道' and highway=='pedestrian':highway='residential'
            if not e['verified'] or 'bike' not in e['modes'] or e['id'] in cycle_ids or highway not in ('residential','primary','secondary','tertiary','unclassified','living_street'):continue
            a=xy([nodes[e['source']]['longitude'],nodes[e['source']]['latitude']]);b=xy([nodes[e['target']]['longitude'],nodes[e['target']]['latitude']])
            road={**e,'a':a,'b':b,'highway':highway,'name':name}
            self.items[e['id']]=road;self.degree[e['source']].add(e['target']);self.degree[e['target']].add(e['source'])
            for x in range(int(min(a[0],b[0])//55),int(max(a[0],b[0])//55)+1):
                for y in range(int(min(a[1],b[1])//55),int(max(a[1],b[1])//55)+1):self.grid[x,y].append(road)
    def match(self,a,b):
        p=((a[0]+b[0])/2,(a[1]+b[1])/2);ix,iy=int(p[0]//55),int(p[1]//55);best=None;gap=1.1
        for road in {r['id']:r for dx in (-1,0,1) for dy in (-1,0,1) for r in self.grid.get((ix+dx,iy+dy),[])}.values():
            da=(b[0]-a[0],b[1]-a[1]);db=(road['b'][0]-road['a'][0],road['b'][1]-road['a'][1])
            den=math.hypot(*da)*math.hypot(*db)
            if den<.01 or abs(da[0]*db[0]+da[1]*db[1])/den<.985:continue
            _,d=project(p,road['a'],road['b'])
            if d<gap:gap=d;best=road['id']
        return best


class Paths:
    def __init__(self,paths,roads):
        self.paths={};self.roads=roads
        for pid,path in paths.items():
            points=[xy(p) for p in path['coordinates']];lengths=[0]
            for a,b in zip(points,points[1:]):lengths.append(lengths[-1]+math.dist(a,b))
            road_ids=[roads.match(a,b) for a,b in zip(points,points[1:])]
            self.paths[pid]=(points,lengths,road_ids)
    def sample(self,pid,progress):
        points,lengths,ids=self.paths[pid];at=max(0,min(1,progress))*lengths[-1]
        i=max(1,min(len(points)-1,bisect.bisect_left(lengths,at)));t=(at-lengths[i-1])/(lengths[i]-lengths[i-1] or 1)
        a,b=points[i-1],points[i];return (a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t),ids[i-1] if ids else None


def pace_at(pace,elapsed):
    if not pace:return None
    if elapsed<=pace[0][0]:return pace[0][1]
    if elapsed>=pace[-1][0]:return pace[-1][1]
    lo=0;hi=len(pace)-1
    while hi-lo>1:
        m=(lo+hi)//2
        if pace[m][0]<=elapsed:lo=m
        else:hi=m
    t,p=pace[lo];end,q=pace[hi];return p+(q-p)*(elapsed-t)/(end-t or 1)


def state_at(a,time,paths):
    elapsed=time-a['start'];first=a.get('leg1_seconds',0);dwell=a.get('dwell_seconds',0)
    if elapsed<0:return {'kind':'waiting'}
    if a.get('via_path') is not None:
        if elapsed<first:return {'kind':'moving','path':a['via_path'],'progress':pace_at(a.get('leg1_pace'),elapsed) or elapsed/max(1,first),'leg':'canteen'}
        if elapsed<first+dwell:return {'kind':'dining'}
        if elapsed<a['travel_seconds']:return {'kind':'moving','path':a['path'],'progress':pace_at(a.get('travel_pace'),elapsed-first-dwell) or (elapsed-first-dwell)/max(1,a['travel_seconds']-first-dwell)}
    elif elapsed<a['travel_seconds']:return {'kind':'moving','path':a['path'],'progress':pace_at(a.get('travel_pace'),elapsed) or elapsed/max(1,a['travel_seconds'])}
    if a['mode']=='walk':return {'kind':'arrived' if elapsed>=a['travel_seconds']+12 else 'entering'}
    tail=paths.get(a.get('walk_path'));seconds=a.get('walk_seconds',tail['seconds'] if tail else 0);walk=elapsed-a['travel_seconds']-a.get('parking_seconds',18)-42
    if walk<0:return {'kind':'parking'}
    if tail and walk<seconds:return {'kind':'walking','path':a['walk_path'],'progress':pace_at(a.get('walk_pace'),walk) or walk/max(1,seconds)}
    return {'kind':'arrived' if walk>=seconds+12 else 'entering'}


def arrival(a,paths):return a['start']+a['travel_seconds']+(12 if a['mode']=='walk' else a.get('parking_seconds',18)+54+a.get('walk_seconds',paths.get(a.get('walk_path'),{}).get('seconds',0)))


def schedules(a,paths):
    first=a.get('leg1_seconds',0);dwell=a.get('dwell_seconds',0);start=a['start']
    if a.get('via_path') is not None:yield a['via_path'],start,first,a['mode'],a.get('leg1_pace')
    yield a['path'],start+first+dwell,a['travel_seconds']-first-dwell,a['mode'],a.get('travel_pace')
    if a.get('walk_path') is not None:yield a['walk_path'],start+a['travel_seconds']+a.get('parking_seconds',18)+42,a.get('walk_seconds',paths[a['walk_path']]['seconds']),'walk',a.get('walk_pace')


def occupancy(agents,paths,sampler):
    cells=defaultdict(float);vehicles=defaultdict(set)
    for a in agents:
        touched=set()
        for pid,start,duration,mode,profile in schedules(a,paths):
            for offset in range(0,max(1,int(duration)),12):
                time=start+offset
                if time>1800:break
                progress=pace_at(profile,offset) if profile else offset/max(1,duration)
                point,road=sampler.sample(pid,progress);key=(cell(point),int(time//30))
                if key not in touched:cells[key]+=1 if mode=='walk' else 1.4;touched.add(key)
                if mode!='walk' and road:vehicles[road,int(time//30)].add(a['id'])
    return cells,vehicles


def parking_spillback(agents,areas,sampler,cells,vehicles):
    """Overloaded parking entrances obstruct the nearest general road.

    Queue members are real arriving riders, not extra generated vehicles.
    The same capacity and spillback rules apply to both parking strategies.
    """
    lookup={a['id']:a for a in areas};loads=defaultdict(int)
    for a in sorted((a for a in agents if a.get('area_id')),key=lambda a:a['start']+a['travel_seconds']):
        area=lookup.get(a['area_id'])
        if not area:continue
        loads[area['id']]+=1
        excess=max(0,loads[area['id']]/max(1,area['capacity'])-1)
        if excess<=0:continue
        center=xy([area['longitude'],area['latitude']]);options=[]
        for road in sampler.roads.items.values():
            point,gap=project(center,road['a'],road['b'])
            if gap<=110:options.append((gap,road['id'],point))
        if not options:continue
        _,rid,point=min(options);road=sampler.roads.items[rid]
        start=a['start']+a['travel_seconds'];duration=min(720,180+420*excess)
        dx=road['b'][0]-road['a'][0];dy=road['b'][1]-road['a'][1];length=math.hypot(dx,dy) or 1
        touched={cell((point[0]+dx/length*d,point[1]+dy/length*d)) for d in range(-44,45,11)}
        for bucket in range(int(start//30),min(60,int((start+duration)//30))+1):
            vehicles[rid,bucket].add(a['id'])
            for spot in touched:cells[spot,bucket]+=1.4


def accidents_for(vehicles,roads,seed):
    events=[]
    for (road_id,bucket),users in sorted(vehicles.items(),key=lambda item:(-len(item[1]),item[0])):
        if road_id not in roads.items:continue
        n=len(users)
        if n<20:continue
        key=f'{seed}/{road_id}/{bucket}'.encode();u=int.from_bytes(hashlib.sha256(key).digest()[:8],'big')/2**64
        if u>min(.28,.003+max(0,n-20)**1.6*.00022):continue
        road=roads.items[road_id];nodes=[(road['source'],road['a']),(road['target'],road['b'])]
        junctions=[p for node,p in nodes if len(roads.degree[node])>=3]
        point=junctions[0] if junctions else ((road['a'][0]+road['b'][0])/2,(road['a'][1]+road['b'][1])/2)
        start=bucket*30
        if any(math.dist(point,e['_xy'])<55 and abs(start-e['start'])<240 for e in events):continue
        lon,lat=geo(point);duration=150+int(u*1000)%151
        events.append({'id':f'acc{len(events)+1}','road_id':road_id,'longitude':lon,'latitude':lat,'start':start,'end':min(1800,start+duration),'occupancy':n,'kind':'junction' if junctions else 'segment','highway':road['highway'],'road_name':road['name'],'_xy':point,'note':'交通情景事故，非真实事件'})
    return sorted(events,key=lambda e:e['start'])


def teaching_accidents(vehicles,roads,areas,case,seed):
    """Configured presentation incidents: 4 baseline / 1 guided, not predictions."""
    targets=[a for a in areas if a.get('hotspot')]
    if not targets:return []
    candidates=[]
    for (rid,bucket),users in vehicles.items():
        if rid not in roads.items or not users or not 12<=bucket<=48:continue
        road=roads.items[rid];point=((road['a'][0]+road['b'][0])/2,(road['a'][1]+road['b'][1])/2)
        area=min(targets,key=lambda a:math.dist(point,xy([a['longitude'],a['latitude']])))
        gap=math.dist(point,xy([area['longitude'],area['latitude']]))
        if gap>180:continue
        candidates.append((rid,bucket,len(users),point,area['name'][:2],gap))
    events=[]
    desired=[('修远',540),('明远',780),('鸿远',990),('修远',1230)] if case=='baseline' else [('明远',900)]
    for group,time in desired:
        options=sorted(candidates,key=lambda c:(c[4]!=group,abs(c[1]*30-time)/30+c[5]/25-min(c[2],60)/12,c[0]))
        chosen=next((c for c in options if not any(math.dist(c[3],e['_xy'])<90 for e in events)),None)
        if chosen is None:continue
        rid,bucket,n,point,g,gap=chosen;road=roads.items[rid];lon,lat=geo(point)
        events.append({'id':f'demo-{case}-{len(events)+1}','road_id':rid,'longitude':lon,'latitude':lat,'start':bucket*30,'end':bucket*30+120,'occupancy':n,'kind':'segment','highway':road['highway'],'road_name':road['name'],'teaching_group':g,'source':'configured_demo','_xy':point,'note':'按展示需求配置事故数量，非概率预测或真实事故'})
    return sorted(events,key=lambda e:e['start'])


def corridor_pressure(agents,paths,sampler,cells):
    """Include parallel-lane and pedestrian interference in Xiuyuan corridor load."""
    roads=[r for r in sampler.roads.items.values() if r['name']=='修远大道'];users=defaultdict(set)
    for a in agents:
        for pid,start,duration,mode,profile in schedules(a,paths):
            for offset in range(0,max(1,int(duration)),12):
                time=start+offset
                if time>=1800:break
                p,_=sampler.sample(pid,pace_at(profile,offset) if profile else offset/max(1,duration))
                options=[(project(p,r['a'],r['b'])[1],r['id'],r) for r in roads]
                if not options:continue
                gap,rid,road=min(options,key=lambda x:x[0])
                if gap>32:continue
                bucket=int(time//30);users[rid,bucket].add(a['id'])
    for (rid,bucket),ids in users.items():
        road=sampler.roads.items[rid]
        for fraction in (0,.25,.5,.75,1):
            point=(road['a'][0]+fraction*(road['b'][0]-road['a'][0]),road['a'][1]+fraction*(road['b'][1]-road['a'][1]))
            cells[cell(point),bucket]=max(cells.get((cell(point),bucket),0),len(ids)*.8)
    return users


def integrate(a,pid,base,start,cells,events,sampler):
    t=0.;p=0.;points=[[0.,0.]];last=0
    while p<1:
        point,road=sampler.sample(pid,p);now=start+t;n=cells.get((cell(point),min(60,int(now//30))),0)
        crowd=max(.22,1/(1+(max(0,n-8)/15)**1.5));wave=1+.12*math.sin(now/19+a['id']*.71)+.06*math.sin(now/7.3+a['id']*1.3)
        factor=max(.15,crowd*wave)
        for event in events:
            if road and event['start']<=now<=event['end'] and math.dist(point,event['_xy'])<28:factor=min(factor*.65,.23 if int(now//12)%4==0 else .32)
        p=min(1,p+6*factor/max(12,base));t+=6
        if t-last>=18 or p>=1:points.append([t,round(p,5)]);last=t
    return t,points


def timeline_for(agents,paths):
    output=[];groups=['食堂','修远','明远','鸿远']
    for time in range(0,1801,30):
        zones={g:{'incoming':0,'outgoing':0,'active':0,'arrived':0,'dorm_source':0,'canteen_source':0} for g in groups}
        for a in agents:
            start=a['start'];first=a.get('leg1_seconds',0);dwell=a.get('dwell_seconds',0);via=a.get('via_path') is not None;end=arrival(a,paths);g=a['destination_name'][:2]
            if via:
                reach=start+first;leave=reach+dwell
                if time-60<reach<=time:zones['食堂']['incoming']+=1
                if time-60<leave<=time:zones['食堂']['outgoing']+=1
                if start<=time<leave:zones['食堂']['active']+=1
                if start<=time<leave:continue
            if a.get('board_at') and time-60<start<=time:zones['食堂']['outgoing']+=1
            if g not in zones:continue
            if time-60<end<=time:zones[g]['incoming']+=1
            if end<=time:zones[g]['arrived']+=1
            if start<=time<end:
                zones[g]['active']+=1
                if a.get('board_at') or via and time>=start+first+dwell:zones[g]['canteen_source']+=1
                else:zones[g]['dorm_source']+=1
        output.append({'time':time,'zones':zones})
    return output


def apply_motion(cases,paths,graph,seed,areas=()):
    roads=Roads(graph);sampler=Paths(paths,roads);events={};metrics={};timeline={}
    for name,agents in cases.items():
        cells,_=occupancy(agents,paths,sampler)
        corridor_pressure(agents,paths,sampler,cells)
        baselines={a['id']:dict(a) for a in agents}
        def run_motion(items):
            for a in agents:
                base_agent=baselines[a['id']];a['travel_seconds']=base_agent['travel_seconds']
                if 'leg1_seconds' in base_agent:a['leg1_seconds']=base_agent['leg1_seconds']
                first=a.get('leg1_seconds',0);dwell=a.get('dwell_seconds',0);base=a['travel_seconds'];free=base
                if a.get('via_path') is not None:
                    duration,pace=integrate(a,a['via_path'],first,a['start'],cells,items,sampler);a['leg1_seconds']=duration;a['leg1_pace']=pace
                    second,pace=integrate(a,a['path'],base-first-dwell,a['start']+duration+dwell,cells,items,sampler);a['travel_seconds']=duration+dwell+second;a['travel_pace']=pace
                else:a['travel_seconds'],a['travel_pace']=integrate(a,a['path'],base,a['start'],cells,items,sampler)
                a['free_flow_seconds']=round(free,1)
            capacities={area['id']:area['capacity'] for area in areas};arrivals_by_area=defaultdict(int)
            for a in sorted((a for a in agents if a['area_id']),key=lambda a:(a['start']+a['travel_seconds'],a['id'])):
                aid=a['area_id'];arrivals_by_area[aid]+=1
                pressure=max(0,arrivals_by_area[aid]/max(1,capacities.get(aid,100))-.75)
                a['parking_queue_seconds']=round(min(720,360*pressure*pressure),1)
                a['parking_seconds']=18+a['parking_queue_seconds']
            for a in agents:
                if a.get('walk_path') is not None:
                    tail=paths[a['walk_path']]['seconds'];a['walk_seconds'],a['walk_pace']=integrate(a,a['walk_path'],tail,a['start']+a['travel_seconds']+a.get('parking_seconds',18)+42,cells,items,sampler);a['free_flow_seconds']+=tail
                a['delay_seconds']=round(max(0,a['travel_seconds']+a.get('walk_seconds',0)+a.get('parking_queue_seconds',0)-a['free_flow_seconds']),1)
        # First observe vehicles after spatial crowding; then discover incidents
        # on those actual timed road traversals and apply their additional delay.
        run_motion([])
        _,vehicles=occupancy(agents,paths,sampler)
        parking_spillback(agents,areas,sampler,cells,vehicles)
        items=teaching_accidents(vehicles,roads,areas,name,seed)
        corridor=corridor_pressure(agents,paths,sampler,cells)
        display_vehicles={key:set(value) for key,value in vehicles.items()}
        for key,users in corridor.items():display_vehicles.setdefault(key,set()).update(users)
        run_motion(items)
        arrivals=[arrival(a,paths)-a['start'] for a in agents];riders=[a for a in agents if a['mode']!='walk']
        metrics[name]={'trip':sum(arrivals)/max(1,len(arrivals))/60,'walk':sum(a.get('walk_seconds',0) for a in riders)/max(1,len(riders))/60,'accidents':len(items),'congested':len({r for (r,k),users in vehicles.items() if len(users)>=14}),'delay_minutes':sum(a['delay_seconds'] for a in agents)/max(1,len(agents))/60,'arrived':sum(arrival(a,paths)<=1800 for a in agents),'over':0}
        pressure=[]
        for rid in sorted({r for (r,k),users in display_vehicles.items() if len(users)>=12}):
            road=roads.items[rid];windows=[]
            for bucket in range(60):
                n=len(display_vehicles.get((rid,bucket),()))
                threshold=12 if road['name']=='修远大道' else 22
                if n<threshold:continue
                if windows and windows[-1]['end']==bucket*30:
                    windows[-1]['end']=(bucket+1)*30;windows[-1]['vehicles']=max(windows[-1]['vehicles'],n)
                else:windows.append({'start':bucket*30,'end':(bucket+1)*30,'vehicles':n})
            for window in windows:pressure.append({**window,'road_id':rid,'road_name':road['name'],'coordinates':[geo(road['a']),geo(road['b'])]})
        metrics[name]['congestion_windows']=pressure
        timeline[name]=timeline_for(agents,paths)
        events[name]=[{k:v for k,v in e.items() if k!='_xy'} for e in items]
    return events,metrics,timeline
