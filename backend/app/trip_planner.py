"""Dijkstra over explicit surveyed edges; no invented connections or snapping."""
from math import radians, sin, cos, asin, sqrt
import heapq

def distance(a,b):
    lat1,lat2=radians(a['latitude']),radians(b['latitude'])
    dlat=lat2-lat1;dlon=radians(b['longitude']-a['longitude'])
    return 6371000*2*asin(min(1,sqrt(sin(dlat/2)**2+cos(lat1)*cos(lat2)*sin(dlon/2)**2)))

def adjacency(network,mode,speed,by_distance=False):
    nodes={n['id']:n for n in network['nodes']};graph={i:[] for i in nodes}
    for edge in network['edges']:
        if mode not in edge['modes'] or not edge['verified']: continue
        a,b=edge['source'],edge['target'];meters=distance(nodes[a],nodes[b])
        seconds=meters/(speed/3.6)*edge['congestion']
        weight=meters if by_distance else seconds
        graph[a].append((b,weight,meters,seconds))
        if edge['bidirectional']:graph[b].append((a,weight,meters,seconds))
    return graph

def shortest(graph,start):
    dist={start:0};prev={};queue=[(0,start)]
    while queue:
        cost,node=heapq.heappop(queue)
        if cost!=dist[node]: continue
        for target,weight,meters,seconds in graph[node]:
            total=cost+weight
            if total<dist.get(target,float('inf')):
                dist[target]=total;prev[target]=(node,meters,seconds);heapq.heappush(queue,(total,target))
    return dist,prev

def segment(nodes,prev,start,end,mode):
    path=[end];meters=seconds=0;current=end
    while current!=start:
        parent,m,s=prev[current];meters+=m;seconds+=s;current=parent;path.append(current)
    path.reverse()
    coords=[[nodes[n]['longitude'],nodes[n]['latitude']] for n in path]
    geometry={'type':'LineString','coordinates':coords} if len(coords)>1 else {'type':'Point','coordinates':coords[0]}
    return {'mode':mode,'node_ids':path,'distance_m':round(meters,1),'duration_seconds':round(seconds,1),
            'geojson':{'type':'Feature','properties':{'mode':mode},'geometry':geometry}}

def plan(network,request,status):
    nodes={n['id']:n for n in network['nodes']}
    if request.origin_id not in nodes or request.destination_id not in nodes: raise ValueError('起终点不在已保存路网中')
    bike=adjacency(network,'bike',request.bike_speed_kmh)
    walk=adjacency(network,'walk',request.walk_speed_kmh,request.preference=='less_walking')
    bike_dist,bike_prev=shortest(bike,request.origin_id)
    # Reverse walking graph computes every parking-to-destination path in one pass.
    reverse={n:[] for n in walk}
    for a,links in walk.items():
        for b,w,m,s in links: reverse[b].append((a,w,m,s))
    walk_dist,walk_prev=shortest(reverse,request.destination_id)
    candidates=[];excluded=[]
    for node in nodes.values():
        if node['kind']!='parking':continue
        nid=node['id'];item=status.get(node.get('parking_id') or nid)
        if not item or item['available']<request.min_available:
            excluded.append({'id':nid,'reason':'空位不足或状态缺失'});continue
        if nid not in bike_dist or nid not in walk_dist:
            excluded.append({'id':nid,'reason':'骑行或步行道路不连通（仅使用已核验道路）'});continue
        ride=segment(nodes,bike_prev,request.origin_id,nid,'bike')
        backward=segment(nodes,walk_prev,request.destination_id,nid,'walk')
        backward['node_ids'].reverse()
        if backward['geojson']['geometry']['type']=='LineString': backward['geojson']['geometry']['coordinates'].reverse()
        total=ride['duration_seconds']+backward['duration_seconds']+request.parking_minutes*60
        candidates.append({'parking_node_id':nid,'parking_id':node.get('parking_id') or nid,'name':node['name'],
            'available':item['available'],'capacity':item['capacity'],'total_minutes':round(total/60,2),
            'walk_distance_m':backward['distance_m'],'segments':[ride,backward],
            'score_seconds':total,'reason':'按步行距离优先、总耗时其次排序' if request.preference=='less_walking' else '按骑行、停车和步行总耗时排序'})
    candidates.sort(key=lambda x:(x['walk_distance_m'],x['score_seconds'],x['parking_node_id']) if request.preference=='less_walking' else (x['score_seconds'],x['walk_distance_m'],x['parking_node_id']))
    for c in candidates:c.pop('score_seconds')
    return {'status':'ok' if candidates else 'no_route','dataset':network['dataset'],'is_example':network['dataset']=='example',
            'network_revision':network['revision'],'preference':request.preference,'recommended':candidates[0] if candidates else None,
            'alternatives':candidates[1:5],'excluded':excluded,
            'assumptions':{'bike_speed_kmh':request.bike_speed_kmh,'walk_speed_kmh':request.walk_speed_kmh,'parking_minutes':request.parking_minutes,
                           'congestion':'道路时间乘数，由编辑者设置，非实测拥堵'},
            'transit':{'status':'not_configured','message':'公交线路与时刻尚未提供，不生成公交方案。'},
            'warnings':['停车空位为模拟数据，预计耗时基于设定速度，并非实时预测。','路线只沿已核验的录入道路计算；未核验道路不参与规划。']}
