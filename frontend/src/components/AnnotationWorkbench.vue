<script setup>
import {ref,computed,onMounted,onBeforeUnmount} from 'vue'
const emit=defineEmits(['close'])
const items=ref([]),current=ref(null),polygons=ref([]),revision=ref(0),baseline=ref('[]'),draft=ref([]),label=ref('allowed'),note=ref(''),time=ref(0),video=ref(null),error=ref(''),message=ref(''),busy=ref(false),selected=ref(''),paused=ref(true)
const names={allowed:'可停车区域'}
const reviewedFrames=ref([])
const colors={allowed:'#22c55e'}
const dirty=computed(()=>JSON.stringify(polygons.value)!==baseline.value||draft.value.length>0)
const visible=computed(()=>polygons.value.filter(p=>Math.abs(p.time_seconds-time.value)<0.08))
const reviewed=computed(()=>reviewedFrames.value.some(t=>Math.abs(t-time.value)<0.08))
const chosen=computed(()=>polygons.value.find(p=>p.id===selected.value))
async function api(path,options){const r=await fetch('/api/annotations'+path,options);const d=await r.json();if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail));return d}
async function refresh(){items.value=(await api('/media')).items}
function leave(){return !dirty.value||confirm('有未保存标注，确认丢弃？可先取消并保存或导出。')}
async function open(id){if(!leave())return;error.value='';try{const d=await api('/media/'+id);current.value=d.media;polygons.value=d.polygons;reviewedFrames.value=d.reviewed_frames||[];revision.value=d.revision;baseline.value=JSON.stringify(d.polygons);draft.value=[];selected.value='';time.value=0;paused.value=true}catch(e){error.value=e.message}}
async function upload(event){const files=[...(event.target.files||[])];busy.value=true;error.value='';let last=null;const failures=[];for(let i=0;i<files.length;i++){const f=files[i];message.value=`上传 ${i+1}/${files.length}：${f.name}`;try{if(f.size>100*1024*1024)throw Error('超过100MB');const d=await api('/media?'+new URLSearchParams({filename:f.name}),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f});last=d.id}catch(e){failures.push(f.name+'：'+e.message)}}try{await refresh();if(last&&!dirty.value)await open(last)}catch(e){failures.push(e.message)}error.value=failures.join('；');message.value='上传完成，素材只保存在本地后端，未调用 Qwen';busy.value=false;event.target.value=''}
function point(event){if(!current.value||!paused.value)return;const r=event.currentTarget.getBoundingClientRect();draft.value.push([Math.max(0,Math.min(1,(event.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(event.clientY-r.top)/r.height))])}
function finish(){if(draft.value.length<3)return;polygons.value.push({id:crypto.randomUUID(),label:label.value,note:note.value,time_seconds:current.value.kind==='image'?0:Math.min(current.value.duration_seconds,Number(time.value.toFixed(4))),points:[...draft.value]});draft.value=[];note.value=''}
function points(p){return p.map(([x,y])=>`${x*1000},${y*1000}`).join(' ')}
async function save(){video.value?.pause();if(draft.value.length){error.value='请先完成区域或清空正在绘制的顶点';return}if(!visible.value.length&&!confirm('本帧没有可停车区域，确认整帧不可停车？'))return;busy.value=true;error.value='';try{const d=await api('/media/'+current.value.id,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:revision.value,polygons:polygons.value,reviewed_frames:[...reviewedFrames.value,Math.min(current.value.duration_seconds,Number(time.value.toFixed(4)))]})});revision.value=d.revision;reviewedFrames.value=d.reviewed_frames;baseline.value=JSON.stringify(polygons.value);message.value='已保存到数据库 · 版本 '+d.revision;await refresh()}catch(e){error.value=e.message}finally{busy.value=false}}
function seek(p){if(draft.value.length){error.value='请先完成或清空正在绘制的区域';return}selected.value=p.id;if(video.value){video.value.pause();video.value.currentTime=p.time_seconds}time.value=p.time_seconds}
function updateTime(){const next=video.value.currentTime;if(draft.value.length&&Math.abs(next-time.value)>0.08){draft.value=[];message.value='视频帧已变化，未完成的顶点已清空；已完成标注仍保留'}time.value=next}
function exportJson(){const data={schema_version:1,media:current.value,revision:revision.value,coordinate_system:'normalized_image_xy',scope:'single_frame',outside_policy:'forbidden_in_reviewed_frame',unreviewed_policy:'unknown',reviewed_frames:reviewedFrames.value,source:'manual_annotation',polygons:polygons.value};const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='annotations-'+current.value.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function close(){if(leave())emit('close')}
function beforeUnload(e){if(dirty.value){e.preventDefault();e.returnValue=''}}
onMounted(async()=>{window.addEventListener('beforeunload',beforeUnload);try{await refresh()}catch(e){error.value=e.message}})
onBeforeUnmount(()=>window.removeEventListener('beforeunload',beforeUnload))
</script>
<template>
 <Teleport to="body"><section class="annotation-workbench" aria-label="可停车范围标注">
  <header><strong>照片 / 视频标注工作台</strong><span>{{dirty?'有未保存修改':'已保存'}} · {{current?.filename||'请选择素材'}}</span><button @click="close">返回</button></header>
  <div class="layout"><aside>
   <label class="upload">批量添加照片 / 视频<input type="file" multiple accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.webm,.avi" :disabled="busy" @change="upload"></label>
   <p>每个文件最多100MB，视频最长30分钟。保存原始文件，不调用云端识别。</p>
   <label>素材库<select :value="current?.id||''" :disabled="busy" @change="open($event.target.value)"><option disabled value="">选择素材（{{items.length}}）</option><option v-for="m in items" :key="m.id" :value="m.id">{{m.filename}} · {{m.kind==='video'?'视频':'照片'}}</option></select></label>
   <p v-if="message" role="status">{{message}}</p><p v-if="error" role="alert" class="error">{{error}}</p>
   <template v-if="current">
    <h3>画区域</h3><label>标注类型<select v-model="label"><option v-for="(v,k) in names" :value="k" :key="k">{{v}}</option></select></label>
    <label>备注<input v-model="note" maxlength="500" placeholder="如：修远楼西侧白线内"></label>
    <p>在画面上依次点击边界顶点，再点“完成区域”。只画可停车范围。确认本帧后，所有绿色区域以外均为不可停车；未标注帧保持未知。</p>
    <div class="actions"><button :disabled="draft.length<3" @click="finish">完成区域（{{draft.length}}点）</button><button :disabled="!draft.length" @click="draft.pop()">撤销顶点</button><button @click="draft=[]">清空草稿</button></div>
    <p v-if="current.kind==='video'">当前 {{time.toFixed(2)}} 秒。先暂停再画区域；标注只对应当前帧，不会自动沿用到移动镜头或其他时刻。</p>
    <button class="primary" :disabled="busy" @click="save">确认本帧并保存</button><button @click="exportJson">导出 JSON</button>
    <h3>已完成 {{polygons.length}} 个标注</h3>
    <div class="list"><button v-for="p in polygons" :key="p.id" :class="{chosen:selected===p.id}" @click="seek(p)">{{names[p.label]}} · {{p.time_seconds.toFixed(2)}}秒 {{p.note}}</button></div>
    <div v-if="chosen"><label>修改类型<select v-model="chosen.label"><option v-for="(v,k) in names" :key="k" :value="k">{{v}}</option></select></label><label>修改备注<input v-model="chosen.note" maxlength="500"></label><button @click="polygons=polygons.filter(p=>p.id!==selected);selected=''">删除所选标注</button><p>修改边界可删除后重画，保存前可重新加载恢复。</p></div>
    <button :disabled="busy" @click="open(current.id)">重新加载已保存版本</button>
   </template>
  </aside><main><div v-if="current" class="stage" :style="{aspectRatio:current.width+'/'+current.height}" :key="current.id">
   <img v-if="current.kind==='image'" :src="current.url" alt="待标注原尺寸图片">
   <video v-else ref="video" :src="current.url" preload="metadata" @timeupdate="updateTime" @seeked="updateTime" @play="paused=false" @pause="paused=true" @error="error='浏览器不能播放此编码，请转换为 H.264 MP4；原文件已保留'" />
   <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" @click="point" aria-label="点击画面添加区域顶点">
    <defs><mask id="outside-parking-mask"><rect width="1000" height="1000" fill="white"/><polygon v-for="p in visible" :key="p.id" :points="points(p.points)" fill="black"/></mask></defs><rect v-if="reviewed||visible.length" width="1000" height="1000" fill="#ef4444" fill-opacity=".16" mask="url(#outside-parking-mask)"/>
    <polygon v-for="p in visible" :key="p.id" :points="points(p.points)" :fill="colors[p.label]" fill-opacity=".22" :stroke="colors[p.label]" :stroke-width="p.id===selected?5:2" vector-effect="non-scaling-stroke"><title>{{names[p.label]}} {{p.note}}</title></polygon>
    <polyline :points="points(draft)" fill="none" :stroke="colors[label]" stroke-width="3" vector-effect="non-scaling-stroke"/>
    <circle v-for="(p,i) in draft" :key="i" :cx="p[0]*1000" :cy="p[1]*1000" r="4" fill="white" stroke="#2563eb"/>
   </svg>
  </div><div v-else class="empty">上传今天采集的照片或视频，开始标注可停车范围</div>
  <div v-if="current?.kind==='video'" class="video-controls"><button @click="paused?video.play():video.pause()">{{paused?'播放':'暂停'}}</button><input aria-label="视频定位秒数" type="range" min="0" :max="current.duration_seconds" step="0.01" :value="time" @input="video.pause();video.currentTime=Number($event.target.value)"><span>{{time.toFixed(2)}} / {{current.duration_seconds.toFixed(2)}} 秒</span></div>
  <p class="legend">绿色内可停车，确认帧的其余画面不可停车；没有审核的帧不作判断。画面范围不是地图经纬度区域，也不自动判定某辆车违停。</p></main></div>
 </section></Teleport>
</template>
<style scoped>
.annotation-workbench{position:fixed;inset:0;z-index:2200;background:#f1f5f9;color:#172b4d;font:14px/1.5 system-ui;display:flex;flex-direction:column}.annotation-workbench header{display:flex;align-items:center;gap:20px;padding:14px 20px;background:white;border-bottom:1px solid #ddd}.annotation-workbench header span{flex:1;overflow:hidden;text-overflow:ellipsis}.layout{display:flex;flex:1;min-height:0}.layout aside{width:320px;flex-shrink:0;overflow:auto;padding:18px;background:white}.layout main{flex:1;min-width:0;padding:20px;overflow:auto}.stage{position:relative;width:100%;background:#111}.stage img,.stage video{width:100%;height:100%;display:block}.stage svg{position:absolute;inset:0;width:100%;height:100%;cursor:crosshair}.annotation-workbench label{display:block;margin:12px 0}.annotation-workbench input:not([type=range]),.annotation-workbench select{box-sizing:border-box;width:100%;padding:8px;border:1px solid #cbd5e1;border-radius:6px}.annotation-workbench button{padding:8px 10px;border:1px solid #cbd5e1;border-radius:6px;background:white;color:inherit;cursor:pointer;margin:3px}.annotation-workbench button:disabled{opacity:.45;cursor:default}.annotation-workbench .primary{background:#2563eb;color:white}.annotation-workbench p{font-size:12px;color:#64748b}.annotation-workbench .error{color:#b91c1c;overflow-wrap:anywhere}.actions{display:flex;flex-wrap:wrap}.list{max-height:220px;overflow:auto}.list button{display:block;text-align:left;width:95%}.list .chosen{border-color:#2563eb;background:#eff6ff}.video-controls{display:flex;align-items:center;gap:10px}.video-controls input{flex:1}.empty{padding:100px 20px;text-align:center}.legend{text-align:center}@media(max-width:750px){.layout{flex-direction:column-reverse}.layout aside{width:auto;max-height:45%;}.layout main{min-height:30vh;padding:8px}}
</style>
