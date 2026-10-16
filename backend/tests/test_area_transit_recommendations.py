"""Business integration tests. All model replies are explicit test doubles; no paid calls."""
import json
from datetime import datetime,timezone,timedelta
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import area_surveys,vision
from app.network_models import Network
from app.qwen_vision import VisionEngine

def png():
    import cv2,numpy as np
    return cv2.imencode('.png',np.zeros((48,64,3),dtype=np.uint8))[1].tobytes()

def bind(c,area,group='same-instant',time=0):
    r=c.post('/api/annotations/media?filename=angle.png',content=png());assert r.status_code==201
    mid=r.json()['id']
    payload={'revision':0,'area_id':area,'capture_group':group,'view_name':'东侧','reviewed_frames':[time],
             'polygons':[{'id':'allowed','label':'allowed','time_seconds':time,'points':[[.1,.1],[.8,.1],[.8,.8],[.1,.8]]}]}
    saved=c.put('/api/annotations/media/'+mid,json=payload);assert saved.status_code==200
    return mid

def test_area_capacity_controls_single_file_and_multiview_violations(monkeypatch):
    with TestClient(app) as c:
        area=c.get('/api/parking/areas').json()['features'][0]['properties']['id']
        assert c.put('/api/parking/'+area+'/capacity',json={'capacity':50}).status_code==200
        monkeypatch.setattr(vision,'readiness',lambda:{'ready':True})
        jobs=[];service=app.state.vision
        monkeypatch.setattr(service,'submit',lambda job,path:jobs.append(job))
        r=c.post('/api/vision/jobs',params={'filename':'capacity.png','area_id':area,'bicycle_capacity':999},content=png())
        assert r.status_code==202 and jobs[0]['bicycle_capacity']==50
        service.slots.release() # The stub did not process this queued job.
        mids=[bind(c,area),bind(c,area)]
        geometry=c.get('/api/parking-editor').json()
        geometry['collection']['features']=[f for f in geometry['collection']['features'] if f['properties']['id']!=area]
        assert c.put('/api/parking-editor',json=geometry).status_code==422
        assert len(c.get('/api/annotations/views',params={'area_id':area,'capture_group':'same-instant'}).json()['items'])==2
        seen=[]
        def count(views):
            seen.extend(views)
            return {'bicycle':10,'powered_two_wheeler':45,'uncertain_type':5,'total':60,'person':2,
                    'legal_count':40,'illegal_count':15,'unknown_location_count':5,'note':'mock overlap estimate'}
        monkeypatch.setattr(service.engine,'count_views',count)
        monkeypatch.setattr(area_surveys,'readiness',lambda:{'ready':True})
        monkeypatch.setattr(service.executor,'submit',lambda fn,*args:fn(*args))
        body={'area_id':area,'capture_group':'same-instant','views':[{'media_id':mid} for mid in mids]}
        response=c.post('/api/vision/surveys',json=body);assert response.status_code==202
        job=c.get('/api/vision/jobs/'+response.json()['id']).json()
        assert job['status']=='completed',job
        assert job['result']['two_wheeler']['latest']['percent']==120
        assert job['result']['illegal_count']==15 and job['result']['view_count']==2
        assert len(seen)==2 and seen[0]['raw']==png() and seen[0]['polygons']
        overview=next(p for p in c.get('/api/parking/overview').json()['items'] if p['id']==area)
        assert overview['count']==60 and overview['illegal_count']==15 and overview['percent']==120
        assert overview['source']=='qwen_estimate' and overview['available']==0
        # Capacity is read again at display time; old job percentages are not reused.
        c.put('/api/parking/'+area+'/capacity',json={'capacity':100})
        overview=next(p for p in c.get('/api/parking/overview').json()['items'] if p['id']==area)
        assert overview['percent']==60
        assert c.get('/api/annotations/media/'+mids[0]+'/content').status_code==200
        assert c.post('/api/vision/surveys',json={**body,'capture_group':'another-time'}).status_code==422
        assert c.post('/api/vision/surveys',json={**body,'views':[body['views'][0]]*2}).status_code==422

def test_surveys_reject_unannotated_frame_and_foreign_area():
    with TestClient(app) as c:
        areas=c.get('/api/parking/areas').json()['features'];area=areas[0]['properties']['id']
        mid=bind(c,area)
        assert c.post('/api/vision/surveys',json={'area_id':area,'capture_group':'same-instant','views':[{'media_id':mid,'time_seconds':.01}]}).status_code==422
        assert c.put('/api/annotations/media/'+mid,json={'revision':1,'area_id':'missing','polygons':[]}).status_code==422

