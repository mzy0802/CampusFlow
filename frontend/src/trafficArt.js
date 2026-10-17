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
// Dot-matrix flow: a leader glyph pulls a column of dots along the route,
// making crowd direction and volume readable without continuous trails.
export function drawDotFlow(ctx,sample,progress,mode,alpha=1,members=3,gap=.015){
 const color=palette[mode]
 if(progress<=0||alpha<=0)return
 const dots=Math.min(14,2+Math.round(members*1.2)),head=sample(progress)
 if(!head)return
 ctx.save()
 for(let k=dots;k>=1;k--){
  const at=progress-k*gap
  if(at<=0)continue
  const p=sample(at),f=1-k/(dots+1)
  ctx.globalAlpha=alpha*(.22+.6*f)
  ctx.fillStyle=color
  ctx.beginPath();ctx.arc(p.x,p.y,(mode==='walk'?2.3:3)*(.5+.5*f),0,Math.PI*2);ctx.fill()
 }
 const halo=ctx.createRadialGradient(head.x,head.y,0,head.x,head.y,9)
 halo.addColorStop(0,'#fffdf0e0');halo.addColorStop(.3,color+'b0');halo.addColorStop(1,color+'00')
 ctx.fillStyle=halo;ctx.globalAlpha=alpha;ctx.beginPath();ctx.arc(head.x,head.y,9,0,Math.PI*2);ctx.fill()
 ctx.fillStyle=color;ctx.globalAlpha=alpha*.95
 ctx.beginPath();ctx.arc(head.x,head.y,mode==='walk'?2.8:3.6,0,Math.PI*2);ctx.fill()
 ctx.strokeStyle='#fffefa';ctx.lineWidth=1.2;ctx.stroke()
 ctx.restore()
}
