// Project each road only when the map changes, rather than per actor/trail sample.
export class ScreenRoutes {
 constructor(map,paths){this.map=map;this.paths=paths;this.cache=new Map()}
 clear(){this.cache.clear()}
 get(id){if(this.cache.has(id))return this.cache.get(id);const geo=this.paths[id]?.coordinates||[[0,0],[0,0]],points=geo.map(p=>this.map.latLngToContainerPoint([p[1],p[0]])),lengths=[0];let total=0;for(let i=1;i<geo.length;i++){total+=Math.hypot((geo[i][0]-geo[i-1][0])*Math.cos(geo[i][1]*Math.PI/180),geo[i][1]-geo[i-1][1]);lengths.push(total)}const full=new Path2D();points.forEach((p,i)=>i?full.lineTo(p.x,p.y):full.moveTo(p.x,p.y));const r={points,lengths,total,full,bucket:-1,partial:null};this.cache.set(id,r);return r}
 sample(id,p){const r=this.get(id),at=Math.max(0,Math.min(1,p))*r.total;let lo=1,hi=r.points.length-1;while(lo<hi){const m=(lo+hi)>>1;if(r.lengths[m]<at)lo=m+1;else hi=m}const i=Math.max(1,lo),a=r.points[i-1]||r.points[0],b=r.points[i]||a,t=(at-r.lengths[i-1])/(r.lengths[i]-r.lengths[i-1]||1);return {x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t}}
 trace(id,progress){const r=this.get(id);if(progress>=1)return r.full;const bucket=Math.floor(progress*80);if(r.bucket===bucket)return r.partial;r.bucket=bucket;const p=bucket/80,at=p*r.total,path=new Path2D();path.moveTo(r.points[0].x,r.points[0].y);for(let i=1;i<r.points.length&&r.lengths[i]<at;i++)path.lineTo(r.points[i].x,r.points[i].y);const end=this.sample(id,p);path.lineTo(end.x,end.y);r.partial=path;return path}
}
