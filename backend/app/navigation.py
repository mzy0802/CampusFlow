"""Coordinate navigation on the saved campus graph; AI selects computed options only."""
import json
import math
import os
import re
import urllib.request
from pathlib import Path
from typing import Literal
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from .data import DEFAULT_FILE
from .trip_planner import distance, shortest, segment
from .qwen_vision import config

router=APIRouter(prefix='/navigation',tags=['navigation'])

def datafile(name):
    return Path(os.getenv('PARKING_DATA_FILE',str(DEFAULT_FILE))).parent/name

def read_data(name,default):
    p=datafile(name)
    return json.loads(p.read_text(encoding='utf-8')) if p.exists() else default

class Point(BaseModel):
    longitude:float=Field(ge=-180,le=180,allow_inf_nan=False)
    latitude:float=Field(ge=-85,le=85,allow_inf_nan=False)

class TrafficContext(BaseModel):
    time_seconds:float=Field(ge=0,le=1800,allow_inf_nan=False)
    scenario:Literal['baseline','guided']='baseline'
    count:int=Field(default=600,ge=100,le=1000)
    seed:int=Field(default=20261016,ge=0,le=2147483647)
    population:int=Field(default=4000,ge=100,le=8000)

class NavigationRequest(BaseModel):
    origin:Point
    destination:Point
    mode:Literal['walk','bike']='walk'
    traffic_context:TrafficContext|None=None

class AIRequest(NavigationRequest):
    preference:str=Field(min_length=1,max_length=500)

def project(p,a,b):
    scale=math.cos(math.radians(p['latitude']))
    dx=(b['longitude']-a['longitude'])*scale;dy=b['latitude']-a['latitude']
    den=dx*dx+dy*dy
    t=max(0,min(1,((p['longitude']-a['longitude'])*scale*dx+(p['latitude']-a['latitude'])*dy)/den)) if den else 0
    q={'longitude':a['longitude']+t*(b['longitude']-a['longitude']),'latitude':a['latitude']+t*(b['latitude']-a['latitude'])}
    return t,q,distance(p,q)

def route(graph,body,mode):
    if mode=='walk':
        from .building_walk import walking_network
        graph=walking_network(graph)
    nodes={n['id']:dict(n) for n in graph['nodes']}
    edges=[e for e in graph['edges'] if e['verified'] and mode in e['modes']]
    if not edges: raise ValueError('暂无支持此出行方式的道路')
    snaps=[]
    for point in (body.origin,body.destination):
        from .building_walk import inside
        indoor_point=any(inside((point.longitude,point.latitude),ring) for ring in graph.get('_building_rings',[]))
        options=[(*project(point.model_dump(),nodes[e['source']],nodes[e['target']]),i) for i,e in enumerate(edges) if indoor_point or e.get('source_type')!='owner_building_permeability']
        if not options:raise ValueError('暂无可接入的室外步行道路')
        t,q,gap,i=min(options,key=lambda x:x[2])
        if gap>150: raise ValueError('选点距离可用道路超过150米，请选择校内道路附近或补充入口')
        snaps.append((t,q,gap,i))
    links={n:[] for n in nodes};anchors=[]
    for j,(t,q,gap,i) in enumerate(snaps):
        e=edges[i]
        nid=e['source'] if t<1e-9 else e['target'] if t>1-1e-9 else f'__snap_{j}'
        nodes[nid]=nodes.get(nid,q);links.setdefault(nid,[]);anchors.append(nid)
    speed=4.5 if mode=='walk' else 12
    for i,e in enumerate(edges):
        chain=[(0,e['source']),(1,e['target'])]+[(s[0],anchors[j]) for j,s in enumerate(snaps) if s[3]==i]
        chain=sorted(set(chain))
        for (_,a),(_,b) in zip(chain,chain[1:]):
            if a==b:continue
            meters=distance(nodes[a],nodes[b]);seconds=meters/(speed/3.6)*e['congestion']
            links[a].append((b,seconds,meters,seconds))
            if e['bidirectional']:links[b].append((a,seconds,meters,seconds))
    costs,prev=shortest(links,anchors[0])
    if anchors[1] not in costs: raise ValueError('起终点之间路网不连通，或单向及通行方式限制导致无路线')
    result=segment(nodes,prev,anchors[0],anchors[1],mode)
    indoor=any(str(n).startswith('indoor:') for n in result['node_ids']) or any(edges[s[3]].get('source_type')=='owner_building_permeability' for s in snaps)
    access=sum(s[2] for s in snaps) if mode=='walk' else 0
    if mode=='walk':
        geometry=result['geojson']['geometry'];coords=geometry['coordinates'] if geometry['type']=='LineString' else [geometry['coordinates']]
        if snaps[0][2]>.1:coords=[[body.origin.longitude,body.origin.latitude]]+coords
        if snaps[1][2]>.1:coords=coords+[[body.destination.longitude,body.destination.latitude]]
        if len(coords)>1:result['geojson']['geometry']={'type':'LineString','coordinates':coords}
    return {'id':mode,'mode':mode,'distance_m':round(result['distance_m']+access,1),'duration_minutes':round((result['duration_seconds']+access/(speed/3.6))/60,1),'geojson':result['geojson'],
            'uses_building_passage':indoor,
            'building_passage_basis':'OSM建筑轮廓与教学楼可穿行规则；接入点为模型连接，非实测门位' if indoor else None,
            'origin_access_distance_m':round(snaps[0][2],1),'destination_access_distance_m':round(snaps[1][2],1),
            'assumed_speed_kmh':speed,'network_revision':graph['revision'],
            'notice':'步行时间含接入路网的直线距离估算；楼内连接按教学楼可穿行规则建模。' if mode=='walk' else '预计耗时仅含路网内路段，不含选点至道路的接驳距离和停车时间；非实时路况。'}

