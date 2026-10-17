from app.scenario_dynamics import Roads,Paths,accidents_for,integrate,cell,xy,pace_at,state_at


def fixture():
    nodes=[{'id':i,'longitude':x,'latitude':y} for i,x,y in [('a',108.89,34.37),('b',108.892,34.37),('c',108.89,34.371),('d',108.89,34.369)]]
    edges=[{'id':i,'source':a,'target':b,'modes':['walk','bike'],'verified':True,'congestion':1,'bidirectional':True,'highway':kind} for i,a,b,kind in [('main','a','b','residential'),('north','a','c','residential'),('south','a','d','residential'),('foot','b','c','footway'),('cycle','b','d','cycleway')]]
    roads=Roads({'nodes':nodes,'edges':edges})
    paths={'p':{'coordinates':[[108.89,34.37],[108.892,34.37]],'seconds':120}}
    return roads,paths,Paths(paths,roads)


def test_accidents_are_on_major_vehicle_roads_not_footpaths_or_cycleways():
    roads,paths,sampler=fixture()
    assert 'foot' not in roads.items and 'cycle' not in roads.items
    vehicles={(key,k):set(range(500)) for key in ('main','foot','cycle') for k in range(61)}
    events=accidents_for(vehicles,roads,20261016)
    assert events
    for e in events:
        assert e['road_id']=='main' and e['highway']=='residential'
        assert abs(e['latitude']-34.37)<1e-8
        assert 108.89<=e['longitude']<=108.892


def test_spatial_crowding_and_accidents_slow_actual_nonuniform_progress():
    roads,paths,sampler=fixture();agent={'id':10}
    congested={(cell(sampler.sample('p',p/100)[0]),k):60 for p in range(101) for k in range(61)}
    free,profile=integrate(agent,'p',120,0,{},[],sampler)
    slow,slow_profile=integrate(agent,'p',120,0,congested,[],sampler)
    event={'_xy':xy([108.891,34.37]),'start':0,'end':1000}
    incident,incident_profile=integrate(agent,'p',120,0,congested,[event],sampler)
    assert free<slow<incident
    slopes=[round((q-p)/(u-t),6) for (t,p),(u,q) in zip(profile,profile[1:])]
    assert len(set(slopes))>2
    assert all(a[1]<=b[1] for a,b in zip(incident_profile,incident_profile[1:]))


def test_meal_and_second_leg_profiles_are_independent_and_snapshot_matches():
    _,paths,_=fixture()
    a={'mode':'bicycle','start':100,'path':'p','via_path':'p','leg1_seconds':60,'dwell_seconds':240,'travel_seconds':420,'leg1_pace':[[0,0],[30,.2],[60,1]],'travel_pace':[[0,0],[60,.25],[120,1]],'walk_path':'p','walk_seconds':120,'walk_pace':[[0,0],[60,.2],[120,1]]}
    assert state_at(a,130,paths)['progress']==.2
    assert state_at(a,250,paths)['kind']=='dining'
    assert state_at(a,460,paths)['progress']==.25
    assert state_at(a,640,paths)['progress']==.2


def test_parking_overflow_spills_back_only_real_queue_members_to_general_roads():
    from collections import defaultdict
    from app.scenario_dynamics import parking_spillback
    _,_,sampler=fixture()
    area={'id':'lot','longitude':108.891,'latitude':34.3701,'capacity':2}
    agents=[{'id':i,'area_id':'lot','start':0,'travel_seconds':120} for i in range(5)]
    cells=defaultdict(float);vehicles=defaultdict(set)
    parking_spillback(agents,[area],sampler,cells,vehicles)
    assert cells and vehicles
    assert {r for r,b in vehicles}=={'main'}
    assert set().union(*vehicles.values())=={2,3,4}
    cells.clear();vehicles.clear()
    parking_spillback(agents[:2],[area],sampler,cells,vehicles)
    assert not cells and not vehicles


def test_xiuyuan_corridor_includes_adjacent_lane_flow_without_fake_road_accidents():
    from collections import defaultdict
    from app.scenario_dynamics import corridor_pressure,occupancy
    roads,paths,_=fixture();roads.items['main']['name']='修远大道'
    paths['parallel']={'coordinates':[[108.89,34.37015],[108.892,34.37015]],'seconds':120}
    sampler=Paths(paths,roads)
    agents=[{'id':i,'mode':'bicycle','path':'parallel','start':0,'travel_seconds':120} for i in range(24)]
    cells,vehicles=occupancy(agents,paths,sampler)
    assert not vehicles
    traffic=corridor_pressure(agents,paths,sampler,cells)
    assert any(len(ids)==24 for ids in traffic.values())
    assert all(rid=='main' for rid,bucket in traffic)
    assert cells


def test_named_xiuyuan_shared_avenue_is_not_dropped_as_generic_pedestrian(monkeypatch):
    from app import navigation
    def data(name,default):
        if name=='roads.osm.geojson':return {'features':[{'properties':{'id':'avenue','highway':'pedestrian','tags':{'name':'修远大道'}}}]}
        return default
    monkeypatch.setattr(navigation,'read_data',data)
    nodes=[{'id':'a','longitude':108.899,'latitude':34.371},{'id':'b','longitude':108.901,'latitude':34.372}]
    edges=[{'id':rid,'source':'a','target':'b','verified':True,'modes':['walk','bike'],'highway':'pedestrian'} for rid in ('avenue','ordinary-footpath')]
    roads=Roads({'nodes':nodes,'edges':edges})
    assert 'avenue' in roads.items and roads.items['avenue']['name']=='修远大道'
    assert 'ordinary-footpath' not in roads.items
