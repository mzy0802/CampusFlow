"""Offline, reproducible conversion of the attributed OSM campus extract."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
raw = json.loads((ROOT / 'data/osm/weishui.raw.json').read_text(encoding='utf-8'))
elements = raw['elements']
nodes = {n['id']: n for n in elements if n['type'] == 'node'}
boundary = next(w for w in elements if w['type'] == 'way' and w['id'] == 271773865)
ring = [(nodes[n]['lon'], nodes[n]['lat']) for n in boundary['nodes']]

def inside(point):
    x, y = point
    result = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:]):
        if abs((x-ax)*(by-ay)-(y-ay)*(bx-ax)) < 1e-12 and min(ax,bx)-1e-10 <= x <= max(ax,bx)+1e-10 and min(ay,by)-1e-10 <= y <= max(ay,by)+1e-10:
            return True
        if (ay > y) != (by > y) and x < (bx-ax)*(y-ay)/(by-ay)+ax:
            result = not result
    return result

graph = {'schema_version': 1, 'dataset': 'campus', 'revision': 0, 'nodes': [], 'edges': []}
used = {}
features = []
labels = {'footway':'步行道', 'path':'路径', 'residential':'校内道路', 'pedestrian':'步行区域道路', 'service':'服务道路', 'steps':'台阶', 'cycleway':'自行车道'}
for way in elements:
    tags = way.get('tags', {})
    if way['type'] != 'way' or 'highway' not in tags or tags.get('area') == 'yes':
        continue
    highway = tags['highway']
    name = tags.get('name:zh') or tags.get('name') or labels.get(highway, highway)
    modes = ['walk'] if highway in ('footway', 'steps', 'pedestrian', 'path') else ['walk', 'bike']
    if tags.get('bicycle') in ('yes', 'designated', 'permissive') and 'bike' not in modes: modes.append('bike')
    for mode, key in [('walk','foot'), ('bike','bicycle')]:
        if tags.get(key, tags.get('access')) in ('no','private') and mode in modes: modes.remove(mode)
    for i, (a,b) in enumerate(zip(way['nodes'], way['nodes'][1:])):
        pa=(nodes[a]['lon'], nodes[a]['lat']); pb=(nodes[b]['lon'], nodes[b]['lat'])
        if pa == pb or not all(inside(p) for p in (pa,pb,((pa[0]+pb[0])/2,(pa[1]+pb[1])/2))): continue
        edge_id=f'osm_w{way["id"]}_{i}'
        features.append({'type':'Feature','properties':{'id':edge_id,'name':name,'osm_way_id':way['id'],'highway':highway,'tags':tags,'verified':False,'source':'OpenStreetMap contributors'},'geometry':{'type':'LineString','coordinates':[pa,pb]}})
        if not modes: continue
        for n in (a,b): used.setdefault(n, f'{name} · {n}')
        # Conservative pending-review representation; no edge routes until verified.
        source,target=(b,a) if tags.get('oneway')=='-1' else (a,b)
        graph['edges'].append({'id':edge_id,'source':f'osm_n{source}','target':f'osm_n{target}','modes':modes,'bidirectional':tags.get('oneway') not in ('yes','1','true','-1'),'congestion':1,'verified':False})
graph['nodes']=[{'id':f'osm_n{n}','name':name,'longitude':nodes[n]['lon'],'latitude':nodes[n]['lat'],'kind':'junction'} for n,name in sorted(used.items())]
for name, data in [('network.osm.json',graph), ('roads.osm.geojson',{'type':'FeatureCollection','features':features}), ('campus-boundary.osm.geojson',{'type':'Feature','properties':boundary['tags'],'geometry':{'type':'Polygon','coordinates':[ring]}})]:
    (ROOT/'data'/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'{len(graph["nodes"])} nodes, {len(graph["edges"])} edges, {len(features)} map segments; all unverified')