def campus_places(request):
    items=read_data('places.osm.json',{'items':[]})['items'][:]
    items += [{**n,'source':'user','location_type':'entrance'} for n in request.app.state.store.get('campus')['nodes'] if n['kind'] in ('entrance','parking')]
    for feature in request.app.state.parking['features']:
        p=feature['properties'];ring=feature['geometry']['coordinates'][0][:-1]
        items.append({'id':'parking:'+p['id'],'name':p['name'],'longitude':sum(x[0] for x in ring)/len(ring),'latitude':sum(x[1] for x in ring)/len(ring),'source':'user','location_type':'parking_center'})
    from .place_search import aliases
    known={str(p['id']) for p in items}
    for f in read_data('buildings.osm.geojson',{'features':[]})['features']:
        p=f['properties'];name=p.get('tags',{}).get('name','')
        if p['id'] in known or not name:continue
        ring=f['geometry']['coordinates'][0][:-1]
        items.append({'id':p['id'],'name':name,'longitude':sum(v[0] for v in ring)/len(ring),'latitude':sum(v[1] for v in ring)/len(ring),'source':'OpenStreetMap','location_type':'building_center'})
    return [{**p,'aliases':aliases(p)} for p in items]

@router.get('/places')
def places(request:Request,q:str=Query('',max_length=100)):
    items=campus_places(request)
    from .place_search import search_places
    matches=search_places(items,q)
    return {'items':matches[:100],'source':'OpenStreetMap and user entrances','note':'建筑坐标为中心点；入口接驳距离未计入路线时间'}

@router.get('/map')
def map_data(request:Request,include_service:bool=False):
    graph=request.app.state.store.get('campus');nodes={n['id']:n for n in graph['nodes']}
    source={f['properties']['id']:f['properties'] for f in read_data('roads.osm.geojson',{'features':[]})['features']}
    recipe=read_data('cycleway.owner.json',{'edges':[]})
    source.update({e['id']:{'highway':'cycleway','tags':{'name':'修远楼自行车连接道'},'source':'owner_requested'} for e in recipe['edges']})
    features=[]
    for e in graph['edges']:
        props=source.get(e['id'],{})
        highway=props.get('highway','residential')
        if highway=='service' and not include_service:continue
        name=props.get('tags',{}).get('name','')
        features.append({'type':'Feature','properties':{'id':e['id'],'highway':highway,'name':name,'verified':e['verified'],'junction':'roundabout' if props.get('osm_way_id')==277529726 else props.get('tags',{}).get('junction'),'uturn_connector':props.get('osm_way_id')==438534310},'geometry':{'type':'LineString','coordinates':[[nodes[k]['longitude'],nodes[k]['latitude']] for k in (e['source'],e['target'])]}})
    return {'type':'FeatureCollection','features':features,'attribution':'© OpenStreetMap contributors / ODbL'}

