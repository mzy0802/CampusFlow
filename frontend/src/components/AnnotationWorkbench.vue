<script setup>
import {ref,computed,watch,onMounted,onBeforeUnmount} from 'vue'
import {cleanPoints,polygonIssue} from '../annotationGeometry'
const emit=defineEmits(['close','observation'])
const areas=ref([]),areaId=ref(''),viewName=ref(''),captureGroup=ref(''),savedViews=ref([]),surveySelection=ref([]),surveyJob=ref(null)
const viewsLoading=ref(false),viewsStatus=ref(''),viewsError=ref(''),availableGroups=ref([])
let surveyTimer,stopped=false,viewsRequest=0
const items=ref([]),current=ref(null),polygons=ref([]),revision=ref(0),baseline=ref('[]'),draft=ref([]),label=ref('allowed'),note=ref(''),time=ref(0),video=ref(null),error=ref(''),message=ref(''),busy=ref(false),selected=ref(''),paused=ref(true)
const names={allowed:'可停车区域'}
const reviewedFrames=ref([])
const colors={allowed:'#22c55e'}
function serialized(){return JSON.stringify({polygons:polygons.value,area_id:areaId.value,view_name:viewName.value,capture_group:captureGroup.value})}
const dirty=computed(()=>current.value&&(serialized()!==baseline.value||draft.value.length>0))
const visible=computed(()=>polygons.value.filter(p=>Math.abs(p.time_seconds-time.value)<0.08))
const reviewed=computed(()=>reviewedFrames.value.some(t=>Math.abs(t-time.value)<0.08))
const chosen=computed(()=>polygons.value.find(p=>p.id===selected.value))
async function api(path,options){const r=await fetch('/api/annotations'+path,options);let d;try{d=await r.json()}catch{throw Error('接口未返回有效数据，请确认后端已启动')}if(!r.ok){if(r.status===404&&path.startsWith('/views'))throw Error('当前后端没有视角读取接口，请重启后端后重试');const detail=Array.isArray(d.detail)?d.detail.map(e=>{const i=e.loc?.indexOf('polygons');return (i>=0&&typeof e.loc[i+1]==='number'?`第${e.loc[i+1]+1}个区域：`:'')+e.msg.replace(/^Value error,\s*/,'')}).join('；'):d.detail;throw Error(typeof detail==='string'?detail:'保存失败，请重试')}return d}
watch([areaId,captureGroup,()=>current.value?.id],()=>{viewsRequest++;savedViews.value=[];surveySelection.value=[];viewsStatus.value='';viewsError.value='';availableGroups.value=[]},{flush:'sync'})
async function refresh(){items.value=(await api('/media')).items}
function leave(){return !dirty.value||confirm('有未保存标注，确认丢弃？可先取消并保存或导出。')}
async function open(id){if(!leave())return;error.value='';try{const d=await api('/media/'+id);current.value=d.media;polygons.value=d.polygons;areaId.value=d.area_id||'';viewName.value=d.view_name||'';captureGroup.value=d.capture_group||'';savedViews.value=[];surveySelection.value=[];reviewedFrames.value=d.reviewed_frames||[];revision.value=d.revision;baseline.value=serialized();draft.value=[];selected.value='';time.value=0;paused.value=true}catch(e){error.value=e.message}}
async function upload(event){const files=[...(event.target.files||[])];busy.value=true;error.value='';let last=null;const failures=[];for(let i=0;i<files.length;i++){const f=files[i];message.value=`上传 ${i+1}/${files.length}：${f.name}`;try{if(f.size>100*1024*1024)throw Error('超过100MB');const d=await api('/media?'+new URLSearchParams({filename:f.name}),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f});last=d.id}catch(e){failures.push(f.name+'：'+e.message)}}try{await refresh();if(last&&!dirty.value)await open(last)}catch(e){failures.push(e.message)}error.value=failures.join('；');message.value='上传完成，素材只保存在本地后端，未调用 Qwen';busy.value=false;event.target.value=''}
function point(event){
 if(!current.value||!paused.value||busy.value||viewsLoading.value||event.detail>1)return
 const r=event.currentTarget.getBoundingClientRect(),p=[Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))]
 const gap=q=>Math.hypot((p[0]-q[0])*r.width,(p[1]-q[1])*r.height)
 event.currentTarget.focus();error.value=''
 if(draft.value.length>=3&&gap(draft.value[0])<10){finish();return}
 if(draft.value.length&&gap(draft.value.at(-1))<3)return
 if(draft.value.length>=200){error.value='每个区域最多200个顶点';return}
 draft.value.push(p)
}
function finish(){if(!draft.value.length)return;const p=cleanPoints(draft.value),issue=polygonIssue(p);if(issue){error.value=issue;return}polygons.value.push({id:crypto.randomUUID(),label:label.value,note:note.value,time_seconds:current.value.kind==='image'?0:Math.min(current.value.duration_seconds,Number(time.value.toFixed(4))),points:p});draft.value=[];note.value='';error.value='';message.value='区域已完成，接着点击“保存标注”即可保存'}
function points(p){return p.map(([x,y])=>`${x*1000},${y*1000}`).join(' ')}
async function persist(markFrame=false){
 const id=current.value.id
 const before=JSON.stringify(polygons.value),normalized=polygons.value.map(p=>({...p,points:cleanPoints(p.points)}))
 const frames=markFrame?[...reviewedFrames.value,Math.min(current.value.duration_seconds,Number(time.value.toFixed(4)))]:reviewedFrames.value
 const d=await api('/media/'+id,{method:'PUT',headers:{'Content-Type':'application/json'},signal:AbortSignal.timeout(15000),body:JSON.stringify({revision:revision.value,area_id:areaId.value.trim()||null,view_name:viewName.value,capture_group:captureGroup.value.trim(),polygons:normalized,reviewed_frames:frames})})
 if(stopped||current.value?.id!==id)return false
 if((d.area_id||'')!==areaId.value.trim()||(d.capture_group||'')!==captureGroup.value.trim())throw Error('后端未保存停车区或批次信息，请重启更新后的后端')
 revision.value=d.revision;reviewedFrames.value=d.reviewed_frames
 if(JSON.stringify(polygons.value)===before)polygons.value=d.polygons
 baseline.value=JSON.stringify({polygons:d.polygons,area_id:d.area_id||'',view_name:d.view_name||'',capture_group:d.capture_group||''})
 message.value='已保存到数据库 · 版本 '+d.revision
 return true
}
async function save(){video.value?.pause();if(draft.value.length){error.value='请先完成区域或清空正在绘制的顶点';return}if(!visible.value.length&&!confirm('本帧没有可停车区域，确认整帧不可停车？'))return;busy.value=true;error.value='';areaId.value=areaId.value.trim();captureGroup.value=captureGroup.value.trim();viewName.value=viewName.value.trim();try{await persist(true);await refresh()}catch(e){error.value=e.message}finally{busy.value=false}}
async function loadViews(){
 if(viewsLoading.value||busy.value)return
 error.value=''
 viewsError.value='';viewsStatus.value='';savedViews.value=[];surveySelection.value=[];availableGroups.value=[]
 if(!areaId.value.trim()||!captureGroup.value.trim()){viewsError.value='请选择本画面归属的停车区，并填写采集批次后再读取。';return}
 if(draft.value.length){viewsError.value='先点击“完成区域”或清空未完成顶点，再读取视角。';return}
 areaId.value=areaId.value.trim();captureGroup.value=captureGroup.value.trim();viewName.value=viewName.value.trim()
 viewsLoading.value=true;const token=++viewsRequest
 try{
  if(dirty.value){viewsStatus.value='正在保存当前素材的关联信息…';if(!await persist(false))return}
  if(token!==viewsRequest||stopped)return
  viewsStatus.value='正在读取同区同批次视角…'
  const d=await api('/views?'+new URLSearchParams({area_id:areaId.value,capture_group:captureGroup.value}),{signal:AbortSignal.timeout(15000)})
  if(token!==viewsRequest||stopped)return
  if(!Array.isArray(d.items))throw Error('后端返回的视角列表格式不正确，请重启后端')
  savedViews.value=d.items;availableGroups.value=(d.available_groups||[]).filter(g=>g!==captureGroup.value)
  if(d.items.length){viewsStatus.value=`已读取 ${d.items.length} 个视角（${new Set(d.items.map(v=>v.media_id)).size} 份素材），请在下方勾选后联合识别。`}
  else if(d.matched_media_count>0){viewsStatus.value='该批次的素材还没有保存过标注帧。请先画可停范围并点击“确认本帧并保存”，然后再次读取。'}
  else if(d.area_media_count>0){viewsStatus.value='该停车区没有属于当前批次的已保存视角。请给其他角度填写相同批次并保存，或选择下方已有批次。'}
  else{viewsStatus.value='尚未找到同区同批次已保存视角。请先关联素材、画可停范围并保存。'}
 }catch(e){if(token===viewsRequest&&!stopped){viewsStatus.value='';viewsError.value=e.name==='TimeoutError'?'读取超时，请确认后端运行后重试。':'保存或读取失败：'+e.message}}
 finally{viewsLoading.value=false}
}
async function pollSurvey(){try{const r=await fetch('/api/vision/jobs/'+surveyJob.value.id);const d=await r.json();if(!r.ok)throw Error(d.detail);if(stopped)return;surveyJob.value=d;if(d.status==='completed'){emit('observation');return}if(d.status==='failed')return}catch(e){if(!stopped)error.value=e.message}if(!stopped)surveyTimer=setTimeout(pollSurvey,1500)}
async function analyzeViews(){if(dirty.value){error.value='请先保存当前素材的区域与关联信息';return}error.value='';try{const r=await fetch('/api/vision/surveys',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({area_id:areaId.value,capture_group:captureGroup.value,views:surveySelection.value.map(v=>JSON.parse(v))})});const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail));surveyJob.value=d;pollSurvey()}catch(e){error.value=e.message}}
function seek(p){if(draft.value.length){error.value='请先完成或清空正在绘制的区域';return}selected.value=p.id;if(video.value){video.value.pause();video.value.currentTime=p.time_seconds}time.value=p.time_seconds}
function updateTime(){const next=video.value.currentTime;if(draft.value.length&&Math.abs(next-time.value)>0.08){draft.value=[];message.value='视频帧已变化，未完成的顶点已清空；已完成标注仍保留'}time.value=next}
function exportJson(){const data={schema_version:2,area_id:areaId.value,view_name:viewName.value,capture_group:captureGroup.value,media:current.value,revision:revision.value,coordinate_system:'normalized_image_xy',scope:'single_frame',outside_policy:'forbidden_in_reviewed_frame',unreviewed_policy:'unknown',reviewed_frames:reviewedFrames.value,source:'manual_annotation',polygons:polygons.value};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='annotations-'+current.value.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function close(){if(leave())emit('close')}
function beforeUnload(e){if(dirty.value){e.preventDefault();e.returnValue=''}}
onMounted(async()=>{window.addEventListener('beforeunload',beforeUnload);try{await refresh();const r=await fetch('/api/parking/areas');if(!r.ok)throw Error('停车区域加载失败');areas.value=(await r.json()).features.map(f=>f.properties)}catch(e){error.value=e.message}})
onBeforeUnmount(()=>{stopped=true;viewsRequest++;clearTimeout(surveyTimer);window.removeEventListener('beforeunload',beforeUnload)})
</script>
<template>
 <Teleport to="body"><section class="annotation-workbench" aria-label="可停车范围标注">
  <header><strong>照片 / 视频标注工作台</strong><span>{{dirty?'有未保存修改':'已保存'}} · {{current?.filename||'请选择素材'}}</span><button @click="close">返回</button></header>
  <div class="layout"><aside>
   <label class="upload">批量添加照片 / 视频<input type="file" multiple accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.avi" :disabled="busy||viewsLoading" @change="upload"></label>
   <p>每个文件最多100MB，视频最长30分钟。保存原始文件，不调用云端识别。</p>
   <label>素材库<select :value="current?.id||''" :disabled="busy||viewsLoading" @change="open($event.target.value)"><option disabled value="">选择素材（{{items.length}}）</option><option v-for="m in items" :key="m.id" :value="m.id">{{m.filename}} · {{m.kind==='video'?'视频':'照片'}}</option></select></label>
   <p v-if="message" role="status">{{message}}</p><p v-if="error" role="alert" class="error">{{error}}</p>
   <template v-if="current">
    <h3>关联地图停车区</h3><label>本画面归属<select v-model="areaId" :disabled="busy||viewsLoading"><option value="">暂不关联</option><option v-for="a in areas" :key="a.id" :value="a.id">{{a.name}} · 容量 {{a.capacity}}</option></select></label>
    <label>视角名称<input v-model="viewName" maxlength="100" placeholder="如：东侧俯拍" :disabled="busy||viewsLoading"></label><label>同一时刻采集批次<input v-model="captureGroup" maxlength="100" placeholder="如：10月16日-停车区A-14点" :disabled="busy||viewsLoading"></label>
    <p>本帧所有可停区域关联到所选地图停车区；画面周边违停也归属此区，并已包含在总数中。同一区域同一时段的不同角度填写相同批次，跨时段另建批次。画面应只覆盖此区及其负责的周边。</p>
    <h3>画区域</h3><label>标注类型<select v-model="label"><option v-for="(v,k) in names" :value="k" :key="k">{{v}}</option></select></label>
    <label>备注<input v-model="note" maxlength="500" placeholder="如：西侧白线内"></label>
    <p>沿边缘顺时针或逆时针单击一圈，不要来回穿过区域。至少3点，点“完成区域”、双击最后一点或按Enter均可结束；系统自动闭合，不用重复点击起点。只画可停车范围。</p>
    <div class="actions"><button :disabled="draft.length<3" @click="finish">完成区域（{{draft.length}}点）</button><button :disabled="!draft.length" @click="draft.pop()">撤销顶点</button><button @click="draft=[]">清空草稿</button></div>
    <p v-if="current.kind==='video'">当前 {{time.toFixed(2)}} 秒。先暂停再画区域；标注只对应当前帧，不会自动沿用到移动镜头或其他时刻。</p>
    <button class="primary" :disabled="busy||viewsLoading" @click="save">确认本帧并保存</button><button @click="exportJson">导出 JSON</button>
    <h3>已完成 {{polygons.length}} 个标注</h3>
    <div class="list"><button v-for="p in polygons" :key="p.id" :class="{chosen:selected===p.id}" @click="seek(p)">{{names[p.label]}} · {{p.time_seconds.toFixed(2)}}秒 {{p.note}}</button></div>
    <div v-if="chosen"><label>修改类型<select v-model="chosen.label"><option v-for="(v,k) in names" :key="k" :value="k">{{v}}</option></select></label><label>修改备注<input v-model="chosen.note" maxlength="500"></label><button @click="polygons=polygons.filter(p=>p.id!==selected);selected=''">删除所选标注</button><p>修改边界可删除后重画，保存前可重新加载恢复。</p></div>
    <button :disabled="busy||viewsLoading" @click="open(current.id)">重新加载已保存版本</button>
    <h3>多角度联合识别</h3><p>点击读取会自动保存当前素材的停车区、批次及已完成区域，不会调用Qwen。</p><button :disabled="viewsLoading||busy" :aria-busy="viewsLoading" @click="loadViews">{{viewsLoading?'正在保存并读取…':'读取同区同批次已保存视角'}}</button>
    <p v-if="viewsStatus" class="views-status" role="status">{{viewsStatus}}</p><p v-if="viewsError" class="error" role="alert">{{viewsError}}</p>
    <div v-if="availableGroups.length"><p>该停车区已有批次：</p><button v-for="g in availableGroups" :key="g" :disabled="viewsLoading" @click="captureGroup=g;loadViews()">{{g}}</button></div>
    <label v-for="v in savedViews" :key="v.media_id+':'+v.time_seconds" class="view-check"><input type="checkbox" v-model="surveySelection" :value="JSON.stringify({media_id:v.media_id,time_seconds:v.time_seconds})">{{v.view_name||v.filename}} · {{v.time_seconds}} 秒</label>
    <p>选择1～6个视角，一次发送原始图片或原尺寸视频帧到Qwen联合去重估算，最多24MB；会产生API费用。不会把多张图片数量简单相加。</p>
    <button class="primary" :disabled="viewsLoading||!surveySelection.length||surveySelection.length>6||['queued','processing'].includes(surveyJob?.status)" @click="analyzeViews">联合识别所选视角</button>
    <p v-if="surveyJob">任务：{{surveyJob.status==='completed'?'已完成':surveyJob.status==='failed'?'失败': '识别中'}} {{surveyJob.error||''}}</p>
    <div v-if="surveyJob?.result"><strong>总数 {{surveyJob.result.two_wheeler.latest.count}} 辆 · {{surveyJob.result.two_wheeler.latest.percent}}%</strong><p>自行车 {{surveyJob.result.bicycle.latest.count}} · 电动两轮车 {{surveyJob.result.motorcycle.latest.count}} · 类型不明 {{surveyJob.result.uncertain_type.latest.count}}</p><p>区内 {{surveyJob.result.legal_count}} · 违停 {{surveyJob.result.illegal_count}} · 位置不明 {{surveyJob.result.unknown_location_count}}（均已计入总数）</p></div>
   </template>
  </aside><main><div v-if="current" class="drawing-toolbar"><strong>{{draft.length?'正在绘制 · '+draft.length+'点':'沿边界逐点单击'}}</strong><button :disabled="draft.length<3||busy||viewsLoading" @click="finish">完成区域</button><button :disabled="!draft.length" @click="draft.pop();error=''">撤销一点</button><button class="primary" :disabled="busy||viewsLoading" @click="save">保存标注</button><span>Enter完成 · Esc取消 · 系统自动闭合</span><p v-if="error" class="error" role="alert">{{error}}</p></div><div v-if="current" class="stage" :style="{aspectRatio:current.width+'/'+current.height}" :key="current.id">
   <img v-if="current.kind==='image'" :src="current.url" alt="待标注原尺寸图片">
   <video v-else ref="video" :src="current.url" preload="metadata" @timeupdate="updateTime" @seeked="updateTime" @play="paused=false" @pause="paused=true" @error="error='浏览器不能播放此编码，请转换为 H.264 MP4；原文件已保留'" />
   <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" tabindex="0" @click="point" @dblclick.stop.prevent="finish" @keydown.enter.prevent="finish" @keydown.esc.prevent="draft=[];error=''" @keydown.backspace.prevent="draft.pop()" aria-label="点击画面添加区域顶点">
    <defs><mask id="outside-parking-mask"><rect width="1000" height="1000" fill="white"/><polygon v-for="p in visible" :key="p.id" :points="points(p.points)" fill="black"/></mask></defs><rect v-if="reviewed||visible.length" width="1000" height="1000" fill="#ef4444" fill-opacity=".16" mask="url(#outside-parking-mask)"/>
    <polygon v-for="p in visible" :key="p.id" :points="points(p.points)" :fill="colors[p.label]" fill-opacity=".22" :stroke="colors[p.label]" :stroke-width="p.id===selected?5:2" vector-effect="non-scaling-stroke"><title>{{names[p.label]}} {{p.note}}</title></polygon>
    <polyline :points="points(draft)" fill="none" :stroke="colors[label]" stroke-width="3" vector-effect="non-scaling-stroke"/>
    <circle v-for="(p,i) in draft" :key="i" :cx="p[0]*1000" :cy="p[1]*1000" r="4" fill="white" stroke="#2563eb"/>
   </svg>
  </div><div v-else class="empty">上传今天采集的照片或视频，开始标注可停车范围</div>
  <div v-if="current?.kind==='video'" class="video-controls"><button @click="paused?video.play():video.pause()">{{paused?'播放':'暂停'}}</button><input aria-label="视频定位秒数" type="range" min="0" :max="current.duration_seconds" step="0.01" :value="time" @input="video.pause();video.currentTime=Number($event.target.value)"><span>{{time.toFixed(2)}} / {{current.duration_seconds.toFixed(2)}} 秒</span></div>
  <p class="legend">绿色内可停车，其余画面不可停车。绑定地图停车区并提交联合识别后，周边违停计入该区容载率；未保存帧不参与识别。</p></main></div>
 </section></Teleport>
</template>
<style scoped>
.annotation-workbench{position:fixed;inset:0;z-index:2200;background:#f1f5f9;color:#172b4d;font:14px/1.5 var(--app-font);display:flex;flex-direction:column}.annotation-workbench header{display:flex;align-items:center;gap:20px;padding:14px 20px;background:white;border-bottom:1px solid #ddd}.annotation-workbench header span{flex:1;overflow:hidden;text-overflow:ellipsis}.layout{display:flex;flex:1;min-height:0}.layout aside{width:320px;flex-shrink:0;overflow:auto;padding:18px;background:white}.layout main{flex:1;min-width:0;padding:20px;overflow:auto}.stage{position:relative;width:100%;background:#111;user-select:none;-webkit-user-select:none}.stage img,.stage video{-webkit-user-drag:none}.stage img,.stage video{width:100%;height:100%;display:block}.stage svg{position:absolute;inset:0;width:100%;height:100%;cursor:crosshair}.annotation-workbench label{display:block;margin:12px 0}.annotation-workbench input:not([type=range]),.annotation-workbench select{box-sizing:border-box;width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:6px}.annotation-workbench button{padding:8px 10px;border:1px solid #cbd5e1;border-radius:6px;background:white;color:inherit;cursor:pointer;margin:3px}.annotation-workbench button:disabled{opacity:.45;cursor:default}.annotation-workbench .primary{background:#2563eb;color:white}.annotation-workbench p{font-size:12px;color:#64748b}.annotation-workbench .error{color:#b91c1c;overflow-wrap:anywhere}.actions{display:flex;flex-wrap:wrap}.list{max-height:220px;overflow:auto}.list button{display:block;text-align:left;width:95%}.list .chosen{border-color:#2563eb;background:#eff6ff}.video-controls{display:flex;align-items:center;gap:10px}.video-controls input{flex:1}.empty{padding:100px 20px;text-align:center}.legend{text-align:center}@media(max-width:750px){.layout{flex-direction:column-reverse}.layout aside{width:auto;max-height:45%;}.layout main{min-height:30vh;padding:8px}}
</style>
<style scoped>.view-check{display:flex!important;align-items:center;gap:8px}.view-check input{width:auto!important}.annotation-workbench .views-status{padding:10px;background:#eff6ff;border-radius:7px;color:#1d4ed8}.drawing-toolbar{position:sticky;top:-20px;background:white;z-index:5;padding:8px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;border-radius:8px;margin-bottom:12px;box-shadow:0 2px 8px #0001}.drawing-toolbar span{font-size:12px;color:#64748b}.drawing-toolbar .error{flex-basis:100%;margin:0}.stage svg:focus{outline:2px solid #93c5fd;outline-offset:2px}</style>
