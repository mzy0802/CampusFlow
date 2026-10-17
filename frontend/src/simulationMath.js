export function routePoint(path, progress){
  if(!path?.length)return [0,0]
  if(!path._lengths){let total=0;path._lengths=[0];for(let i=1;i<path.length;i++){total+=Math.hypot((path[i][0]-path[i-1][0])*Math.cos(path[i][1]*Math.PI/180),path[i][1]-path[i-1][1]);path._lengths.push(total)}path._total=total}
  const at=Math.max(0,Math.min(1,progress))*path._total
  let lo=1,hi=path.length-1;while(lo<hi){const mid=(lo+hi)>>1;if(path._lengths[mid]<at)lo=mid+1;else hi=mid}
  const i=Math.max(1,lo),a=path[i-1]||path[0],b=path[i]||a,t=(at-path._lengths[i-1])/(path._lengths[i]-path._lengths[i-1]||1)
  return [a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t]
}
export function phase(agent,time,paths){
  const elapsed=time-agent.start
  if(elapsed<0)return {kind:'waiting'}
  if(elapsed<agent.travel_seconds)return {kind:'moving',mode:agent.mode,path:agent.path,progress:elapsed/agent.travel_seconds}
  if(agent.mode==='walk')return elapsed<agent.travel_seconds+12?{kind:'entering',mode:'walk',progress:(elapsed-agent.travel_seconds)/12}:{kind:'arrived'}
  if(elapsed<agent.travel_seconds+18)return {kind:'parking',area:agent.area_id,progress:(elapsed-agent.travel_seconds)/18}
  if(elapsed<agent.travel_seconds+36)return {kind:'dismount',area:agent.area_id,progress:(elapsed-agent.travel_seconds-18)/18}
  if(elapsed<agent.travel_seconds+60)return {kind:'leaving',area:agent.area_id,progress:(elapsed-agent.travel_seconds-36)/24}
  const tail=paths[agent.walk_path]
  if(tail&&elapsed<agent.travel_seconds+60+tail.seconds)return {kind:'walking',mode:'walk',path:agent.walk_path,progress:(elapsed-agent.travel_seconds-60)/tail.seconds}
  const finish=agent.travel_seconds+60+(tail?.seconds||0)
  if(elapsed<finish+12)return {kind:'entering',mode:'walk',progress:(elapsed-finish)/12,area:agent.area_id}
  return {kind:'arrived',area:agent.area_id}
}
export function occupancy(agents,time,weight){const counts={};for(const a of agents)if(a.area_id&&time>=a.start+a.travel_seconds+18)counts[a.area_id]=(counts[a.area_id]||0)+weight;return counts}
export function inside(point,ring){let yes=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const a=ring[i],b=ring[j];if((a[1]>point[1])!==(b[1]>point[1])&&point[0]<(b[0]-a[0])*(point[1]-a[1])/(b[1]-a[1])+a[0])yes=!yes}return yes}

export function arrivalTime(a,paths){return a.start+a.travel_seconds+(a.mode==='walk'?12:72+(paths[a.walk_path]?.seconds||0))}
export function parkingTotals(agents,time,weight){const loads={},illegal={};for(const a of agents)if(a.area_id&&time>=a.start+a.travel_seconds+18){loads[a.area_id]=(loads[a.area_id]||0)+weight;if(a.illegal)illegal[a.area_id]=(illegal[a.area_id]||0)+weight}return {loads,illegal}}
export function parkingLabelPoint(ring,zoom){const xs=ring.map(p=>p.x),ys=ring.map(p=>p.y);const scale=Math.max(.46,Math.min(.9,.46+(zoom-14)*.085));return {x:(Math.min(...xs)+Math.max(...xs))/2,y:zoom>=17?Math.min(...ys)-14-17*scale:(Math.min(...ys)+Math.max(...ys))/2,scale,outside:zoom>=17}}