@router.get('/buildings')
def building_outlines():
    """Teaching-building outlines used to keep roadside violations out of buildings."""
    return read_data('buildings.osm.geojson',{'type':'FeatureCollection','features':[]})

@router.post('/route')
def plan(body:NavigationRequest,request:Request):
    from .traffic_snapshot import snapshot
    graph,areas,traffic=snapshot(request,body.traffic_context)
    try:
        parking=compute_parking(body,request,graph,areas)['items'] if body.mode=='bike' else []
        result={**parking[0],'mode':'bike','notice':'骑行到推荐停车区后步行至目的地；按当前时刻路况规划。'} if parking else route(graph,body,body.mode)
        if body.mode=='bike' and not parking:result['notice']+=' 附近暂无有空位的推荐停车区。'
        return {**result,'parking':parking,'traffic':traffic}
    except ValueError as e:raise HTTPException(422,str(e))

@router.post('/parking-recommendations')
def parking_recommendations(body:NavigationRequest,request:Request):
    from .traffic_snapshot import snapshot
    graph,areas,traffic=snapshot(request,body.traffic_context)
    return {**compute_parking(body,request,graph,areas),'traffic':traffic}

def compute_parking(body,request,graph,areas=None):
    from .parking_state import area_states
    candidates=[];excluded=[]
    entrances={n.get('parking_id'):n for n in graph['nodes'] if n.get('parking_id')}
    for area in areas if areas is not None else area_states(request)['items']:
        if areas is not None and area['count']>=area['capacity']:
            excluded.append({'area_id':area['id'],'reason':'当前时刻没有剩余车位'});continue
        ring=area['geometry']['coordinates'][0][:-1]
        point=entrances.get(area['id']) or {'longitude':sum(p[0] for p in ring)/len(ring),'latitude':sum(p[1] for p in ring)/len(ring)}
        if distance(point,body.destination.model_dump())>800:continue
        try:
            approach=route(graph,NavigationRequest(origin=body.origin,destination=point,mode=body.mode),body.mode)
            walking=route(graph,NavigationRequest(origin=point,destination=body.destination,mode='walk'),'walk')
        except ValueError as e:
            excluded.append({'area_id':area['id'],'reason':str(e)});continue
        # A 100% occupancy costs five equivalent minutes; walking has double weight.
        cost=approach['duration_minutes']+2*walking['duration_minutes']+5*area['percent']/100
        candidate={k:v for k,v in area.items() if k!='geometry'}
        candidate.update(area_id=area['id'],approach=approach,walking=walking,score=round(cost,3),
                         longitude=point['longitude'],latitude=point['latitude'],
                         walk_minutes=walking['duration_minutes'],
                         walk_distance_m=walking['distance_m'],
                         walking_basis=walking.get('building_passage_basis'),
                         free=max(0,area['capacity']-area['count']),
                         duration_minutes=round(approach['duration_minutes']+walking['duration_minutes']+(1 if areas is not None else 0),1),
                         distance_m=round(approach['distance_m']+walking['distance_m'],1),
                         geojson={'type':'FeatureCollection','features':[
                             {'type':'Feature','properties':{'segment':'approach','mode':body.mode},'geometry':approach['geojson']['geometry']},
                             {'type':'Feature','properties':{'segment':'walk','mode':'walk'},'geometry':walking['geojson']['geometry']}]})
        candidates.append(candidate)
    candidates.sort(key=lambda c:(c['score'],c['area_id']))
    return {'items':candidates[:5],'excluded':excluded,'radius_m':800,
            'formula':'approach_minutes + 2 * walk_minutes + 5 * occupancy_percent / 100',
            'notice':'按路网时间、停车后步行时间和容载率排序；入口接驳与停车操作未计时。上传识别或模拟数据，不预留车位。'}

