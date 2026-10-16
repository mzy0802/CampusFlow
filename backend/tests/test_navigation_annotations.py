import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.navigation import NavigationRequest,route
from app.annotations import Polygon
from app.parking_editor import validate_collection
from app.data import load_parking

def line_graph(bidirectional=True):
    return {'revision':1,'nodes':[{'id':'a','longitude':0,'latitude':0},{'id':'b','longitude':.01,'latitude':0}], 'edges':[{'id':'ab','source':'a','target':'b','modes':['walk','bike'],'verified':True,'bidirectional':bidirectional,'congestion':1}]}

def test_navigation_splits_same_edge_and_respects_oneway():
    request=NavigationRequest(origin={'longitude':.002,'latitude':0},destination={'longitude':.008,'latitude':0})
    result=route(line_graph(),request,'walk')
    assert 660<result['distance_m']<675
    assert result['geojson']['geometry']['coordinates'][0]==[.002,0]
    assert result['origin_access_distance_m']==0
    reverse=NavigationRequest(origin=request.destination,destination=request.origin)
    with pytest.raises(ValueError,match='不连通'):route(line_graph(False),reverse,'walk')
    far=NavigationRequest(origin={'longitude':1,'latitude':1},destination=request.destination)
    with pytest.raises(ValueError,match='150'):route(line_graph(),far,'walk')

@pytest.mark.parametrize('points',[
    [(0,0),(1,1),(0,1),(1,0)],
    [(0,0),(1,0),(.5,0)],
    [(0,0),(1,0),(1,0),(0,1)],
    [(0,0),(1.1,0),(0,1)],
])
def test_invalid_annotation_geometry(points):
    with pytest.raises(ValueError):Polygon(id='x',label='allowed',points=points)

def test_only_allowed_label_accepted():
    with pytest.raises(ValueError):Polygon(id='x',label='forbidden',points=[(0,0),(1,0),(0,1)])

def test_annotation_upload_persistence_frame_policy_and_conflict():
    import cv2,numpy as np
    data=cv2.imencode('.png',np.zeros((24,32,3),dtype=np.uint8))[1].tobytes()
    with TestClient(app) as c:
        response=c.post('/api/annotations/media?filename=test.png',content=data)
        assert response.status_code==201
        mid=response.json()['id']
        assert response.json()['width']==32
        assert c.get(f'/api/annotations/media/{mid}/content').status_code==200
        old=c.get(f'/api/annotations/media/{mid}').json()
        assert old['reviewed_frames']==[] and old['unreviewed_policy']=='unknown'
        body={'revision':0,'reviewed_frames':[0],'polygons':[{'id':'p','label':'allowed','points':[[.1,.1],[.8,.1],[.8,.8],[.1,.8]]}]}
        saved=c.put(f'/api/annotations/media/{mid}',json=body)
        assert saved.status_code==200
        assert saved.json()['outside_policy']=='forbidden_in_reviewed_frame'
        assert c.put(f'/api/annotations/media/{mid}',json=body).status_code==409
        body.update(revision=1,reviewed_frames=[2])
        assert c.put(f'/api/annotations/media/{mid}',json=body).status_code==422
        assert len(c.get('/api/annotations/media').json()['items'])==1
        assert c.post('/api/annotations/media?filename=bad.png',content=b'bad').status_code==422
        assert len(c.get('/api/annotations/media').json()['items'])==1
        assert c.get('/api/annotations/media/not-a-valid-id/content').status_code==404
    with TestClient(app) as c:
        assert c.get(f'/api/annotations/media/{mid}').json()['polygons'][0]['id']=='p'

