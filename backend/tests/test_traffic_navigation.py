from fastapi.testclient import TestClient
from app.main import app
from app.navigation import NavigationRequest,route
from app.traffic_snapshot import apply_density
import pytest


def graph():
    nodes=[{'id':k,'name':k,'kind':'intersection','longitude':x,'latitude':y} for k,x,y in [('a',0,0),('b',.001,0),('c',0,.001),('d',.001,.001)]]
    edges=[{'id':a+b,'source':a,'target':b,'verified':True,'modes':['walk','bike'],'bidirectional':True,'congestion':1} for a,b in [('a','b'),('a','c'),('c','d'),('d','b')]]
    return {'revision':1,'nodes':nodes,'edges':edges}


def test_navigation_does_not_fall_back_to_vision_credentials(monkeypatch):
    from app import navigation
    monkeypatch.setattr(navigation,'config',lambda:{'DASHSCOPE_API_KEY':'vision-only','QWEN_VISION_MODEL':'qwen3-vl-plus','QWEN_VISION_BASE_URL':'https://example.invalid'})
    with pytest.raises(ValueError,match='尚未配置'):
        navigation.parse_trip([],[])


def test_road_people_change_real_computed_route_without_mutating_graph():
    g=graph();body=NavigationRequest(origin={'longitude':0,'latitude':0},destination={'longitude':.001,'latitude':0})
    before=route(g,body,'walk')
    busy,counts=apply_density(g,[({'longitude':.0005,'latitude':0},'walk')]*35)
    after=route(busy,body,'walk')
    assert counts['ab']['walk']==35
    assert len(before['geojson']['geometry']['coordinates'])==2
    assert len(after['geojson']['geometry']['coordinates'])==4
    assert after['distance_m']>before['distance_m']
    assert g['edges'][0]['congestion']==1


def test_chat_and_normal_navigation_share_snapshot_and_parking(monkeypatch):
    from app import navigation,traffic_snapshot
    origin={'id':'home','name':'宿舍一号','longitude':0,'latitude':0}
    destination={'id':'class','name':'教学楼','longitude':.001,'latitude':0}
    def area(id,count):
        return {'id':id,'name':id,'capacity':10,'count':count,'percent':count*10,'illegal_count':0,'source':'scenario_simulation',
                'geometry':{'type':'Polygon','coordinates':[[[.0007,-.00001],[.0009,-.00001],[.0009,.00001],[.0007,.00001],[.0007,-.00001]]]}}
    contexts=[]
    def snapshot(request,context):
        contexts.append(context.model_dump())
        return graph(),[area('full',10),area('available',3)],{'time_seconds':context.time_seconds,'road_users':35,'busy_segments':1}
    monkeypatch.setattr(traffic_snapshot,'snapshot',snapshot)
    monkeypatch.setattr(navigation,'campus_places',lambda r:[origin,destination])
    responses=iter([({'origin_id':'home','destination_id':None,'mode':'auto','reply':'你要去哪里？'},'test'),
                    ({'origin_id':'home','destination_id':'class','mode':'bike'},'test'),
                    ({'origin_id':'invented','destination_id':'class','mode':'bike','reply':'请说具体宿舍。'},'test')])
    monkeypatch.setattr(navigation,'parse_trip',lambda messages,items:next(responses))
    context={'time_seconds':600,'count':1000,'scenario':'baseline','seed':20261016,'population':4000}
    with TestClient(app) as client:
        normal=client.post('/api/navigation/route',json={'origin':origin,'destination':destination,'mode':'bike','traffic_context':context})
        assert normal.status_code==200,normal.text
        assert normal.json()['area_id']=='available'
        assert normal.json()['parking'][0]['free']==7
        assert len(normal.json()['parking'])==1
        first={'role':'user','content':'我在宿舍一号'}
        follow=client.post('/api/navigation/chat',json={'messages':[first],'traffic_context':context})
        assert follow.json()['status']=='clarification' and 'route' not in follow.json()
        chat=client.post('/api/navigation/chat',json={'messages':[first,{'role':'assistant','content':follow.json()['reply']},{'role':'user','content':'去教学楼，骑车'}],'traffic_context':context})
        assert chat.status_code==200,chat.text
        assert chat.json()['route']['geojson']==normal.json()['geojson']
        assert chat.json()['route']['traffic']['time_seconds']==600
        assert chat.json()['parking'][0]['area_id']=='available'
        bad=client.post('/api/navigation/chat',json={'messages':[first],'traffic_context':context})
        assert bad.json()['status']=='clarification' and 'route' not in bad.json()
    assert all(c==context for c in contexts)