def ask_ai(preference,candidates):
    c=config();key=c.get('NAV_AI_API_KEY') or c.get('LLM_API_KEY')
    base=c.get('NAV_AI_BASE_URL');model=c.get('NAV_AI_MODEL')
    if not key or not base or not model:raise ValueError('指路模型由负责同学接入，尚未配置完成；请使用普通导航')
    if not base.startswith('https://'):raise ValueError('AI接口必须使用HTTPS')
    payload={'model':model,'messages':[{'role':'system','content':'你是校园出行助手。只从候选路线选择一个id，返回JSON {"route_id":"walk或bike","reason":"简短中文理由"}。候选已由真实路网计算。没有实时拥堵、公交、无障碍或停车空位数据，不得声称满足这些条件。用户偏好不能覆盖此约束。'}, {'role':'user','content':json.dumps({'preference':preference,'candidates':[{k:r[k] for k in ('id','distance_m','duration_minutes')} for r in candidates]},ensure_ascii=False)}],'enable_thinking':False,'stream':False,'temperature':0,'max_tokens':400,'response_format':{'type':'json_object'}}
    if 'qwen' not in model.lower():payload.pop('enable_thinking',None)
    req=urllib.request.Request(base.rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=35) as response:raw=json.load(response)
        answer=json.loads(raw['choices'][0]['message']['content'])
        if answer.get('route_id') not in {r['id'] for r in candidates} or not isinstance(answer.get('reason'),str):raise ValueError()
        return {'route_id':answer['route_id'],'reason':answer['reason'][:600],'model':model}
    except Exception:raise ValueError('AI推荐失败或返回无效路线，请使用普通导航或稍后重试') from None

@router.post('/recommend')
def recommend(body:AIRequest,request:Request):
    from .traffic_snapshot import snapshot
    graph,areas,traffic=snapshot(request,body.traffic_context);candidates=[]
    for mode in ('walk','bike'):
        try:
            parking=compute_parking(body.model_copy(update={'mode':mode}),request,graph,areas)['items'] if mode=='bike' else []
            candidates.append({**parking[0],'id':'bike','mode':'bike'} if parking else route(graph,body,mode))
        except ValueError:pass
    if not candidates:raise HTTPException(422,'没有可计算的候选路线，请调整选点或补充道路连接')
    try:answer=ask_ai(body.preference,candidates)
    except ValueError as e:raise HTTPException(503,str(e))
    result=next(r for r in candidates if r['id']==answer['route_id'])
    return {**result,'traffic':traffic,'ai':answer,'alternatives':[r for r in candidates if r['id']!=answer['route_id']]}


class ChatMessage(BaseModel):
    role:Literal['user','assistant']
    content:str=Field(min_length=1,max_length=2000)

class ChatNavigationRequest(BaseModel):
    messages:list[ChatMessage]=Field(min_length=1,max_length=12)
    traffic_context:TrafficContext|None=None


def mention_hints(messages,items):
    """Deterministic resolution of "N号楼" mentions, injected into the prompt so the LLM cannot guess."""
    from .place_search import search_places,normalize
    text=' '.join(m.content for m in messages if m.role=='user')
    hints=[];seen=set()
    for match in re.finditer(r'(?<!\d)(\d{1,2})\s*号\s*(?:楼|栋|公寓|宿舍)?',text):
        number=str(int(match.group(1)))
        if number in seen:continue
        seen.add(number)
        key=normalize(f'{number}号楼')
        exact=[it for it in items if key in [normalize(it['name'])]+[normalize(a) for a in it.get('aliases',[])]]
        if len(exact)==1:
            hints.append(f"用户说的“{number}号楼”唯一对应目录条目「{exact[0]['name']}」(id={exact[0]['id']})，必须选它，禁止换成其他号码的楼")
        elif 2<=len(exact)<=6:
            listing='、'.join(f"「{it['name']}」(id={it['id']})" for it in exact)
            hints.append(f"用户说的“{number}号楼”可能指{listing}，按对话上下文选择；无法确定就在reply里追问，origin_id/destination_id填null")
    return hints

