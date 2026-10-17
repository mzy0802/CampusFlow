import json
from fastapi.testclient import TestClient
from app.main import app
from app.place_search import normalize,aliases,search_places
from app.building_walk import building_connections,visible
from app.navigation import NavigationRequest,route


def test_campus_number_aliases_rank_buildings_above_parking_and_preserve_numbers():
    items=[{'id':'parking','name':'明远1西侧'},{'id':'a','name':'明远教学楼A栋'},{'id':'b','name':'明远教学楼B栋'},{'id':'x4','name':'修远教学楼四区'},{'id':'x1','name':'修远教学楼一区'}]
    items=[{**p,'aliases':aliases(p)} for p in items]
    for query in ('明远1','明远一区','明远A区','明远Ａ栋'):
        assert search_places(items,query)[0]['id']=='a'
    assert search_places(items,'明远2')[0]['id']=='b'
    assert search_places(items,'修远4区')[0]['id']=='x4'
    assert search_places(items,'名远1')[0]['id']=='a'
    assert not any(p['id']=='x1' for p in search_places(items,'明远1'))
    assert normalize('二十三号宿舍楼')==normalize('23号公寓')


def test_real_catalog_includes_xiuyuan_four_from_osm_relation():
    with TestClient(app) as c:
        hits=c.get('/api/navigation/places?q=修远4区').json()['items']
        assert hits[0]['id']=='osm_relation_16871375'
        assert hits[0]['name']=='修远教学楼四区'
        assert hits[0]['source']=='OpenStreetMap'
        assert c.get('/api/navigation/places?q=明远1').json()['items'][0]['name']=='明远教学楼A栋'


def test_building_walk_shortens_detour_but_never_admits_bicycles():
    feature={'properties':{'id':'building','tags':{'name':'明远教学楼A栋'}},'geometry':{'coordinates':[[[0,0],[.001,0],[.001,.001],[0,.001],[0,0]]]}}
    coords=[('w',-.00005,.0005),('nw',-.00005,.0011),('ne',.00105,.0011),('e',.00105,.0005)]
    nodes=[{'id':i,'longitude':x,'latitude':y} for i,x,y in coords]
    edges=[{'id':a+b,'source':a,'target':b,'modes':['walk','bike'],'verified':True,'bidirectional':True,'congestion':1} for a,b in [('w','nw'),('nw','ne'),('ne','e')]]
    graph={'revision':1,'nodes':nodes,'edges':edges,'_building_walk':True}
    n,e=building_connections(feature,nodes);assert e
    augmented={**graph,'nodes':nodes+n,'edges':edges+e}
    request=NavigationRequest(origin=nodes[0],destination=nodes[-1])
    before=route(graph,request,'walk');after=route(augmented,request,'walk')
    assert after['distance_m']<before['distance_m']*.7
    assert after['uses_building_passage']
    assert route(augmented,request,'bike')['geojson']==route(graph,request,'bike')['geojson']


def test_indoor_visibility_respects_concave_outline_and_courtyard_holes():
    outer=[(0,0),(100,0),(100,100),(0,100)]
    hole=[(40,40),(60,40),(60,60),(40,60)]
    assert not visible((10,50),(90,50),[outer,hole])
    assert visible((10,20),(90,20),[outer,hole])
    concave=[(0,0),(100,0),(100,20),(20,20),(20,100),(0,100)]
    assert not visible((10,90),(90,10),[concave])
    assert visible((10,10),(90,10),[concave])
