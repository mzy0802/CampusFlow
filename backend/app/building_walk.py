"""Walk-only building permeability, based on OSM outlines and the owner's rule.

Connections are modelled access points, not surveyed door positions. Polygon
holes are respected. The saved road graph and bicycle permissions stay intact.
"""
import heapq
import json
import math
from functools import lru_cache


def inside(p,ring):
    hit=False
    for a,b in zip(ring,ring[1:]+ring[:1]):
        if (a[1]>p[1])!=(b[1]>p[1]) and p[0]<(b[0]-a[0])*(p[1]-a[1])/(b[1]-a[1])+a[0]:hit=not hit
    return hit


def nearest(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1];t=max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy or 1)))
    q=(a[0]+t*dx,a[1]+t*dy)
    return q,math.dist(p,q)


def boundary_distance(p,ring):
    return min((nearest(p,a,b) for a,b in zip(ring,ring[1:]+ring[:1])),key=lambda x:x[1])


def visible(a,b,rings):
    # Split the line at every polygon-edge crossing, then test each interval.
    cuts=[0,1];dx,dy=b[0]-a[0],b[1]-a[1]
    for ring in rings:
        for c,d in zip(ring,ring[1:]+ring[:1]):
            ex,ey=d[0]-c[0],d[1]-c[1];den=dx*ey-dy*ex
            if abs(den)<1e-9:continue
            cx,cy=c[0]-a[0],c[1]-a[1];t=(cx*ey-cy*ex)/den;u=(cx*dy-cy*dx)/den
            if 0<t<1 and 0<=u<=1:cuts.append(t)
    cuts=sorted(set(cuts))
    for low,high in zip(cuts,cuts[1:]):
        t=(low+high)/2;p=(a[0]+t*dx,a[1]+t*dy)
        if not inside(p,rings[0]) and boundary_distance(p,rings[0])[1]>.02:return False
        if any(inside(p,r) and boundary_distance(p,r)[1]>.02 for r in rings[1:]):return False
    return True


def building_connections(feature,road_nodes):
    rings_geo=feature['geometry']['coordinates'];outer=rings_geo[0][:-1]
    center=(sum(p[0] for p in outer)/len(outer),sum(p[1] for p in outer)/len(outer))
    sx=111320*math.cos(center[1]*math.pi/180);sy=111320
    to_xy=lambda p:((p[0]-center[0])*sx,(p[1]-center[1])*sy)
    to_geo=lambda p:(p[0]/sx+center[0],p[1]/sy+center[1])
    rings=[[to_xy(p) for p in ring[:-1]] for ring in rings_geo]
    candidates=[]
    for n in road_nodes:
        p=to_xy((n['longitude'],n['latitude']));q,gap=min((boundary_distance(p,r) for r in rings),key=lambda x:x[1])
        if inside(p,rings[0]) and not any(inside(p,r) for r in rings[1:]):q=p;gap=0
        if gap<=18:candidates.append((n,q,gap))
    if len(candidates)<2:return [],[]
    # Spread a bounded set of access points around the outline; don't let one
    # dense road junction crowd out the opposite side of the building.
    selected=[min(candidates,key=lambda x:x[2])]
    remaining=[c for c in candidates if c is not selected[0]]
    while remaining and len(selected)<8:
        c=max(remaining,key=lambda c:min(math.dist(c[1],s[1]) for s in selected))
        if min(math.dist(c[1],s[1]) for s in selected)<5:break
        selected.append(c);remaining.remove(c)
    points=[p for ring in rings for p in ring]+[c[1] for c in selected]
    offset=len(points)-len(selected);links={i:[] for i in range(len(points))}
    for i,a in enumerate(points):
        for j in range(i+1,len(points)):
            b=points[j]
            if visible(a,b,rings):
                length=math.dist(a,b);links[i].append((j,length));links[j].append((i,length))
    used=set()
    for start in range(offset,len(points)):
        queue=[(0,start)];costs={start:0};previous={}
        while queue:
            cost,u=heapq.heappop(queue)
            if cost!=costs[u]:continue
            for v,length in links[u]:
                value=cost+length
                if value<costs.get(v,float('inf')):costs[v]=value;previous[v]=u;heapq.heappush(queue,(value,v))
        for end in range(start+1,len(points)):
            if end not in costs:continue
            v=end
            while v!=start:
                u=previous[v];used.add(tuple(sorted((u,v))));v=u
    prefix='indoor:'+feature['properties']['id']+':'
    active={i for pair in used for i in pair};nodes=[];edges=[]
    for i in active:
        x,y=to_geo(points[i]);nodes.append({'id':prefix+str(i),'name':feature['properties']['tags']['name']+'步行连接','longitude':x,'latitude':y,'kind':'intersection'})
    def edge(a,b,key):return {'id':prefix+key,'source':a,'target':b,'modes':['walk'],'verified':True,'bidirectional':True,'congestion':1,'source_type':'owner_building_permeability','building_id':feature['properties']['id']}
    for i,j in used:edges.append(edge(prefix+str(i),prefix+str(j),f'{i}-{j}'))
    for k,(n,q,gap) in enumerate(selected):
        if offset+k in active:edges.append(edge(n['id'],prefix+str(offset+k),'access-'+str(k)))
    return nodes,edges


@lru_cache(maxsize=4)
def additions(node_signature,walk_ids,buildings_json):
    road_nodes=[{'id':i,'longitude':x,'latitude':y} for i,x,y in node_signature if i in walk_ids]
    nodes=[];edges=[]
    for feature in json.loads(buildings_json)['features']:
        name=feature['properties'].get('tags',{}).get('name','')
        if not any(name.startswith(k) for k in ('修远教学楼','明远教学楼','鸿远教学楼')):continue
        n,e=building_connections(feature,road_nodes);nodes+=n;edges+=e
    return nodes,edges


@lru_cache(maxsize=2)
def load_buildings(path,mtime):
    return path.read_text(encoding='utf-8')


def walking_network(graph):
    if graph.get('_building_walk'):return graph
    from .navigation import datafile
    path=datafile('buildings.osm.geojson')
    if not path.exists():return graph
    sig=tuple((n['id'],n['longitude'],n['latitude']) for n in graph['nodes'])
    ids=frozenset(k for e in graph['edges'] if e['verified'] and 'walk' in e['modes'] for k in (e['source'],e['target']))
    raw=load_buildings(path,path.stat().st_mtime_ns)
    nodes,edges=additions(sig,ids,raw)
    rings=[f['geometry']['coordinates'][0] for f in json.loads(raw)['features'] if any(f['properties'].get('tags',{}).get('name','').startswith(k) for k in ('修远教学楼','明远教学楼','鸿远教学楼'))]
    return {**graph,'nodes':graph['nodes']+nodes,'edges':graph['edges']+edges,'_building_walk':True,'_building_rings':rings}