def parse_trip(messages,items):
    """Resolve language to catalog IDs; the model never invents coordinates or geometry."""
    c=config();key=c.get('NAV_AI_API_KEY') or c.get('LLM_API_KEY')
    base=c.get('NAV_AI_BASE_URL');model=c.get('NAV_AI_MODEL')
    if not key or not base or not model:raise ValueError('指路模型由负责同学接入，尚未配置完成；请使用普通导航')
    if not base.startswith('https://'):raise ValueError('AI接口必须使用HTTPS')
    system='''你是长安大学渭水校区出行助手。根据对话解析用户现在在哪、要去哪以及出行方式。仅从地点目录选择完整且唯一的id，不得编造地点或坐标。缺少起点、终点或地点有歧义时，以简短中文追问，不猜测具体楼号。用户提到的楼号必须在目录的名称或别名中完全匹配；匹配不到就在reply里追问确认，origin_id或destination_id填null，禁止用相近号码（如把15号楼当成9号、10号）替代。结合历史补全后续回答，最新用户信息优先。返回JSON：{"origin_id":字符串或null,"destination_id":字符串或null,"mode":"walk或bike或auto","reply":"追问或简短出行说明"}。明确步行用walk，骑自行车或电动车用bike，未指定用auto。用户要少走路时可以bike；禁止声称实时路况或定位权限，不编造用时。地点目录：'''
    catalog=[{'id':str(p['id']),'name':p['name'],'aliases':p.get('aliases',[])} for p in items]
    hints=mention_hints(messages,items)
    hint_text=('\n地点消歧提示（优先级最高）：'+'；'.join(hints)+'。') if hints else ''
    payload={'model':model,'messages':[{'role':'system','content':system+json.dumps(catalog,ensure_ascii=False)+hint_text}]+[m.model_dump() for m in messages],
             'stream':False,'temperature':0,'max_tokens':500,'response_format':{'type':'json_object'}}
    # Qwen accepts this option; other providers retain their own defaults.
    if 'qwen' in model.lower():payload['enable_thinking']=False
    req=urllib.request.Request(base.rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=35) as response:raw=json.load(response)
        return json.loads(raw['choices'][0]['message']['content']),model
    except Exception:raise ValueError('指路模型连接失败或回复格式无效，请稍后重试') from None


def demo_parse(messages,items):
    """Built-in rule parser, only until the responsible student plugs in the real model."""
    from .place_search import normalize
    text=' '.join(m.content for m in messages if m.role=='user')
    norm=normalize(text)
    hits=[];seen=set()
    for it in sorted(items,key=lambda p:-len(normalize(p['name']))):
        for term in [it['name']]+list(it.get('aliases',[])):
            n=normalize(term)
            if len(n)>=2 and n in norm and str(it['id']) not in seen:
                hits.append((norm.index(n),it));seen.add(str(it['id']));break
    hits.sort(key=lambda h:h[0])
    found=[h[1] for h in hits]
    origin=destination=None
    if len(found)>=2:origin,destination=found[0],found[1]
    elif len(found)==1:
        key=normalize(found[0]['name']);pos=norm.find(key)
        after=norm[pos+len(key):] if pos>=0 else ''
        if any(k in after for k in ('去','到','回')) or any(k in norm[:pos] for k in ('去','到')):destination=found[0]
        else:origin=found[0]
    if not destination and any(k in norm for k in ('食堂','餐厅','吃饭')):
        canteens=[p for p in items if '餐厅' in p['name'] or '食堂' in p['name']]
        names='、'.join(c['name'] for c in canteens[:6]) or '暂无食堂目录'
        return {'origin_id':str(origin['id']) if origin else None,'destination_id':None,'mode':'auto','reply':f'想去哪个食堂？校园里有{names}。'}
    if not origin or not destination:
        missing='起点' if not origin else '目的地'
        return {'origin_id':str(origin['id']) if origin else None,'destination_id':str(destination['id']) if destination else None,'mode':'auto','reply':f'请告诉我{missing}，例如宿舍楼号、食堂或教学楼名称。'}
    mode='walk' if any(k in text for k in ('步行','走路')) else 'bike' if any(k in text for k in ('骑','自行车','电动')) else 'auto'
    return {'origin_id':str(origin['id']),'destination_id':str(destination['id']),'mode':mode,'reply':''}


