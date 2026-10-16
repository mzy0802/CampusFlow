<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getJson } from '../api'
import MapIcon from './MapIcon.vue'
import AnnotationWorkbench from './AnnotationWorkbench.vue'
const annotating=ref(false)
const props = defineProps({ areas: { type: Array, default: () => [] }, selectedId: String })
const emit = defineEmits(['observation'])
const health=ref(null), file=ref(null), areaId=ref(''), bicycleCapacity=ref(100), personCapacity=ref(50)
const confidence=ref(0.2), interval=ref(1), busy=ref(false), uploading=ref(false), error=ref(''), job=ref(null), uploadProgress=ref(0)
let pollTimer, stopped=false, xhr
const currentArea=computed(()=>props.areas.find(area=>area.id===areaId.value))
const active=computed(()=>job.value && ['queued','processing'].includes(job.value.status))
const stateLabels={queued:'等待处理',processing:'正在识别',completed:'识别完成',failed:'处理失败'}
const levelLabels={clear:'检测比例低，待核验',moderate:'检测比例中等',crowded:'检测比例高',overloaded:'检测超过参考容量'}
const resultCards=computed(()=>[['two_wheeler','两轮车候选总数','bike'],['bicycle','自行车','bike'],['motorcycle','电动两轮车 / 摩托车候选','bike'],['person','人员','people']].filter(([key])=>job.value?.result?.[key]))
watch(()=>props.selectedId,value=>{if(!busy.value && value) areaId.value=value},{immediate:true})
watch(currentArea,area=>{if(area && !busy.value) bicycleCapacity.value=area.capacity})
function chooseFile(event){
  const chosen=event.target.files?.[0]; error.value=''
  if(chosen && chosen.size>100*1024*1024){error.value='文件超过 100 MB，请截取或压缩后重试。';file.value=null;return}
  file.value=chosen||null
}
async function checkHealth(){
  try{health.value=await getJson('/vision/health')}
  catch{health.value={ready:false,message:'识别接口暂不可用，请重启更新后的后端。'}}
}
async function poll(){
  try{
    const result=await getJson(`/vision/jobs/${job.value.id}`)
    if(stopped)return
    job.value=result; error.value=''
    if(['completed','failed'].includes(result.status)){
      busy.value=false
      if(result.status==='completed')emit('observation')
      return
    }
  }catch{if(!stopped)error.value='查询进度失败，正在重试；请保持后端运行。'}
  if(!stopped)pollTimer=setTimeout(poll,1500)
}
async function submit(){
  if(!file.value||busy.value)return
  error.value='';job.value=null;busy.value=true;uploading.value=true;uploadProgress.value=0
  const query=new URLSearchParams({filename:file.value.name,bicycle_capacity:String(bicycleCapacity.value),person_capacity:String(personCapacity.value),confidence:String(confidence.value),interval_seconds:String(interval.value)})
  if(areaId.value)query.set('area_id',areaId.value)
  try{
    const result=await new Promise((resolve,reject)=>{
      xhr=new XMLHttpRequest();xhr.open('POST',`/api/vision/jobs?${query}`);xhr.timeout=180000
      xhr.setRequestHeader('Content-Type',file.value.type||'application/octet-stream')
      xhr.upload.onprogress=e=>{if(e.lengthComputable)uploadProgress.value=Math.round(e.loaded/e.total*100)}
      xhr.onerror=()=>reject(new Error('上传连接失败，请检查后端。'))
      xhr.ontimeout=()=>reject(new Error('上传超时，请尝试更小的文件。'))
      xhr.onabort=()=>reject(new Error('上传已中断。'))
      xhr.onload=()=>{
        let data
        try{data=JSON.parse(xhr.responseText)}catch{reject(new Error(`服务器未返回有效结果 (${xhr.status})`));return}
        if(xhr.status>=200&&xhr.status<300)resolve(data)
        else reject(new Error(typeof data.detail==='string'?data.detail:data.detail?.message||`上传失败 (${xhr.status})`))
      }
      xhr.send(file.value)
    })
    if(stopped)return
    job.value=result;uploading.value=false;await poll()
  }catch(err){if(!stopped){error.value=err.message;busy.value=false;uploading.value=false}}
}
onMounted(checkHealth)
onBeforeUnmount(()=>{stopped=true;clearTimeout(pollTimer);xhr?.abort()})
</script>
<template>
  <div class="vision-panel">
    <AnnotationWorkbench v-if="annotating" @close="annotating=false" />
    <button class="primary-button" @click="annotating=true">可停车范围标注 · 批量素材</button>
    <div class="panel-heading"><span class="heading-icon blue"><MapIcon name="people" /></span><div><h2>人车识别实验室</h2><p>上传测试 · 后端分析 · 数据呈现</p></div></div>
    <div class="model-status" :class="{ready:health?.ready}"><i></i><span>{{health?.ready?'识别引擎就绪':health?.message||'正在检查识别引擎…'}}</span><button class="icon-button" aria-label="重新检查识别引擎" @click="checkHealth"><MapIcon name="refresh" :size="16" /></button></div>
    <p v-if="health?.ready" class="muted">{{health.model}} · Qwen 云端视觉计数 · 准确率待核验</p>
    <form @submit.prevent="submit">
      <label class="upload-zone" :class="{chosen:file}"><MapIcon name="upload" :size="30" /><strong>{{file?file.name:'选择照片或视频'}}</strong><span>JPG / PNG / WebP · MP4 / MOV / AVI / WebM</span><small>最大 100 MB，视频最长 2 分钟</small><input aria-label="上传照片或视频" type="file" accept=".jpg,.jpeg,.png,.webp,.mp4,.mov,.avi,.webm" :disabled="busy" @change="chooseFile"></label>
      <label class="field">关联停车区域<select v-model="areaId" :disabled="busy"><option value="">独立测试，不关联地图</option><option v-for="area in areas" :key="area.id" :value="area.id">{{area.name}}</option></select></label>
      <div class="field-grid"><label class="field">两轮车总容量<input v-model.number="bicycleCapacity" type="number" min="1" max="100000" required :disabled="busy"><small>自行车与电动车共用的停车容量</small></label><label class="field">人员参考容量<input v-model.number="personCapacity" type="number" min="1" max="100000" required :disabled="busy"><small>测试参考值，需自行核验</small></label></div>
      <p class="muted">图片原文件将发送到百炼 Qwen，客户端不缩图；云端可能调整分辨率。视频最多抽取12帧调用，可能产生 API 费用。</p>
      <details class="advanced"><summary>识别参数</summary><div class="field-grid"><label v-if="false" class="field">置信度阈值<input v-model.number="confidence" type="number" min="0.05" max="0.95" step="0.05" required :disabled="busy"></label><label class="field">视频采样间隔（秒）<input v-model.number="interval" type="number" min="0.5" max="10" step="0.5" required :disabled="busy"></label></div></details>
      <button class="primary-button" :disabled="!file||busy||!health?.ready"><MapIcon name="upload" :size="18" />{{busy?uploading?`上传中 ${uploadProgress}%`:'后台正在识别…':'开始识别'}}</button>
    </form>
    <p v-if="error" class="alert error" role="alert">{{error}}</p>
    <div v-if="uploading||active" class="job-progress"><div><span>{{uploading?'上传文件':stateLabels[job.status]}}</span><b>{{uploading?uploadProgress:job.progress||0}}%</b></div><progress :value="uploading?uploadProgress:job.progress||0" max="100"></progress><small>识别在后端执行，可以继续浏览地图。</small></div>
    <p v-if="job?.status==='failed'" class="alert error" role="alert">{{job.error}}</p>
    <section v-if="job?.status==='completed'" class="vision-result">
      <div class="result-heading"><h3>识别结果</h3><span class="tag blue-tag">上传测试</span></div><p class="muted">{{job.kind==='video'?'最后一个采样帧':'当前照片'}} · {{job.result.sampled_frames}} 个采样帧</p>
      <div class="count-grid"><div v-for="[key,label,icon] in resultCards" :key="key" class="count-card" :class="job.result[key].latest.level"><MapIcon :name="icon" /><span>{{label}}</span><strong>{{job.result[key].latest.count}}<small>{{key==='person'?'人':'辆'}}</small></strong><b>{{job.result[key].latest.percent}}%</b><p>{{levelLabels[job.result[key].latest.level]}} / {{key==='person'?'人员参考容量':'两轮车总容量'}} {{job.result[key].latest.capacity}}</p><small>采样峰值 {{job.result[key].peak.count}} · {{job.result[key].peak.percent}}%</small></div></div>
      <p v-if="job.result.uncertain_type" class="muted">类型不确定：{{job.result.uncertain_type.latest.count}} 辆（已包含在总数中）</p>
      <p class="info-note">{{job.result.classification_note || '旧版结果只统计自行车，请重新上传。'}} 计数可能漏检或误检，检测比例低不代表现场空闲，不能直接据此判定通畅。</p>
      <figure><img :src="job.preview_url" alt="Qwen计数对应的原始画面"><figcaption>Qwen 计数 · 原图预览，无检测框</figcaption></figure>
      <details v-if="job.kind==='video'" class="timeline"><summary>查看采样记录</summary><table><thead><tr><th>秒</th><th>人数</th><th>自行车</th><th>电动车候选</th><th>两轮总数</th></tr></thead><tbody><tr v-for="sample in job.result.samples" :key="sample.time_seconds"><td>{{sample.time_seconds}}</td><td>{{sample.person}}</td><td>{{sample.bicycle}}</td><td>{{sample.motorcycle??'—'}}</td><td>{{sample.two_wheeler??'—'}}</td></tr></tbody></table></details>
    </section>
    <div class="info-note"><strong>拥挤度可以超过 100%</strong><p>两轮车候选总数 ÷ 两轮车停车容量 × 100%。例如 120 辆 / 100 辆 = 120%。自行车和电动两轮车候选分开显示，分项比例也以两轮车总容量为分母。车型和数量仍需人工核验；视频为抽帧统计，不是去重通行量。</p></div>
  </div>
</template>
