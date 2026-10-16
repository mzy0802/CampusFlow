<script setup>
import {ref,computed,onMounted,onBeforeUnmount,watch,nextTick} from 'vue'
import L from 'leaflet'
const props=defineProps({areas:{type:Array,default:()=>[]},parkingGeoJson:Object})
const emit=defineEmits(['close'])
const dataset=ref('campus'), graph=ref({nodes:[],edges:[],revision:0,dataset:'campus'}), saved=ref(''), selected=ref(''), edgeId=ref(''), error=ref(''), message=ref(''), busy=ref(false), tool=ref('select'), mapEl=ref(null)
const origin=ref(''),destination=ref(''),preference=ref('fastest'),result=ref(null),activePlan=ref(null),from=ref(''),to=ref(''),capacityArea=ref(''),capacityValue=ref(100)
let map,layer,routeLayer,tiles,observer,parkingLayer
let roadMetadata=new Map()
const node=computed(()=>graph.value.nodes.find(n=>n.id===selected.value))
const edge=computed(()=>graph.value.edges.find(e=>e.id===edgeId.value))
const dirty=computed(()=>JSON.stringify(graph.value)!==saved.value)
const options=computed(()=>result.value?.recommended?[result.value.recommended,...result.value.alternatives]:[])
async function api(path,method='GET',body){
 const response=await fetch('/api'+path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined})
 const data=await response.json()
 if(!response.ok){const d=data.detail;throw new Error(typeof d==='string'?d:Array.isArray(d)?d.map(x=>x.msg).join('；'):'请求失败')}
 return data
}
function uid(prefix){return prefix+crypto.randomUUID().replaceAll('-','').slice(0,12)}
function invalidate(){result.value=null;activePlan.value=null;routeLayer?.clearLayers()}
function fit(){
 const coords=graph.value.nodes.filter(n=>Number.isFinite(n.latitude)&&Number.isFinite(n.longitude)).map(n=>[n.latitude,n.longitude])
 if(coords.length)map.fitBounds(coords,{padding:[45,45],maxZoom:19})
 else if(parkingLayer?.getBounds().isValid())map.fitBounds(parkingLayer.getBounds(),{padding:[40,40],maxZoom:18})
}
async function load(value=dataset.value){
 if(dirty.value&&saved.value&&!confirm('有未保存修改，切换后将丢弃。需要保留请先取消并导出。'))return
 busy.value=true;error.value=''
 try{const data=await api('/network/'+value);if(value==='campus'){const roads=await api('/navigation/map?include_service=true');roadMetadata=new Map(roads.features.map(f=>[f.properties.id,f.properties]))}dataset.value=value;graph.value=data;saved.value=JSON.stringify(data);selected.value='';edgeId.value='';from.value='';to.value='';origin.value=data.nodes[0]?.id||'';destination.value=data.nodes.find(n=>n.kind==='entrance')?.id||'';invalidate();await nextTick();paint();fit();message.value=value==='example'?'独立虚构示例：不是渭水校区道路。':'道路按负责人要求纳入规划；停车入口需关联。'}catch(e){error.value=e.message}finally{busy.value=false}
}
async function save(){busy.value=true;error.value='';try{const data=await api('/network/'+dataset.value,'PUT',graph.value);graph.value=data;saved.value=JSON.stringify(data);message.value='已保存到数据库 · 版本 '+data.revision;invalidate()}catch(e){error.value=e.message}finally{busy.value=false}}
function addNode(latlng){
 const id=uid('n');graph.value.nodes.push({id,name:'新节点 '+(graph.value.nodes.length+1),longitude:Number(latlng.lng.toFixed(7)),latitude:Number(latlng.lat.toFixed(7)),kind:'junction',parking_id:null,capacity:100,available:50});selected.value=id;edgeId.value=''
}
function deleteNode(){if(!node.value)return;const id=node.value.id;graph.value.nodes=graph.value.nodes.filter(n=>n.id!==id);graph.value.edges=graph.value.edges.filter(e=>e.source!==id&&e.target!==id);if(origin.value===id)origin.value='';if(destination.value===id)destination.value='';if(from.value===id)from.value='';if(to.value===id)to.value='';selected.value=''}
function addEdge(){if(!from.value||!to.value||from.value===to.value){error.value='请选择两个不同节点';return}const id=uid('e');graph.value.edges.push({id,source:from.value,target:to.value,modes:['walk','bike'],bidirectional:true,congestion:1,verified:true});edgeId.value=id;selected.value='';error.value=''}
function paint(){
 if(!map)return
 layer.clearLayers()
 if(parkingLayer){if(dataset.value==='campus')parkingLayer.addTo(map);else parkingLayer.remove()}
 if(dataset.value==='campus'){if(!map.hasLayer(tiles))tiles.addTo(map)}else if(map.hasLayer(tiles))map.removeLayer(tiles)
 const validNodes=graph.value.nodes.filter(n=>Number.isFinite(n.latitude)&&Number.isFinite(n.longitude)&&Math.abs(n.latitude)<=85&&Math.abs(n.longitude)<=180)
 const nodes=new Map(validNodes.map(n=>[n.id,n]))
 const named=new Set()
 for(const e of graph.value.edges){const a=nodes.get(e.source),b=nodes.get(e.target);if(!a||!b)continue
 const meta=roadMetadata.get(e.id);if(dataset.value==='campus'&&meta?.highway==='service')continue
 const roadColor=meta?.highway==='cycleway'?'#22a447':['footway','pedestrian','steps'].includes(meta?.highway)?'#66CCFF':'#f6c344'
 const line=L.polyline([[a.latitude,a.longitude],[b.latitude,b.longitude]],{color:e.id===edgeId.value?'#ef6c00':roadColor,weight:5,dashArray:e.verified?null:'7 7'}).addTo(layer)
 const label=document.createElement('span');label.textContent=`${a.name} → ${b.name} · ${e.bidirectional?'双向':'单向'} · ${e.verified?'已核验':'未核验'}`;if(meta?.name){label.textContent=meta.name;line.bindTooltip(label,{permanent:!named.has(meta.name),direction:'center'});named.add(meta.name)}else line.bindTooltip(label)
 line.on('click',ev=>{L.DomEvent.stopPropagation(ev);edgeId.value=e.id;selected.value='';paint()})}
 for(const n of validNodes){
 const circle=L.circleMarker([n.latitude,n.longitude],{radius:n.id===selected.value?10:7,color:n.kind==='parking'?'#188038':n.kind==='entrance'?'#9333ea':'#2563eb',fillOpacity:1,weight:3}).addTo(layer)
 const label=document.createElement('span');label.textContent=n.name;circle.bindTooltip(label,{permanent:validNodes.length<=80||n.id===selected.value,direction:'top',offset:[0,-7]})
 circle.on('click',ev=>{L.DomEvent.stopPropagation(ev);if(tool.value==='origin'){origin.value=n.id;tool.value='select'}else if(tool.value==='destination'){destination.value=n.id;tool.value='select'}else{selected.value=n.id;edgeId.value=''}paint()})}
}
function showPlan(plan){activePlan.value=plan;routeLayer.clearLayers();for(const s of plan.segments)L.geoJSON(s.geojson,{style:{color:s.mode==='bike'?'#2563eb':'#16a34a',weight:7,dashArray:s.mode==='walk'?'7 9':null},pointToLayer:(f,ll)=>L.circleMarker(ll,{radius:8})}).addTo(routeLayer);if(routeLayer.getLayers().length)map.fitBounds(routeLayer.getBounds(),{padding:[40,40],maxZoom:19})}
async function calculate(){busy.value=true;error.value='';invalidate();try{result.value=await api('/trips/plan','POST',{dataset:dataset.value,origin_id:origin.value,destination_id:destination.value,preference:preference.value});if(result.value.recommended)showPlan(result.value.recommended)}catch(e){error.value=e.message}finally{busy.value=false}}
function exportGraph(){const url=URL.createObjectURL(new Blob([JSON.stringify(graph.value,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`campusflow-${dataset.value}-network.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
async function importGraph(event){
 const file=event.target.files?.[0];if(!file)return
 try{if(file.size>2*1024*1024)throw new Error('路网文件最大2MB');const data=JSON.parse(await file.text());if(data.dataset!==dataset.value)throw new Error('文件场景不匹配，请先切换到对应场景');if(!Array.isArray(data.nodes)||!Array.isArray(data.edges)||data.nodes.length>2000||data.edges.length>5000)throw new Error('路网格式或规模不合法');if(data.nodes.some(n=>!Number.isFinite(n.latitude)||!Number.isFinite(n.longitude)||Math.abs(n.latitude)>85||Math.abs(n.longitude)>180))throw new Error('节点坐标不合法');if(!confirm('导入将替换当前草稿；数据库在点击保存前不变。是否继续？'))return;graph.value={...data,revision:graph.value.revision};selected.value='';edgeId.value='';message.value='已导入草稿，请保存以完成后端校验';await nextTick();fit()}catch(e){error.value=e.message}finally{event.target.value=''}
}
async function updateCapacity(){busy.value=true;error.value='';try{await api('/parking/'+encodeURIComponent(capacityArea.value)+'/capacity','PUT',{capacity:Number(capacityValue.value)});message.value='容量已保存，停车面板下一次刷新生效';invalidate()}catch(e){error.value=e.message}finally{busy.value=false}}
function close(){if(!dirty.value||confirm('有未保存路网，确认关闭？'))emit('close')}
watch(graph,()=>{invalidate();paint()},{deep:true})
watch([origin,destination,preference],invalidate)
onMounted(async()=>{map=L.map(mapEl.value,{center:[0,0],zoom:17});tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'});parkingLayer=L.geoJSON(props.parkingGeoJson||{type:'FeatureCollection',features:[]},{style:{color:'#188038',weight:2,fillOpacity:.12},onEachFeature(f,l){const label=document.createElement('span');label.textContent=f.properties.name+' · 用户导入边界';l.bindTooltip(label)}});layer=L.layerGroup().addTo(map);routeLayer=L.featureGroup().addTo(map);map.on('click',e=>{if(tool.value==='add')addNode(e.latlng)});observer=new ResizeObserver(()=>map.invalidateSize());observer.observe(mapEl.value);await load()})
onBeforeUnmount(()=>{observer?.disconnect();map?.remove()})
</script>
<template>
 <section class="workbench" aria-label="路网编辑与停车推荐">
  <header><div><strong>CampusFlow · 路线工作台</strong><small>{{dataset==='example'?'虚构示例场景 · 无真实地理含义':'校园路网 · 公开数据与人工核验'}} · {{dirty?'有未保存修改':'已保存'}} · v{{graph.revision}}</small></div><button @click="close">返回停车地图</button></header>
  <div class="workbody"><aside>
   <div class="scene"><button :class="{chosen:dataset==='campus'}" :disabled="busy" @click="load('campus')">校园数据</button><button :class="{chosen:dataset==='example'}" :disabled="busy" @click="load('example')">独立示例</button></div>
   <p v-if="error" role="alert" class="err">{{error}}</p><p v-if="message" role="status" class="hint">{{message}}</p>
   <p v-if="dataset==='campus'" class="hint">道路来源：<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap contributors · ODbL</a>。公开数据可能缺失；已按负责人要求纳入规划，非独立实地核验。节点过多时悬停显示名称。</p>
   <h2>路线与停车推荐</h2>
   <p class="hint">先选择已录入节点作为起终点。蓝色为骑行，绿色虚线为步行；预计时间和空位均为演示数据。</p>
   <label>起点<select v-model="origin"><option value="">请选择</option><option v-for="n in graph.nodes" :key="n.id" :value="n.id">{{n.name}}</option></select></label>
   <label>目的地<select v-model="destination"><option value="">请选择</option><option v-for="n in graph.nodes" :key="n.id" :value="n.id">{{n.name}}</option></select></label>
   <div class="row"><button @click="tool='origin'">地图选起点</button><button @click="tool='destination'">地图选终点</button></div>
   <label>出行偏好<select v-model="preference"><option value="fastest">总耗时短</option><option value="less_walking">少走路优先</option></select></label>
   <button class="primary" :disabled="busy||dirty||!origin||!destination" @click="calculate">{{busy?'处理中…':'计算停车方案'}}</button><small v-if="dirty">请先保存路网，再计算路线。</small>
   <div v-if="result">
    <p v-if="!result.recommended" class="err">没有可行方案。检查空位、道路核验状态、通行方式和连接方向。</p>
    <button v-for="(p,i) in options" :key="p.parking_node_id" class="plan" :class="{chosen:activePlan===p}" @click="showPlan(p)"><b>{{i===0?'推荐':'备选'}} · {{p.name}}</b><span>预计 {{p.total_minutes}} 分钟 · 步行 {{p.walk_distance_m}} 米</span><span>模拟空位 {{p.available}} / {{p.capacity}}</span><small>{{p.reason}}</small></button>
    <p class="hint">速度假设：骑行12 km/h、步行4.5 km/h，停车1分钟。道路时间乘数非实时拥堵。</p><p class="hint">公交尚未配置。</p>
    <details v-if="result.excluded.length"><summary>未入选停车点</summary><p v-for="x in result.excluded" :key="x.id">{{graph.nodes.find(n=>n.id===x.id)?.name}}：{{x.reason}}</p></details>
   </div>
   <hr><details open><summary>路网编辑</summary><p class="hint">点击“新增节点”，再点击地图。弯曲道路应分段设置节点；交叉道路必须共用节点才能连通。</p>
    <div class="row"><button :class="{chosen:tool==='add'}" @click="tool=tool==='add'?'select':'add'">新增节点</button><button @click="tool='select';fit()">查看全部</button></div><p class="hint">当前操作：{{{select:'选择节点或道路',add:'点击地图新增节点',origin:'点击已有节点选起点',destination:'点击已有节点选终点'}[tool]}}</p>
    <label>选择节点<select v-model="selected" @change="edgeId='';paint()"><option value="">请选择</option><option v-for="n in graph.nodes" :key="n.id" :value="n.id">{{n.name}}</option></select></label>
    <div v-if="node" class="editor"><label>名称<input v-model="node.name" maxlength="100"></label><label>类型<select v-model="node.kind"><option value="junction">道路节点</option><option value="entrance">楼宇入口</option><option value="parking">停车入口</option></select></label><label>经度<input v-model.number="node.longitude" type="number" step="0.000001" min="-180" max="180"></label><label>纬度<input v-model.number="node.latitude" type="number" step="0.000001" min="-85" max="85"></label>
     <label v-if="node.kind==='parking'&&dataset==='campus'">关联停车区<select v-model="node.parking_id"><option :value="null">请选择</option><option v-for="a in areas" :key="a.id" :value="a.id">{{a.name}}</option></select></label>
     <template v-if="node.kind==='parking'&&dataset==='example'"><label>示例容量<input v-model.number="node.capacity" type="number" min="1"></label><label>示例空位<input v-model.number="node.available" type="number" min="0"></label></template>
     <button class="danger" @click="deleteNode">删除节点及相连道路</button>
    </div>
    <h3>连接道路</h3><label>从<select v-model="from"><option value="">请选择</option><option v-for="n in graph.nodes" :key="n.id" :value="n.id">{{n.name}}</option></select></label><label>到<select v-model="to"><option value="">请选择</option><option v-for="n in graph.nodes" :key="n.id" :value="n.id">{{n.name}}</option></select></label><button @click="addEdge">添加道路</button>
    <label>选择道路<select v-model="edgeId" @change="selected='';paint()"><option value="">请选择</option><option v-for="e in graph.edges" :key="e.id" :value="e.id">{{graph.nodes.find(n=>n.id===e.source)?.name}} → {{graph.nodes.find(n=>n.id===e.target)?.name}}</option></select></label>
    <div v-if="edge" class="editor"><label class="check"><input v-model="edge.bidirectional" type="checkbox">双向道路</label><label class="check"><input v-model="edge.modes" type="checkbox" value="bike">允许骑行</label><label class="check"><input v-model="edge.modes" type="checkbox" value="walk">允许步行</label><label>通行时间乘数（1～10）<input v-model.number="edge.congestion" type="number" min="1" max="10" step="0.1"></label><label class="check"><input v-model="edge.verified" type="checkbox">已核验可通行{{dataset==='example'?'（示例）':''}}</label><button class="danger" @click="graph.edges=graph.edges.filter(e=>e.id!==edgeId);edgeId=''">删除道路</button></div>
    <p>{{graph.nodes.length}} 个节点 · {{graph.edges.length}} 条道路</p><button class="primary" :disabled="busy||!dirty" @click="save">保存路网到数据库</button>
    <div class="row"><button @click="exportGraph">导出 JSON</button><label class="import">导入 JSON<input type="file" accept=".json" @change="importGraph"></label></div><button :disabled="busy" @click="load()">重新加载已保存版本</button>
   </details>
   <details v-if="dataset==='campus'"><summary>停车容量配置</summary><label>停车区<select v-model="capacityArea"><option value="">请选择</option><option v-for="a in areas" :key="a.id" :value="a.id">{{a.name}}</option></select></label><label>容量<input v-model.number="capacityValue" type="number" min="1" max="100000"></label><button :disabled="!capacityArea||busy" @click="updateCapacity">保存容量</button><p class="hint">仅修改参考容量，空位仍为模拟数据。</p></details>
  </aside><div class="mapwrap"><div ref="mapEl" class="editor-map"></div><div class="badge">{{dataset==='example'?'示例示意图 · 非真实校园路网':'校园道路录入 · 虚线为未核验道路'}}</div></div></div>
 </section>
</template>
<style scoped>
.workbench{position:fixed;inset:0;z-index:2000;background:#f8fafc;color:#172b4d;font:14px/1.5 system-ui,sans-serif;display:flex;flex-direction:column}.workbench header{padding:14px 22px;background:white;border-bottom:1px solid #dbe3ed;display:flex;justify-content:space-between;align-items:center;gap:12px}.workbench header strong{font-size:19px}.workbench small{display:block;color:#64748b}.workbody{display:flex;flex:1;min-height:0}.workbody aside{width:365px;flex-shrink:0;overflow-y:auto;padding:20px;background:white;border-right:1px solid #dbe3ed}.mapwrap{position:relative;flex:1;min-width:0}.editor-map{height:100%;background:#eaf0f6}.badge{position:absolute;top:12px;left:55px;z-index:500;background:#fff7d6;padding:8px 12px;border-radius:7px;pointer-events:none;font-weight:600}.workbench button,.import{border:1px solid #cbd5e1;border-radius:8px;padding:9px 12px;background:white;cursor:pointer;color:inherit;font:inherit}.workbench button:disabled{opacity:.45;cursor:not-allowed}.workbench button.chosen{border-color:#2563eb;background:#eff6ff}.workbench label{display:block;margin:10px 0}.workbench input:not([type=checkbox]),.workbench select{width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:6px;margin-top:4px;background:white;color:#172b4d;box-sizing:border-box}.workbench .check{display:flex;align-items:center;gap:8px}.workbench .row,.scene{display:flex;gap:8px;margin:12px 0;flex-wrap:wrap}.workbench .primary{background:#2563eb;color:white;width:100%;border-color:#2563eb}.workbench .danger{color:#b91c1c}.workbench .hint{font-size:12px;color:#64748b}.workbench .err{background:#fff1f2;color:#9f1239;padding:10px;border-radius:6px}.workbench .plan{display:flex;flex-direction:column;width:100%;text-align:left;margin:10px 0;gap:5px}.workbench details{margin:18px 0}.workbench summary{cursor:pointer;font-size:16px;font-weight:650}.workbench h2{font-size:19px}.workbench h3{font-size:15px}.workbench hr{border:0;border-top:1px solid #e2e8f0;margin:24px 0}.editor{padding:10px;background:#f8fafc;border-radius:9px}.workbench .import{margin:0}.import input{display:none!important}@media(max-width:700px){.workbody{flex-direction:column-reverse}.workbody aside{width:100%;max-height:55%;box-sizing:border-box}.mapwrap{min-height:35vh}.workbench header{padding:9px}.workbench header strong{font-size:15px}.badge{font-size:11px;left:50px;right:8px}.workbench header button{font-size:12px}}
</style>