BUS_SPEED_KMH=18
BUS_WAIT_MINUTES=5

def bus_options(graph,body,request):
    """Walk-to-stop → ride the drawn line → walk-to-destination, per configured route."""
    from .transit import configured
    try:data=configured(request.app.state.store)
    except Exception:return []
    stops={s['id']:s for s in data['stops']}
    if not stops:return []
    def walk_between(a,b):
        try:return route(graph,NavigationRequest(origin=a,destination=b,mode='walk'),'walk')
        except ValueError:return None
    out=[]
    for r in data['routes']:
        seq=[stops[i] for i in r['stop_ids'] if i in stops]
        pts=[dict(p) for p in r['points']]
        if len(seq)<2 or len(pts)<2:continue
        cum=[0.0]
        for a,b in zip(pts,pts[1:]):cum.append(cum[-1]+distance(a,b))
        def vertex(s):
            ds=[distance({'longitude':s['longitude'],'latitude':s['latitude']},p) for p in pts]
            return ds.index(min(ds))
        vi=[vertex(s) for s in seq]
        def nearest(point):
            ds=[distance(point.model_dump(),{'longitude':s['longitude'],'latitude':s['latitude']}) for s in seq]
            i=min(range(len(ds)),key=lambda k:ds[k]);return i,ds[i]
        oi,o_gap=nearest(body.origin);di,d_gap=nearest(body.destination)
        if oi==di or o_gap>800 or d_gap>800:continue
        w1=walk_between(body.origin,Point(longitude=seq[oi]['longitude'],latitude=seq[oi]['latitude']))
        w2=walk_between(Point(longitude=seq[di]['longitude'],latitude=seq[di]['latitude']),body.destination)
        if not w1 or not w2:continue
        a,b=sorted((vi[oi],vi[di]))
        ride_m=cum[b]-cum[a]
        if ride_m<30:continue
        crowd=[v['observation']['percent'] for v in data['vehicles'] if v['route_id']==r['id'] and v.get('observation')]
        minutes=w1['duration_minutes']+BUS_WAIT_MINUTES+ride_m/(BUS_SPEED_KMH/3.6)/60+w2['duration_minutes']
        out.append({'id':'bus:'+r['id'],'mode':'bus','route_name':r['name'],'color':r['color'],
                    'board_stop':seq[oi]['name'],'alight_stop':seq[di]['name'],
                    'wait_minutes':BUS_WAIT_MINUTES,'crowding_percent':round(sum(crowd)/len(crowd)) if crowd else None,
                    'duration_minutes':round(minutes,1),'distance_m':round(w1['distance_m']+ride_m+w2['distance_m'],1),
                    'geojson':{'type':'FeatureCollection','features':[
                        {'type':'Feature','properties':{'segment':'walk','mode':'walk'},'geometry':w1['geojson']['geometry']},
                        {'type':'Feature','properties':{'segment':'bus','mode':'bus','color':r['color'],'route_name':r['name']},'geometry':{'type':'LineString','coordinates':[[p['longitude'],p['latitude']] for p in pts[a:b+1]]}},
                        {'type':'Feature','properties':{'segment':'walk','mode':'walk'},'geometry':w2['geojson']['geometry']}]},
                    'notice':f"公交按平均候车{BUS_WAIT_MINUTES}分钟、时速{BUS_SPEED_KMH}km/h估算，不含实时班次；拥挤度来自车内观测或手动测试。"})
    out.sort(key=lambda o:o['duration_minutes'])
    return out[:2]

