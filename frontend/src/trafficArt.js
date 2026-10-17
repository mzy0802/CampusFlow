// Canvas-native cartoon sprites. Cached frames keep 1000-agent scenes inexpensive.
const palette={walk:'#8662cc',bicycle:'#23a36c',electric:'#f08a36'}
const sprites=new Map()
function rounded(ctx,x,y,w,h,r,fill,stroke){ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fillStyle=fill;ctx.fill();if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=1.3;ctx.stroke()}}
function sprite(mode,rider,frame){const key=`${mode}/${rider}/${frame}`;if(sprites.has(key))return sprites.get(key);const c=document.createElement('canvas');c.width=112;c.height=112;const ctx=c.getContext('2d');ctx.scale(2,2);ctx.translate(28,28);ctx.lineCap='round';ctx.lineJoin='round';const color=palette[mode];
ctx.fillStyle='#283f4922';ctx.beginPath();ctx.ellipse(1,11,13,3,0,0,Math.PI*2);ctx.fill();
const stroke=(points,tone,width=2)=>{ctx.strokeStyle=tone;ctx.lineWidth=width;ctx.beginPath();points.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.stroke()};
if(mode==='walk'){
 const gait=Math.sin(frame*Math.PI/2)*2;stroke([[-3,6],[-4-gait,12]],'#343c60',3.4);stroke([[3,6],[4+gait,12]],'#343c60',3.4);stroke([[-4-gait,12],[-7-gait,12]],'#fffefa',2);stroke([[4+gait,12],[7+gait,12]],'#fffefa',2);
 rounded(ctx,-6,-4,12,13,4,color,'#fffefa');rounded(ctx,2,-3,5,9,2,'#d8c6ff','#665189');stroke([[-5,-1],[-8,3+gait]],'#f5c59e',3);stroke([[5,-1],[8,3-gait]],'#f5c59e',3);
}else{
 for(const x of [-11,11]){ctx.fillStyle='#304253';ctx.strokeStyle='#fffefa';ctx.lineWidth=1.3;ctx.beginPath();ctx.arc(x,8,5.5,0,Math.PI*2);ctx.fill();ctx.stroke();ctx.fillStyle='#c9d7df';ctx.beginPath();ctx.arc(x,8,2.7,0,Math.PI*2);ctx.fill()}
 if(mode==='bicycle'){stroke([[-11,8],[-4,-2],[4,8],[-11,8],[2,-2],[11,8]],color,3);stroke([[11,8],[8,-6],[13,-6]],'#405968',2);rounded(ctx,-8,-5,8,3,1,'#304253');stroke([[0,5],[Math.sin(frame*Math.PI/2)*3,10]],'#f9da9e',2)}
 else{rounded(ctx,-10,-1,20,10,4,color,'#fffefa');rounded(ctx,-8,-5,12,4,2,'#344d5d');rounded(ctx,2,2,5,4,1,'#fff5bf');stroke([[9,6],[9,-7],[14,-7]],'#4b6171',2);rounded(ctx,11,-5,4,4,1,'#ffefac');}
 if(rider){stroke([[-3,-2],[-5,4]],'#3f506c',3);rounded(ctx,-6,-11,11,10,3,mode==='bicycle'?'#5dc29b':'#f6b667','#fffefa');stroke([[4,-7],[9,-6]],'#efbf9c',2.5);rounded(ctx,-8,-10,5,8,2,'#526ba3');}
}
if(mode==='walk'||rider){
 const y=mode==='walk'?-12:-17
 ctx.fillStyle='#ffdbbc';ctx.strokeStyle='#fffefa';ctx.lineWidth=1.2;ctx.beginPath();ctx.ellipse(0,y,6,6.5,0,0,Math.PI*2);ctx.fill();ctx.stroke()
 // Short fringe stays strictly above the eyes; cheeks and chin remain clean.
 ctx.fillStyle='#66513f';ctx.beginPath();ctx.moveTo(-5.5,y-1.8);ctx.quadraticCurveTo(-7,y-8,0,y-7);ctx.quadraticCurveTo(7,y-7,5.5,y-1.8);ctx.lineTo(4,y-3.2);ctx.lineTo(2,y-2.4);ctx.lineTo(1,y-4);ctx.lineTo(-1,y-2.8);ctx.lineTo(-3,y-3.5);ctx.closePath();ctx.fill()
 ctx.fillStyle='#5a4b49';for(const x of [-2,2]){ctx.beginPath();ctx.arc(x,y+1,.55,0,Math.PI*2);ctx.fill()}
 ctx.fillStyle='#efb09e';ctx.beginPath();ctx.ellipse(-3.5,y+2.2,1,.6,0,0,Math.PI*2);ctx.ellipse(3.5,y+2.2,1,.6,0,0,Math.PI*2);ctx.fill()
 if(mode==='electric'){ctx.strokeStyle='#f8db84';ctx.lineWidth=2;ctx.beginPath();ctx.arc(0,y-1,6.5,Math.PI,2*Math.PI);ctx.stroke()}
}

sprites.set(key,c);return c}
export function drawActor(ctx,p,mode,size=1,angle=0,alpha=1,rider=true,time=0){const frame=Math.floor(time*2)%4,img=sprite(mode,rider,frame);ctx.save();ctx.translate(p.x,p.y);if(mode!=='walk'){// Face the travel direction while keeping heads upright on westbound segments.
if(Math.cos(angle)<0)ctx.scale(-1,1);ctx.rotate(Math.max(-.4,Math.min(.4,Math.sin(angle)*.4)))}ctx.globalAlpha=alpha;ctx.drawImage(img,-28*size,-28*size,56*size,56*size);ctx.restore()}
// Continuous racing ribbons: layered strokes replace expensive blur filters.
export function drawFlowPath(ctx,path,mode,time,alpha=1,motion){
 const color=palette[mode],width=mode==='walk'?2:3
 ctx.save();ctx.lineCap='round';ctx.lineJoin='round';ctx.setLineDash([])
 for(const [scale,opacity] of [[3.6,.025],[2.1,.065],[1,.18]]){ctx.globalAlpha=opacity*alpha;ctx.strokeStyle=color;ctx.lineWidth=width*scale;ctx.stroke(path)}
 if(motion&&motion.progress>0){
  const {sample,progress,seed=0}=motion,pulses=mode==='walk'?1:2,rate=mode==='electric'?.034:mode==='bicycle'?.026:.018
  for(let pulse=0;pulse<pulses;pulse++){
   const head=((time*rate+seed*.173+pulse/pulses)%1)*progress,span=Math.min(head,mode==='electric'?.085:.06),tail=head-span
   if(span<.001)continue
   const points=Array.from({length:11},(_,i)=>sample(tail+span*i/10)),start=points[0],end=points.at(-1)
   if(Math.hypot(end.x-start.x,end.y-start.y)<1)continue
   const ribbon=new Path2D();points.forEach((p,i)=>i?ribbon.lineTo(p.x,p.y):ribbon.moveTo(p.x,p.y))
   const gradient=ctx.createLinearGradient(start.x,start.y,end.x,end.y)
   gradient.addColorStop(0,color+'00');gradient.addColorStop(.35,color+'40');gradient.addColorStop(.78,color+'d0');gradient.addColorStop(1,'#fff9df')
   ctx.strokeStyle=gradient;ctx.globalAlpha=.22*alpha;ctx.lineWidth=width*3.3;ctx.stroke(ribbon)
   ctx.globalAlpha=.86*alpha;ctx.lineWidth=width*1.5;ctx.stroke(ribbon)
   const core=ctx.createLinearGradient(start.x,start.y,end.x,end.y);core.addColorStop(0,'#ffffff00');core.addColorStop(.65,'#ffffff25');core.addColorStop(1,'#fffdf0')
   ctx.strokeStyle=core;ctx.lineWidth=mode==='walk'?.9:1.3;ctx.globalAlpha=.95*alpha;ctx.stroke(ribbon)
   const halo=ctx.createRadialGradient(end.x,end.y,0,end.x,end.y,width*2.5);halo.addColorStop(0,'#fffdf0e0');halo.addColorStop(.25,color+'a0');halo.addColorStop(1,color+'00');ctx.fillStyle=halo;ctx.globalAlpha=alpha;ctx.beginPath();ctx.arc(end.x,end.y,width*2.5,0,Math.PI*2);ctx.fill()
  }
 }
 ctx.restore()
}
