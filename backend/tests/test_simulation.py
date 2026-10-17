import json
from app.simulation import generate, HOTSPOTS
from app.data import load_parking, DEFAULT_FILE


def test_morning_counterfactual_conserves_demand_and_routes():
    graph=json.loads((DEFAULT_FILE.parent/'network.osm.json').read_text(encoding='utf-8'))
    places=json.loads((DEFAULT_FILE.parent/'places.osm.json').read_text(encoding='utf-8'))['items']
    d=generate(graph,load_parking(),places,1000)
    assert d['generated_agents']==1000 and not d['excluded']
    assert d['covered_dorms']==d['dorm_count']==24
    baseline=d['cases']['baseline']; guided=d['cases']['guided']
    for before, after in zip(baseline,guided):
        for key in ('id','origin_id','destination_id','mode','start'):
            assert before[key]==after[key]
        for key in ('path','walk_path'):
            if after.get(key) is not None:
                coords=d['paths'][after[key]]['coordinates']
                assert len(coords)>=2 and all(len(p)==2 for p in coords)
    assert sum(p['mode']=='walk' for p in baseline)==150
    assert sum(p['mode']=='electric' for p in baseline)>150
    assert sum(p['mode']=='bicycle' for p in baseline)>150
    assert len([a for a in d['areas'] if a['hotspot']])==len(HOTSPOTS)==13
    def metrics(agents):
        counts={a['id']:0 for a in d['areas']}
        for a in agents:
            if a['area_id'] and a['start']+a['travel_seconds']+18<=1800:counts[a['area_id']]+=d['cohort_per_vehicle']
        ratios=[counts[a['id']]/a['capacity'] for a in d['areas']]
        return sum(counts.values()),max(ratios),sum(r>1 for r in ratios)
    b=metrics(baseline);g=metrics(guided)
    assert sum(bool(a['area_id']) for a in baseline)==sum(bool(a['area_id']) for a in guided)
    assert d['cohort_per_vehicle']==1
    assert b[0]<=sum(p['mode']!='walk' for p in baseline)<=1000
    assert g[1]<b[1] and g[2]<=b[2]
    assert d['is_observed'] is False
    assert all(sum(d['cohort_per_vehicle'] for p in baseline if p['area_id']==a['id'])>0 for a in d['areas'])
    assert any(p.get('illegal') for p in baseline)
    for case in (baseline,guided):
        for a in d['areas']:
            parked=[p for p in case if p['area_id']==a['id']]
            assert sum(d['cohort_per_vehicle'] for p in parked if not p.get('illegal'))<=a['capacity']+.01


def test_morning_reproducible():
    graph=json.loads((DEFAULT_FILE.parent/'network.osm.json').read_text(encoding='utf-8'))
    places=json.loads((DEFAULT_FILE.parent/'places.osm.json').read_text(encoding='utf-8'))['items']
    assert generate(graph,load_parking(),places,100,42)==generate(graph,load_parking(),places,100,42)


def test_full_population_creates_hotspots_without_scaling_vehicle_counts():
    graph=json.loads((DEFAULT_FILE.parent/'network.osm.json').read_text(encoding='utf-8'))
    places=json.loads((DEFAULT_FILE.parent/'places.osm.json').read_text(encoding='utf-8'))['items']
    d=generate(graph,load_parking(),places,4000)
    assert len(d['cases']['baseline'])==4000 and not d['excluded']
    for case in d['cases'].values():
        assert sum(p['mode']=='walk' for p in case)==600
        assert sum(p['mode']!='walk' for p in case)==3400
        parked=sum(bool(p['area_id']) and p['start']+p['travel_seconds']+18<=1800 for p in case)
        assert 0<parked<=3400  # Slow traffic may remain in transit at 08:30.
    loads={a['id']:sum(p['area_id']==a['id'] for p in d['cases']['baseline']) for a in d['areas']}
    assert all(n>0 for n in loads.values())
    assert sum(loads.values())==3400 and d['cohort_per_vehicle']==1
    assert any(loads[a['id']]>a['capacity'] for a in d['areas'] if a['hotspot'])
    guided=d['cases']['guided']
    assert sum(a['destination_name'].startswith('鸿远') for a in guided)==800
    for area in d['areas']:
        assert sum(a['area_id']==area['id'] for a in guided)<=area['capacity']
    assert all(a['start']==b['start'] for a,b in zip(d['cases']['baseline'],guided))
    assert any(a.get('board_at') for a in guided) and any(a.get('via_path') for a in guided)
    assert len(d['timeline']['guided'])==61
    assert d['metrics']['guided']['over']==0

    assert sum(a['destination_name'].startswith('修远') for a in guided)==2000
    assert sum(a['destination_name'].startswith('明远') for a in guided)==1200
    assert d['metrics']['baseline']['trip']-d['metrics']['guided']['trip']>2
    assert len(d['accidents']['guided'])==1 and len(d['accidents']['baseline'])==4
    assert len({e['teaching_group'] for e in d['accidents']['baseline']})==3
    assert any(w['road_name']=='修远大道' for w in d['metrics']['baseline']['congestion_windows'])
    assert d['metrics']['baseline']['congestion_windows']
