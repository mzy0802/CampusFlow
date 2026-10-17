import {inside} from './simulationMath.js'

// Violations park right around the full parking area, never inside buildings
// or inside any parking polygon. Deterministic per area so zooming never moves a vehicle.
export function areaSurroundSpots(areaRing,center,excludeRings,{radius=80,spacing=4,limit=100,seed=1}={}){
 if(!areaRing?.length)return []
 const sx=111320*Math.cos(center[1]*Math.PI/180),sy=111320
 const meters=p=>[(p[0]-center[0])*sx,(p[1]-center[1])*sy]
 const ring=areaRing.map(meters),excluded=(excludeRings||[]).map(r=>r.map(meters))
 const segmentDistance=(p,a,b)=>{const dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy||1)));return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy)}
 function blocked(p){
  if(Math.hypot(p[0],p[1])>radius)return true
  if(inside(p,ring))return true
  if(ring.some((a,i)=>segmentDistance(p,a,ring[(i+1)%ring.length])<1.5))return true
  for(const r of excluded){
   if(r.length>=3&&inside(p,r))return true
   if(r.some((a,i)=>segmentDistance(p,a,r[(i+1)%r.length])<1.5))return true
  }
  return false
 }
 let s=(seed>>>0)||1
 const random=()=>{s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296}
 const result=[],seen=new Set()
 for(let i=0;i<ring.length&&result.length<limit;i++){
  const a=ring[i],b=ring[(i+1)%ring.length],length=Math.hypot(b[0]-a[0],b[1]-a[1])
  if(length<1)continue
  const nx=-(b[1]-a[1])/length,ny=(b[0]-a[0])/length
  for(let d=0;d<=length&&result.length<limit;d+=spacing){
   const t=d/length,off=2+random()*12
   for(const sign of (random()<.5?[1,-1]:[-1,1])){
    const p=[a[0]+(b[0]-a[0])*t+nx*off*sign,a[1]+(b[1]-a[1])*t+ny*off*sign]
    const key=Math.round(p[0]/spacing)+','+Math.round(p[1]/spacing)
    if(!seen.has(key)&&!blocked(p)){seen.add(key);result.push([center[0]+p[0]/sx,center[1]+p[1]/sy]);break}
   }
  }
 }
 return result
}