def test_map_parking_save_conflict_and_restart():
    # Retain an unchanged legacy import; newly drawn self-intersections still fail.
    with pytest.raises(ValueError):validate_collection(load_parking())
    validate_collection(load_parking(),load_parking())
    with TestClient(app) as c:
        doc=c.get('/api/parking-editor').json()
        doc['collection']['features'][0]['properties']['name']='人工修改区域'
        doc['collection']['features'][0]['properties']['capacity']=123
        assert c.put('/api/parking-editor',json=doc).status_code==200
        assert c.put('/api/parking-editor',json=doc).status_code==409
    with TestClient(app) as c:
        f=c.get('/api/parking/areas').json()['features'][0]
        assert f['properties']['name']=='人工修改区域'
        assert f['properties']['capacity']==123

def test_search_and_ai_returns_computed_route(monkeypatch):
    from app import navigation
    with TestClient(app) as c:
        graph=line_graph();graph.update(dataset='campus',revision=0,schema_version=1)
        for n in graph['nodes']:n['name']=n['id']
        assert c.put('/api/network/campus',json=graph).status_code==200
        monkeypatch.setattr(navigation,'ask_ai',lambda pref,choices:{'route_id':'bike','reason':'测试选择骑行','model':'mock'})
        r=c.post('/api/navigation/recommend',json={'origin':{'longitude':.002,'latitude':0},'destination':{'longitude':.008,'latitude':0},'preference':'快一点'})
        assert r.status_code==200
        assert r.json()['mode']=='bike' and r.json()['ai']['model']=='mock'
        assert c.get('/api/navigation/places?q=公寓').status_code==200
        assert c.get('/api/navigation/map').json()['features']

def test_owner_road_acceptance_only_once(tmp_path):
    from app.traffic_store import Store
    from app.network_models import Network
    store=Store(tmp_path/'roads.sqlite3')
    graph=line_graph();graph.update(dataset='campus',revision=0)
    for n in graph['nodes']:n['name']=n['id']
    graph['edges'][0]['verified']=False
    store.save(Network.model_validate(graph));store.accept_current_roads()
    assert store.get('campus')['edges'][0]['verified']
    edited=store.get('campus');edited['edges'][0]['verified']=False
    store.save(Network.model_validate(edited));store.accept_current_roads()
    assert not store.get('campus')['edges'][0]['verified']

def test_video_annotations_are_frame_scoped_and_media_supports_range(tmp_path):
    import cv2,numpy as np
    path=tmp_path/'clip.avi'
    writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(64,48))
    assert writer.isOpened()
    for i in range(20):writer.write(np.full((48,64,3),i*10,dtype=np.uint8))
    writer.release()
    with TestClient(app) as c:
        uploaded=c.post('/api/annotations/media?filename=clip.avi',content=path.read_bytes())
        assert uploaded.status_code==201
        mid=uploaded.json()['id']
        assert uploaded.json()['duration_seconds']==2
        body={'revision':0,'reviewed_frames':[1],'polygons':[]}
        saved=c.put(f'/api/annotations/media/{mid}',json=body).json()
        assert saved['reviewed_frames']==[1] and saved['polygons']==[]
        assert saved['unreviewed_policy']=='unknown'
        response=c.get(f'/api/annotations/media/{mid}/content',headers={'Range':'bytes=0-31'})
        assert response.status_code==206 and len(response.content)==32

def test_map_colors_metadata_hides_service_and_places_have_dorms():
    from app.network_models import Network
    data=Path(__file__).resolve().parents[2]/'data'
    with TestClient(app) as c:
        app.state.store.save(Network.model_validate_json((data/'network.osm.json').read_text(encoding='utf-8')))
        roads=c.get('/api/navigation/map').json()['features']
        assert roads and all(f['properties']['highway']!='service' for f in roads)
        assert any(f['properties']['name'] for f in roads)
        full=c.get('/api/navigation/map?include_service=true').json()['features']
        assert len(full)>len(roads)
        matches=c.get('/api/navigation/places',params={'q':'鸿翔园2号宿舍楼'}).json()['items']
        assert any(p['name']=='鸿翔园2号公寓' for p in matches)