def choose_option(preference,options,traffic):
    """AI weighs time, walking, parking availability, bus crowding and live accidents."""
    c=config();key=c.get('NAV_AI_API_KEY') or c.get('LLM_API_KEY')
    base=c.get('NAV_AI_BASE_URL');model=c.get('NAV_AI_MODEL')
    if not key or not base or not model:raise ValueError('unconfigured')
    if not base.startswith('https://'):raise ValueError('AI接口必须使用HTTPS')
    opts=[{'id':o['id'],'label':o['label'],'minutes':o['duration_minutes'],'meters':o['distance_m'],
           'walk_minutes':o.get('walk_minutes'),'parking_free':o.get('free'),'parking_percent':o.get('percent'),
           'bus_crowding_percent':o.get('crowding_percent'),'bus_wait_minutes':o.get('wait_minutes')} for o in options]
    current={'active_accidents':(traffic or {}).get('active_accidents') or 0,'road_users':(traffic or {}).get('road_users') or 0}
    payload={'model':model,'messages':[
        {'role':'system','content':'你是校园出行助手。在候选方案中为用户选一个，权衡：耗时、步行长短、停车区余位与容载率（越满越应避免）、公交拥挤度与候车时间、当前事故起数与路上人数。用户明确表达的方式偏好优先。只返回JSON {"option_id":"候选id","reason":"50字内中文理由，必须提到至少一个影响选择的具体因素（如某停车区余位、公交拥挤度、当前事故）"}。current_traffic.active_accidents 是当前事故起数，大于0时不得声称"无事故"，可以说所选路线避开事故路段。数据均来自候选与路况，不得编造。'},
        {'role':'user','content':json.dumps({'preference':preference,'options':opts,'current_traffic':current},ensure_ascii=False)}],
        'stream':False,'temperature':0,'max_tokens':300,'response_format':{'type':'json_object'}}
    if 'qwen' in model.lower():payload['enable_thinking']=False
    req=urllib.request.Request(base.rstrip('/')+'/chat/completions',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=35) as response:raw=json.load(response)
        answer=json.loads(raw['choices'][0]['message']['content'])
        ids={o['id'] for o in options}
        if answer.get('option_id') not in ids or not isinstance(answer.get('reason'),str):raise ValueError()
        return answer['option_id'],answer['reason'][:300],model
    except Exception:raise ValueError('AI选路失败') from None


