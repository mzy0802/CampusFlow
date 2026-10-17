export function routePoint(path, progress){
  if(!path?.length)return [0,0]
  if(!path._lengths){let total=0;path._lengths=[0];for(let i=1;i<path.length;i++){total+=Math.hypot((path[i][0]-path[i-1][0])*Math.cos(path[i][1]*Math.PI/180),path[i][1]-path[i-1][1]);path._lengths.push(total)}path._total=total}
  const at=Math.max(0,Math.min(1,progress))*path._total
  let lo=1,hi=path.length-1;while(lo<hi){const mid=(lo+hi)>>1;if(path._lengths[mid]<at)lo=mid+1;else hi=mid}
  const i=Math.max(1,lo),a=path[i-1]||path[0],b=path[i]||a,t=(at-path._lengths[i-1])/(path._lengths[i]-path._lengths[i-1]||1)
  return [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]
}
export function paceAt(pace,elapsed){
  if(!pace?.length)return null
  const last=pace.length-1
  if(elapsed<=pace[0][0])return pace[0][1]
  if(elapsed>=pace[last][0])return pace[last][1]
  let lo=0,hi=last
  while(lo<hi-1){const m=(lo+hi)>>1;if(pace[m][0]<elapsed)lo=m;else hi=m}
  const [t0,p0]=pace[lo],[t1,p1]=pace[hi]
  return p0+(p1-p0)*(elapsed-t0)/((t1-t0)||1)
}
export function phase(agent,time,paths){
  const elapsed=time-agent.start,park=agent.parking_seconds??18
  if(elapsed<0)return {kind:'waiting'}
  const leg1=agent.leg1_seconds||0,dwell=agent.dwell_seconds||0
  if(agent.via_path!=null){
    if(elapsed<leg1)return {kind:'moving',mode:agent.mode,path:agent.via_path,progress:paceAt(agent.leg1_pace||agent.pace,elapsed)??elapsed/Math.max(1,leg1),leg:'canteen'}
    if(elapsed<leg1+dwell)return {kind:'dining',area:agent.via_area_id,progress:dwell?(elapsed-leg1)/dwell:1}
    if(elapsed<agent.travel_seconds)return {kind:'moving',mode:agent.mode,path:agent.path,progress:paceAt(agent.travel_pace,elapsed-leg1-dwell)??paceAt(agent.pace,elapsed)??(elapsed-leg1-dwell)/Math.max(1,agent.travel_seconds-leg1-dwell)}
  }else if(elapsed<agent.travel_seconds)return {kind:'moving',mode:agent.mode,path:agent.path,progress:paceAt(agent.travel_pace||agent.pace,elapsed)??elapsed/agent.travel_seconds}
  if(agent.mode==='walk')return elapsed<agent.travel_seconds+12?{kind:'entering',mode:'walk',progress:(elapsed-agent.travel_seconds)/12}:{kind:'arrived'}
  if(elapsed<agent.travel_seconds+park)return {kind:'parking',area:agent.area_id,progress:(elapsed-agent.travel_seconds)/park}
  if(elapsed<agent.travel_seconds+park+18)return {kind:'dismount',area:agent.area_id,progress:(elapsed-agent.travel_seconds-park)/18}
  if(elapsed<agent.travel_seconds+park+42)return {kind:'leaving',area:agent.area_id,progress:(elapsed-agent.travel_seconds-park-18)/24}
  const tail=paths[agent.walk_path],tailSeconds=agent.walk_seconds??tail?.seconds
  if(tail&&elapsed<agent.travel_seconds+park+42+tailSeconds)return {kind:'walking',mode:'walk',path:agent.walk_path,progress:paceAt(agent.walk_pace,elapsed-agent.travel_seconds-park-42)??(elapsed-agent.travel_seconds-park-42)/tailSeconds}
  const finish=agent.travel_seconds+park+42+(tailSeconds||0)
  if(elapsed<finish+12)return {kind:'entering',mode:'walk',progress:(elapsed-finish)/12,area:agent.area_id}
  return {kind:'arrived',area:agent.area_id}
}
function canteenParked(a,time){return a.via_area_id&&a.leg1_seconds!=null&&time>=a.start+a.leg1_seconds+18&&time<a.start+a.leg1_seconds+(a.dwell_seconds||0)}
export function occupancy(agents,time,weight){const counts={};for(const a of agents){if(a.area_id&&time>=a.start+a.travel_seconds+(a.parking_seconds??18))counts[a.area_id]=(counts[a.area_id]||0)+weight;if(canteenParked(a,time))counts[a.via_area_id]=(counts[a.via_area_id]||0)+weight}return counts}
export function inside(point,ring){let yes=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a[1]>point[1])!==(b[1]>point[1])&&point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])yes=!yes}return yes}

export function arrivalTime(a,paths){return a.start+a.travel_seconds+(a.mode==='walk'?12:(a.parking_seconds??18)+54+(a.walk_seconds??paths[a.walk_path]?.seconds??0))}
export function zoneDetailsAt(agents,time,paths){
 const zones=Object.fromEntries(['食堂','修远','明远','鸿远'].map(g=>[g,{incoming:0,outgoing:0,active:0,arrived:0,dorm_source:0,canteen_source:0}]))
 for(const a of agents){
  const first=a.leg1_seconds||0,dwell=a.dwell_seconds||0,via=a.via_path!=null,end=arrivalTime(a,paths),group=(a.destination_name||'').slice(0,2),reach=a.start+first,leave=reach+dwell
  if(via){if(time-60<reach&&reach<=time)zones['食堂'].incoming++;if(time-60<leave&&leave<=time)zones['食堂'].outgoing++;if(a.start<=time&&time<leave){zones['食堂'].active++;continue}}
  if(a.board_at&&time-60<a.start&&a.start<=time)zones['食堂'].outgoing++
  if(!zones[group])continue
  if(time-60<end&&end<=time)zones[group].incoming++
  if(end<=time)zones[group].arrived++
  if(a.start<=time&&time<end){zones[group].active++;zones[group][a.board_at||via&&time>=leave?'canteen_source':'dorm_source']++}
 }
 return zones
}
export function parkingTotals(agents,time,weight){const loads={},illegal={};for(const a of agents){if(a.area_id&&time>=a.start+a.travel_seconds+(a.parking_seconds??18)){loads[a.area_id]=(loads[a.area_id]||0)+weight;if(a.illegal)illegal[a.area_id]=(illegal[a.area_id]||0)+weight}if(canteenParked(a,time))loads[a.via_area_id]=(loads[a.via_area_id]||0)+weight}return {loads,illegal}}
export function parkingLabelPoint(ring,zoom){const xs=ring.map(p=>p.x),ys=ring.map(p=>p.y);const scale=Math.max(.46,Math.min(.9,.46+(zoom-14)*.085));return {x:(Math.min(...xs)+Math.max(...xs))/2,y:zoom>=17?Math.min(...ys)-14-17*scale:(Math.min(...ys)+Math.max(...ys))/2,scale,outside:zoom>=17}}
