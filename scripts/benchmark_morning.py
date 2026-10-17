"""Run from the project root: python scripts/benchmark_morning.py --count 1000."""
import argparse
import json
import statistics
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import run_backend
from app.data import load_parking,DEFAULT_FILE
from app.simulation import generate

parser=argparse.ArgumentParser()
parser.add_argument('--count','--population',type=int,default=4000,choices=range(100,8001),metavar='100..8000')
parser.add_argument('--seed',type=int,default=20261016)
args=parser.parse_args()
graph=json.loads((DEFAULT_FILE.parent/'network.osm.json').read_text(encoding='utf-8'))
places=json.loads((DEFAULT_FILE.parent/'places.osm.json').read_text(encoding='utf-8'))['items']
d=generate(graph,load_parking(),places,args.count,args.seed)
report={'source':d['source'],'is_observed':False,'count':d['generated_agents'],'seed':args.seed,'time':'08:30','notice':'Single synthetic scenario; not measured intervention effectiveness. Uses repository seed geometry/capacities, not local database edits.','cases':{}}
for case in ('baseline','guided'):
    loads={a['id']:0 for a in d['areas']}
    for p in d['cases'][case]:
        if p['area_id'] and p['start']+p['travel_seconds']+18<=1800:loads[p['area_id']]+=d['cohort_per_vehicle']
    ratios=[loads[a['id']]/a['capacity'] for a in d['areas']]
    report['cases'][case]={'parked':round(sum(loads.values()),2),'over_capacity_areas':sum(r>1 for r in ratios),'peak_percent':round(max(ratios)*100,2),'normalized_load_cv':round(statistics.pstdev(ratios)/(statistics.mean(ratios) or 1),4)}
print(json.dumps(report,ensure_ascii=False,indent=2))
