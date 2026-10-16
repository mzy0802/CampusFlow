// Normalize accidental double clicks and the conventional closing vertex.
export function cleanPoints(points){
 const result=[]
 for(const p of points){const last=result.at(-1);if(!last||p[0]!==last[0]||p[1]!==last[1])result.push([...p])}
 if(result.length>1&&result[0][0]===result.at(-1)[0]&&result[0][1]===result.at(-1)[1])result.pop()
 return result
}
export function polygonIssue(points){
 const p=cleanPoints(points),n=p.length
 if(n<3)return '至少沿边界点击3个不同的点，再完成区域。'
 if(n>200)return '最多支持200个顶点，请减少顶点。'
 if(new Set(p.map(v=>v.join(','))).size!==n)return '边界重复经过同一点，请撤销多余顶点。'
 const orient=(a,b,c)=>(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
 const on=(a,b,c)=>Math.min(a[0],b[0])<=c[0]&&c[0]<=Math.max(a[0],b[0])&&Math.min(a[1],b[1])<=c[1]&&c[1]<=Math.max(a[1],b[1])
 for(let i=0;i<n;i++)for(let j=i+1;j<n;j++){
  if(j===i+1||(i===0&&j===n-1))continue
  const a=p[i],b=p[(i+1)%n],c=p[j],d=p[(j+1)%n],o=[orient(a,b,c),orient(a,b,d),orient(c,d,a),orient(c,d,b)]
  if(o[0]*o[1]<0&&o[2]*o[3]<0||[[o[0],a,b,c],[o[1],a,b,d],[o[2],c,d,a],[o[3],c,d,b]].some(([v,x,y,z])=>Math.abs(v)<1e-12&&on(x,y,z)))return '边界交叉了。请沿边缘顺序画一圈，撤销错误顶点后再完成。'
 }
 if(Math.abs(p.reduce((sum,a,i)=>sum+a[0]*p[(i+1)%n][1]-p[(i+1)%n][0]*a[1],0))<1e-8)return '这些点没有围成有效面积，请沿区域边缘绘制。'
 return ''
}