def test_multiview_prompt_and_validation(monkeypatch):
    engine=VisionEngine();captured=[]
    def completion(content):
        captured.extend(content)
        return json.dumps({'bicycle':1,'powered_two_wheeler':1,'uncertain_type':0,'total':2,'person':0,'legal_count':1,'illegal_count':1,'unknown_location_count':0}),{}
    monkeypatch.setattr(engine,'completion',completion)
    assert engine.count_views([{'name':'a','raw':b'original','mime':'image/png','polygons':[]}])['illegal_count']==1
    assert 'do NOT add' in captured[0]['text'] and 'b3JpZ2luYWw=' in captured[-1]['image_url']['url']
    monkeypatch.setattr(engine,'completion',lambda c:(json.dumps({'bicycle':1,'powered_two_wheeler':1,'uncertain_type':0,'total':2,'person':0,'legal_count':2,'illegal_count':1,'unknown_location_count':0}),{}))
    with pytest.raises(ValueError):engine.count_views([])

def transit_payload():
    return {'revision':0,'stops':[{'id':'s1','name':'一站','longitude':108,'latitude':34},{'id':'s2','name':'二站','longitude':108.01,'latitude':34}],
            'routes':[{'id':'r1','name':'测试线路','points':[{'longitude':108,'latitude':34},{'longitude':108.01,'latitude':34}],'stop_ids':['s1','s2']}],
            'vehicles':[{'id':'bus1','name':'测试车','route_id':'r1','capacity':30,'camera_id':'cam1'}]}

def test_transit_persistence_conflicts_camera_counts_and_recalculated_capacity():
    with TestClient(app) as c:
        assert c.get('/api/transit').json()['routes']==[]
        payload=transit_payload();assert c.put('/api/transit',json=payload).status_code==200
        assert c.put('/api/transit',json=payload).status_code==409
        now=datetime.now(timezone.utc)
        obs={'count':36,'camera_id':'cam1','captured_at':now.isoformat(),'source':'camera'}
        assert c.post('/api/transit/vehicles/bus1/observations',json={**obs,'camera_id':'wrong'}).status_code==422
        r=c.post('/api/transit/vehicles/bus1/observations',json=obs)
        assert r.status_code==200 and r.json()['percent']==120
        assert c.post('/api/transit/vehicles/bus1/observations',json=obs).status_code==409
        assert c.post('/api/transit/vehicles/bus1/observations',json={**obs,'captured_at':(now+timedelta(days=1)).isoformat()}).status_code==422
        payload['revision']=1;payload['vehicles'][0]['capacity']=40
        assert c.put('/api/transit',json=payload).json()['vehicles'][0]['observation']['percent']==90
        payload['revision']=2;payload['routes'][0]['stop_ids']=['missing']
        assert c.put('/api/transit',json=payload).status_code==422
    with TestClient(app) as c:
        assert c.get('/api/transit').json()['vehicles'][0]['observation']['count']==36

def test_parking_recommendation_uses_congestion_and_computes_both_segments(monkeypatch):
    import app.parking_state as state
    def area(id,x,percent):
        return {'id':id,'name':id,'count':percent,'capacity':100,'percent':percent,'illegal_count':0,'source':'simulated','geometry':{'type':'Polygon','coordinates':[[[x-.00001,-.00001],[x+.00001,-.00001],[x+.00001,.00001],[x-.00001,.00001],[x-.00001,-.00001]]]}}
    with TestClient(app) as c:
        graph=Network.model_validate({'dataset':'campus','revision':0,'nodes':[{'id':'a','name':'a','longitude':0,'latitude':0},{'id':'b','name':'b','longitude':.01,'latitude':0}],'edges':[{'id':'e','source':'a','target':'b','bidirectional':True,'verified':True}]})
        app.state.store.save(graph)
        monkeypatch.setattr(state,'area_states',lambda r:{'items':[area('empty',.008,0),area('full',.008,120)]})
        r=c.post('/api/navigation/parking-recommendations',json={'origin':{'longitude':.001,'latitude':0},'destination':{'longitude':.009,'latitude':0},'mode':'bike'})
        assert r.status_code==200,r.text
        items=r.json()['items'];assert [p['area_id'] for p in items]==['empty','full']
        assert items[1]['score']>items[0]['score']
        assert items[0]['walking']['distance_m']>100 and items[0]['approach']['distance_m']>700
        assert len(items[0]['geojson']['features'])==2
