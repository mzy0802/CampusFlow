// Planned camera mounting points: convex exterior building corners, never POIs
// shifted onto a footpath. Coverage is a short directional sector, not a disk.
const sx=111320*Math.cos(34.37*Math.PI/180),sy=111320
const meters=(a,b)=>Math.hypot((a[0]-b[0])*sx,(a[1]-b[1])*sy)
export function exteriorCorners(ring){
 const p=ring.slice(0,-1).map(q=>[...q]).sort((a,b)=>a[0]-b[0]||a[1]-b[1])
 const cross=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
 const half=values=>{const h=[];for(const q of values){while(h.length>1&&cross(h.at(-2),h.at(-1),q)<=0)h.pop();h.push(q)}return h.slice(0,-1)}
 return [...half(p),...half([...p].reverse())]
}
export function cameraPlan(areas,buildings){
 const schools=buildings.filter(f=>/^(修远|明远|鸿远)教学楼/.test(f.properties?.tags?.name||''))
 const corners=schools.flatMap(f=>exteriorCorners(f.geometry.coordinates[0]).map(point=>({point,building:f.properties.tags.name,building_id:f.properties.id})))
 const targets=areas.filter(a=>a.hotspot||/修远大停车场|修远3东|修远4北|明远1西侧|明远4东北角|鸿远1区东|鸿远2区东/.test(a.name))
 const used=new Set(),result=[]
 for(const area of targets){
  const target=[area.longitude,area.latitude],options=corners.filter(c=>c.building.startsWith(area.name.slice(0,2))).sort((a,b)=>meters(a.point,target)-meters(b.point,target))
  const mount=options.find(c=>!used.has(c.point.join(',')))
  if(!mount||meters(mount.point,target)>65)continue
  used.add(mount.point.join(','))
  const heading=Math.atan2((target[0]-mount.point[0])*sx,(target[1]-mount.point[1])*sy)
  result.push({...mount,id:'camera-'+area.id,name:area.name+'摄像头',target,heading,radius:Math.min(42,Math.max(24,meters(mount.point,target)+8)),fov:56,height_m:6,group:area.name.slice(0,2),demo:result.length%2+1})
 }
 // Two building-mounted views also monitor the major road closest to the
 //教学楼南侧; their targets are supplied separately by addRoadCamera below.
 return result
}
export function addRoadCamera(cameras,buildings,roads){
 const options=[]
 for(const f of buildings){
  if(!/^(修远|明远|鸿远)教学楼/.test(f.properties?.tags?.name||''))continue
  for(const corner of exteriorCorners(f.geometry.coordinates[0]))for(const road of roads){
   if(road.properties?.name!=='修远大道')continue
   const [a,b]=road.geometry.coordinates,dx=(b[0]-a[0])*sx,dy=(b[1]-a[1])*sy,t=Math.max(0,Math.min(1,((corner[0]-a[0])*sx*dx+(corner[1]-a[1])*sy*dy)/(dx*dx+dy*dy||1))),target=[a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])],gap=meters(corner,target)
   if(gap>8&&gap<=38&&!cameras.some(c=>meters(c.point,corner)<4))options.push({point:corner,target,building:f.properties.tags.name,building_id:f.properties.id,gap})
  }
 }
 options.sort((a,b)=>a.gap-b.gap)
 for(const o of options){if(cameras.filter(c=>c.road_view).length>=2)break;if(cameras.some(c=>meters(c.point,o.point)<45))continue;cameras.push({...o,id:'camera-road-'+cameras.length,name:'修远大道路口摄像头',heading:Math.atan2((o.target[0]-o.point[0])*sx,(o.target[1]-o.point[1])*sy),radius:Math.min(42,Math.max(24,o.gap+9)),fov:56,height_m:6,group:o.building.slice(0,2),demo:1,road_view:true})}
 return cameras
}
export function cameraSector(camera){
 const coords=[[camera.point[1],camera.point[0]]],half=camera.fov*Math.PI/360
 for(let i=0;i<=20;i++){const angle=camera.heading-half+2*half*i/20;coords.push([camera.point[1]+Math.cos(angle)*camera.radius/sy,camera.point[0]+Math.sin(angle)*camera.radius/sx])}
 coords.push(coords[0]);return coords
}