@router.post('/chat')
def chat_navigation(body:ChatNavigationRequest,request:Request):
    if body.messages[-1].role!='user':raise HTTPException(422,'最后一条消息必须是出行请求')
    items=campus_places(request);lookup={str(p['id']):p for p in items}
    demo=False
    try:trip,model=parse_trip(body.messages,items)
    except ValueError as e:
        if '尚未配置' not in str(e):raise HTTPException(503,str(e)) from None
        trip=demo_parse(body.messages,items);model='demo-builtin';demo=True
    if not isinstance(trip,dict):raise HTTPException(503,'指路模型回复格式无效，请重试')
    origin=lookup.get(str(trip.get('origin_id')));destination=lookup.get(str(trip.get('destination_id')))
    if not origin or not destination:
        reply=trip.get('reply')
        return {'status':'clarification','reply':reply[:600] if isinstance(reply,str) and reply else '请告诉我具体的起点和目的地，例如宿舍楼号、教学楼名称。'}
    mode=trip.get('mode')
    if mode not in ('walk','bike','auto'):raise HTTPException(503,'指路模型返回的出行方式无效，请重试')
    from .traffic_snapshot import snapshot
    graph,areas,traffic=snapshot(request,body.traffic_context);options=[];parking=[]
    for candidate_mode in (('walk','bike') if mode=='auto' else (mode,)):
        nav=NavigationRequest(origin=origin,destination=destination,mode=candidate_mode)
        try:
            direct=route(graph,nav,candidate_mode)
            if candidate_mode=='bike':
                parking=compute_parking(nav,request,graph,areas)['items']
                if parking:
                    direct={**parking[0],'id':'bike','mode':'bike','notice':'蓝线到停车区，紫色线为停车后步行；耗时不含入口接驳和停车操作。'}
            options.append(direct)
        except ValueError:continue
    if len(parking)>1:
        second={**parking[1],'id':'bike-alt','mode':'bike','notice':'备选停车区：蓝线到停车区，紫色线为停车后步行；耗时不含入口接驳和停车操作。'}
        options.append(second)
    nav=NavigationRequest(origin=origin,destination=destination,mode='walk')
    options.extend(bus_options(graph,nav,request))
    if not parking:
        try:parking=compute_parking(NavigationRequest(origin=origin,destination=destination,mode='bike'),request,graph,areas)['items']
        except ValueError:parking=[]
    if not options:raise HTTPException(422,'这两个地点之间暂无可通行路线，请换一个入口或目的地')
    seen=set()
    for o in options:
        o.setdefault('id',o['mode'])
        while o['id'] in seen:o['id']+='-x'
        seen.add(o['id'])
        accidents=(traffic or {}).get('active_accidents') or 0
        if o['mode']=='walk':
            o['label']='步行直达';o['factors']=f"全程步行 · 当前路上 {(traffic or {}).get('road_users') or 0} 人" + (f" · 事故 {accidents} 起" if accidents else '')
        elif o['mode']=='bus':
            o['label']=f"公交 {o['route_name']}：{o['board_stop']} → {o['alight_stop']}"
            crowd=o.get('crowding_percent')
            o['factors']=(f"车内拥挤度 {crowd}%" if crowd is not None else '暂无车内人数数据')+f" · 候车约 {o['wait_minutes']} 分" + (f" · 当前事故 {accidents} 起" if accidents else '')
        else:
            o['label']='骑行，经'+o['name']+'停车' if o.get('area_id') else '骑行直达'
            o['factors']=(f"{o['name']}余位 {o.get('free')} / {o.get('capacity')} · 容载率 {o.get('percent')}%" if o.get('area_id') else '直达骑行，无需停车') + (f" · 当前事故 {accidents} 起" if accidents else '')
    preference_text=' '.join(m.content for m in body.messages if m.role=='user')[-400:]
    ai_reason='';ai_model=model
    try:
        chosen_id,ai_reason,ai_model=choose_option(preference_text,options,traffic)
        result=next(o for o in options if o['id']==chosen_id)
    except ValueError:
        result=min(options,key=lambda r:r['duration_minutes'])
    verb={'walk':'步行','bike':'骑行','bus':'乘坐公交'}[result['mode']]
    stop='，在'+result['name']+'停车后步行' if result.get('area_id') else ''
    bus_leg=f"（{result['board_stop']}上车，{result['alight_stop']}下车）" if result['mode']=='bus' else ''
    reply=f"从{origin['name']}到{destination['name']}，建议{verb}{bus_leg}{stop}，预计{result['duration_minutes']}分钟，约{result['distance_m']}米。"
    if ai_reason:reply+=ai_reason
    if result['mode']=='bike' and not parking:reply+='目的地附近暂无可推荐停车区，请勿随意停车。'
    if demo:reply='演示模式：大模型尚未接入，以下为内置规则按真实路网计算的候选。'+reply
    choices=[{'id':o['id'],'mode':o['mode'],'duration_minutes':o['duration_minutes'],'distance_m':o['distance_m'],
              'area_id':o.get('area_id'),'name':o.get('name'),'factors':o['factors'],
              'label':o['label'],'free':o.get('free'),'capacity':o.get('capacity'),'percent':o.get('percent'),
              'crowding_percent':o.get('crowding_percent'),
              'route':o} for o in options]
    return {'status':'route','reply':reply,'origin':origin,'destination':destination,'recommended':result['id'],'route':{**result,'traffic':traffic,'ai':{'model':ai_model,'reason':ai_reason or reply}},'parking':parking if any(o['mode']=='bike' for o in options) else [],'options':choices,'demo':demo}
