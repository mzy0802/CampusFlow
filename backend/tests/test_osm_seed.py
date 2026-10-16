import json
from pathlib import Path
from app.traffic_store import Store
from app.network_models import Network

DATA = Path(__file__).resolve().parents[2] / 'data'

def test_public_roads_preserve_original_coordinates():
    raw = json.loads((DATA/'osm/weishui.raw.json').read_text(encoding='utf-8'))
    original = {f'osm_n{n["id"]}': (n['lon'],n['lat']) for n in raw['elements'] if n['type']=='node'}
    graph = Network.model_validate_json((DATA/'network.osm.json').read_text(encoding='utf-8'))
    assert len(graph.edges) > 100
    assert all(e.verified for e in graph.edges)
    assert all((n.longitude,n.latitude)==original[n.id] for n in graph.nodes)
    assert all(n.kind=='junction' for n in graph.nodes)

def test_seed_only_initializes_untouched_database(tmp_path):
    store=Store(tmp_path/'test.sqlite3')
    assert store.seed_campus(DATA/'network.osm.json')
    graph=store.get('campus')
    assert graph['revision']==1
    assert not store.seed_campus(DATA/'network.osm.json')
    store.save(Network(dataset='campus',revision=1))
    assert not store.seed_campus(DATA/'network.osm.json')
    assert store.get('campus')['nodes']==[]
