"""Coordinate navigation on the saved campus graph; AI selects computed options only."""
import json
import math
import os
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

DEFAULT_WEIGHTS=(1,2,5)
# Preferences only change the weights of the ranking below; plain navigation
# keeps DEFAULT_WEIGHTS so both paths share one cost function.
PREFERENCE_WEIGHTS={'less_walk':(1,4,5),'avoid_crowd':(1,2,12),'fastest':(1,1,0)}
PREFERENCE_NOTE={'less_walk':'（已按你的偏好优先减少步行）','avoid_crowd':'（已按你的偏好优先避开拥挤停车区）','fastest':'（已按你的偏好优先最短耗时）'}

def parking_cost(approach_minutes,walk_minutes,percent,weights=None):
    """A 100% occupancy costs five equivalent minutes by default; walking has double weight."""
    a,b,c=weights or DEFAULT_WEIGHTS
    return a*approach_minutes+b*walk_minutes+c*percent/100

def preference_key(option,preference):
    """Picking between the computed candidates; less_walk compares walking time alone."""
    if preference=='less_walk':return option.get('walk_minutes',option['duration_minutes'])
    if preference=='avoid_crowd':return option['duration_minutes']+5*(option.get('percent') or 0)/100
    return option['duration_minutes']

def compute_parking(body,request,graph,areas=None,weights=None):
    from .parking_state import area_states
    walk_weight,occupancy_weight=(weights or DEFAULT_WEIGHTS)[1:]
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
        cost=parking_cost(approach['duration_minutes'],walking['duration_minutes'],area['percent'],weights)
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
            'formula':f'approach_minutes + {walk_weight} * walk_minutes + {occupancy_weight} * occupancy_percent / 100',
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


def parse_trip(messages,items):
    """Resolve language to catalog IDs; the model never invents coordinates or geometry."""
    c=config();key=c.get('NAV_AI_API_KEY') or c.get('LLM_API_KEY')
    base=c.get('NAV_AI_BASE_URL');model=c.get('NAV_AI_MODEL')
    if not key or not base or not model:raise ValueError('指路模型由负责同学接入，尚未配置完成；请使用普通导航')
    if not base.startswith('https://'):raise ValueError('AI接口必须使用HTTPS')
    system='''你是长安大学渭水校区出行助手。根据对话解析用户现在在哪、要去哪、出行方式以及出行偏好。仅从地点目录选择完整且唯一的id，不得编造地点或坐标。缺少起点、终点或地点有歧义时，以简短中文追问，不猜测具体楼号。只说了某一族楼而没说哪一栋时也要追问，不要替用户选。结合历史补全后续回答，最新用户信息优先。返回JSON：{"origin_id":字符串或null,"destination_id":字符串或null,"mode":"walk或bike或auto","preference":"less_walk或avoid_crowd或fastest或null","reply":"追问或简短出行说明"}。明确步行用walk，骑自行车或电动车用bike，未指定用auto。说少走路、不想走太远时preference用less_walk；说避开拥挤、别去停满的地方用avoid_crowd；说最快、赶时间用fastest；没提偏好用null。禁止声称实时路况或定位权限，不编造用时。地点目录：'''
    catalog=[{'id':str(p['id']),'name':p['name'],'aliases':p.get('aliases',[])} for p in items]
    payload={'model':model,'messages':[{'role':'system','content':system+json.dumps(catalog,ensure_ascii=False)}]+[m.model_dump() for m in messages],
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
    found=[]
    for _,_hit in hits:
        # Duplicate survey nodes of one gate are one place, not a separate stop.
        if not found or _hit['name']!=found[-1]['name']:found.append(_hit)
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
    latest=body.messages[-1].content
    if not origin or not destination:
        from .place_disambig import clarify
        # A deterministic question beats the model's generic one when the
        # sentence names a building family without saying which one.
        reply=clarify(latest,items) or trip.get('reply')
        return {'status':'clarification','reply':reply[:600] if isinstance(reply,str) and reply else '请告诉我具体的起点和目的地，例如宿舍楼号、教学楼名称。'}
    mode=trip.get('mode')
    if mode not in ('walk','bike','auto'):raise HTTPException(503,'指路模型返回的出行方式无效，请重试')
    from .place_disambig import clarify
    question=clarify(latest,items,origin) or clarify(latest,items,destination)
    if question:return {'status':'clarification','reply':question[:600]}
    preference=trip.get('preference')
    if preference not in PREFERENCE_WEIGHTS:preference=None
    weights=PREFERENCE_WEIGHTS.get(preference)
    from .traffic_snapshot import snapshot
    graph,areas,traffic=snapshot(request,body.traffic_context);options=[];parking=[]
    for candidate_mode in (('walk','bike') if mode=='auto' else (mode,)):
        nav=NavigationRequest(origin=origin,destination=destination,mode=candidate_mode)
        try:
            direct=route(graph,nav,candidate_mode)
            if candidate_mode=='bike':
                parking=compute_parking(nav,request,graph,areas,weights)['items']
                if parking:
                    direct={**parking[0],'mode':'bike','notice':'蓝线到停车区，紫色线为停车后步行；耗时不含入口接驳和停车操作。'}
            options.append(direct)
        except ValueError:continue
    if not options:raise HTTPException(422,'这两个地点之间暂无可通行路线，请换一个入口或目的地')
    if len(parking)>1:
        second={**parking[1],'mode':'bike','notice':'备选停车区：蓝线到停车区，紫色线为停车后步行；耗时不含入口接驳和停车操作。'}
        options.append(second)
    result=min(options,key=lambda r:preference_key(r,preference))
    verb='步行' if result['mode']=='walk' else '骑行'
    stop='，在'+result['name']+'停车后步行' if result.get('area_id') else ''
    reply=f"从{origin['name']}到{destination['name']}，建议{verb}{stop}，预计{result['duration_minutes']}分钟，约{result['distance_m']}米。"
    if result['mode']=='bike' and not parking:reply+='目的地附近暂无可推荐停车区，请勿随意停车。'
    if preference:reply+=PREFERENCE_NOTE[preference]
    if demo:reply='演示模式：大模型尚未接入，以下为内置规则按真实路网计算的候选。'+reply
    choices=[{'mode':o['mode'],'duration_minutes':o['duration_minutes'],'distance_m':o['distance_m'],
              'area_id':o.get('area_id'),'name':o.get('name'),
              'label':('步行直达' if o['mode']=='walk' else ('骑行，经'+o['name']+'停车' if o.get('area_id') else '骑行直达')),
              'route':o} for o in options]
    return {'status':'route','reply':reply,'origin':origin,'destination':destination,'route':{**result,'traffic':traffic,'ai':{'model':model,'reason':reply}},'parking':parking if result['mode']=='bike' else [],'options':choices,'demo':demo,'preference':preference}
