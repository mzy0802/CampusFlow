<script setup>
import {computed,onBeforeUnmount,onMounted,ref} from 'vue'
import L from 'leaflet'
import {getJson} from './api'
import MapIcon from './components/MapIcon.vue'
import VisionPanel from './components/VisionPanel.vue'
import RouteWorkbench from './components/RouteWorkbench.vue'
import ParkingEditor from './components/ParkingEditor.vue'
import TransitWorkbench from './components/TransitWorkbench.vue'
const editingParking=ref(false)
const areas=ref(null),snapshot=ref(null),observations=ref([]),error=ref(''),loading=ref(false)
const selected=ref(''),tab=ref('parking'),moduleInfo=ref(''),useOsm=ref(true),tileError=ref(false)
const query=ref(''),panelOpen=ref(true),mapEl=ref(null),layerOpen=ref(false)
let map,polygons,tiles,labels,timer,resizeObserver,stopped=false
const colors={available:'#188038',busy:'#f29900',full:'#d93025',unknown:'#9aa0a6',clear:'#188038',moderate:'#1a73e8',crowded:'#f29900',overloaded:'#d93025'}
const states={available:'有空位',busy:'较拥挤',full:'已满',unknown:'等待更新',clear:'通畅',moderate:'适中',crowded:'拥挤',overloaded:'超出容量'}
const rows=computed(()=>(areas.value?.features||[]).map(feature=>({...feature.properties,...(snapshot.value?.items.find(item=>item.id===feature.properties.id)||{state:'unknown'}),observation:observations.value.find(item=>item.area_id===feature.properties.id)})))
const filtered=computed(()=>rows.value.filter(item=>`${item.name} ${item.id}`.toLowerCase().includes(query.value.trim().toLowerCase())))
const available=computed(()=>snapshot.value?rows.value.reduce((sum,item)=>sum+(item.available||0),0):'—')
const selectedArea=computed(()=>rows.value.find(item=>item.id===selected.value))
const updated=computed(()=>snapshot.value?new Date(snapshot.value.updated_at).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'}):'等待连接')
const tabs=[['parking','parking','停车'],['vision','people','人车识别'],['roads','road','道路'],['transit','bus','公交'],['routing','route','路线']]
function color(item){return item?.observation ? colors[item.observation.two_wheeler?.level || 'unknown'] : colors[item?.state||'unknown']}
function vehicleText(item){const m=item.observation?.two_wheeler;return m?`两轮车候选 ${m.count} 辆 · 估算 ${m.percent}%`:'旧版结果，请重新上传识别'}
function fitAll(){
  if(!polygons?.getBounds().isValid())return
  const wide=window.innerWidth>760&&panelOpen.value
  map.fitBounds(polygons.getBounds(),{paddingTopLeft:[wide?450:40,100],paddingBottomRight:[70,80],maxZoom:19})
}
function selectArea(id){
  selected.value=id
  polygons?.eachLayer(layer=>{if(layer.feature.properties.id===id)map.fitBounds(layer.getBounds(),{paddingTopLeft:[window.innerWidth>760&&panelOpen.value?450:50,100],paddingBottomRight:[70,80],maxZoom:19})})
  paint()
}
function paint(){
  labels?.clearLayers()
  polygons?.eachLayer(layer=>{
    const item=rows.value.find(row=>row.id===layer.feature.properties.id)
    layer.setStyle({color:color(item),weight:selected.value===item?.id?4:2,fillOpacity:selected.value===item?.id ? 0.3 : 0.16})
    const tooltip=document.createElement('span')
    tooltip.textContent=item.observation?`${item.name} · ${vehicleText(item)}`:`${item.name} · ${item.available??'—'}/${item.capacity} 空位（模拟）`
    layer.bindTooltip(tooltip,{sticky:true})
    const label=document.createElement('div');label.className='parking-pin';label.style.setProperty('--pin-color',color(item))
    const badge=document.createElement('b');badge.textContent='P'
    const text=document.createElement('span');text.textContent=item.observation?(item.observation.two_wheeler ? `${item.observation.two_wheeler.percent}%` : '待复测'):`${item.available??'—'} 空位`
    label.append(badge,text)
    L.marker(layer.getBounds().getCenter(),{icon:L.divIcon({html:label,className:'map-pin-container',iconSize:[90,32],iconAnchor:[45,16]}),keyboard:true,title:item.name}).on('click',()=>selectArea(item.id)).addTo(labels)
  })
}
async function refreshObservations(){try{const data=await getJson('/vision/observations');if(!stopped){observations.value=data.items;paint()}}catch{/* Parking remains usable with the previous backend. */}}
async function refresh(){
  if(loading.value)return
  loading.value=true
  try{const result=await getJson('/parking/status');if(stopped)return;snapshot.value=result;error.value='';paint();await refreshObservations()}
  catch{if(!stopped)error.value='状态更新失败，已显示的数据可能过期。请检查后端。'}
  finally{loading.value=false}
}
async function load(){
  try{
    const data=await getJson('/parking/areas');if(stopped)return;areas.value=data;polygons?.remove()
    polygons=L.geoJSON(data,{onEachFeature(feature,layer){layer.on('click',()=>selectArea(feature.properties.id))}}).addTo(map)
    fitAll();paint();await refresh()
  }catch{if(!stopped)error.value='停车区域加载失败，请检查后端连接后重新加载。'}
}
function toggleOsm(){tileError.value=false;if(useOsm.value)tiles.addTo(map);else if(map.hasLayer(tiles))map.removeLayer(tiles)}
async function switchTab(value){
  tab.value=value;panelOpen.value=true;moduleInfo.value=''
  if(['parking','vision'].includes(value))return
  if(value==='routing'){moduleInfo.value='路线规划正在准备中，接入校园路网后开放。';return}
  try{const info=await getJson(value==='roads'?'/roads':'/transit');if(tab.value===value)moduleInfo.value=info.message}catch{moduleInfo.value='服务暂时不可用，请检查后端。'}
}
function search(){if(filtered.value.length)selectArea(filtered.value[0].id)}
onMounted(async()=>{
  map=L.map(mapEl.value,{center:[0,0],zoom:17,zoomControl:false})
  L.control.zoom({position:'bottomright'}).addTo(map);L.control.scale({position:'bottomright',imperial:false}).addTo(map)
  labels=L.layerGroup().addTo(map)
  tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'})
  tiles.on('tileerror',()=>{tileError.value=true});if(useOsm.value)tiles.addTo(map)
  resizeObserver=new ResizeObserver(()=>map.invalidateSize());resizeObserver.observe(mapEl.value)
  await load();if(!stopped)timer=setInterval(refresh,15000)
})
onBeforeUnmount(()=>{stopped=true;clearInterval(timer);resizeObserver?.disconnect();map?.remove()})
</script>
<template>
  <main class="maps-app">
    <ParkingEditor v-if="editingParking" @close="editingParking=false;load()" />
    <TransitWorkbench v-if="tab==='transit'" @close="tab='parking';refresh()" />
    <RouteWorkbench v-if="['roads','routing'].includes(tab)" :areas="rows" :parking-geo-json="areas" @close="tab='parking';refresh()" />
    <div ref="mapEl" class="full-map" aria-label="校园停车区域地图"></div>
    <nav class="rail" aria-label="主要功能"><div class="app-symbol"><MapIcon name="map" :size="29" /></div><button v-for="[key,icon,label] in tabs" :key="key" :class="{active:tab===key}" @click="switchTab(key)"><span><MapIcon :name="icon" /></span>{{label}}</button><div class="rail-bottom">DEMO</div></nav>
    <div class="search-box"><button class="icon-button" :aria-label="panelOpen?'收起侧栏':'展开侧栏'" @click="panelOpen=!panelOpen"><MapIcon :name="panelOpen?'close':'search'" /></button><form @submit.prevent="search"><input v-model="query" aria-label="搜索停车区域" placeholder="搜索修远楼周边停车区" @focus="tab='parking';panelOpen=true"><button class="icon-button" aria-label="搜索"><MapIcon name="search" :size="21" /></button></form></div>
    <div class="map-chips" aria-label="地图快捷操作"><button class="chip active" @click="switchTab('parking');fitAll()"><MapIcon name="parking" :size="17" />周边停车</button><button class="chip" @click="switchTab('vision')"><MapIcon name="people" :size="17" />人车识别测试</button><span class="campus-label">长安大学 · 渭水校区</span></div>
    <aside v-show="panelOpen" class="side-panel" aria-label="区域与识别面板">
      <section v-show="tab==='parking'">
        <div class="place-heading"><span class="eyebrow">CAMPUS MOBILITY</span><h1>修远楼周边</h1><p>校园停车与出行 · {{rows.length}} 个区域</p><div class="place-tags"><span><i class="dot green"></i>停车数据演示</span><span class="tag">用户导入边界</span></div></div>
        <div class="overview"><div><strong>{{available}}</strong><span>模拟空位</span></div><div><strong>{{observations.length}}</strong><span>已有识别结果</span></div><button class="refresh-button" :disabled="loading" @click="refresh"><MapIcon name="refresh" :size="18" /><span>{{updated}} 更新</span></button></div>
        <div class="section-title"><h2>{{query?'搜索结果':'附近停车区域'}}</h2><button class="text-button" @click="fitAll">查看全部</button></div>
        <p v-if="error" class="alert error" role="alert">{{error}}<button class="text-button" @click="load">重新加载</button></p>
        <p v-if="!filtered.length" class="empty-state">{{query?'没有找到匹配的停车区域':'等待停车区域数据…'}}</p>
        <button v-for="item in filtered" :key="item.id" class="place-card" :class="{selected:selected===item.id}" @click="selectArea(item.id)"><div class="place-icon" :style="{color:color(item)}"><MapIcon name="parking" :size="25" /></div><div class="place-content"><div class="place-title"><h3>{{item.name}}</h3><MapIcon name="arrow" :size="16" /></div><p v-if="item.observation" class="place-state" :style="{color:color(item)}">{{vehicleText(item)}}</p><p v-else class="place-state" :style="{color:color(item)}">{{states[item.state]}} · {{item.available??'—'}} / {{item.capacity}} 空位</p><div class="card-meta"><span>{{item.observation?'上传识别 · 非实时':'停车状态 · 模拟'}}</span><span>{{item.id}}</span></div><div class="occupancy-track"><i :style="{background:color(item),width:`${Math.min(item.observation?.two_wheeler?.percent??((item.occupied||0)/item.capacity*100),100)}%`}"></i></div></div></button>
        <div class="panel-note"><MapIcon name="people" :size="19" /><p>识别人数和自行车、查看拥挤度。<button class="text-button" @click="switchTab('vision')">上传照片或视频 →</button></p></div><p class="data-disclaimer">边界与容量来自上传文件，停车空位仍为模拟；上传识别是画面计数，不能自动等同于区域实时停车量。</p>
      </section>
      <VisionPanel v-show="tab==='vision'" :areas="rows" :selected-id="selected" @observation="refreshObservations" />
      <section v-if="!['parking','vision'].includes(tab)" class="future-panel"><div class="heading-icon blue"><MapIcon :name="tabs.find(t=>t[0]===tab)?.[1]" :size="30" /></div><h2>{{{roads:'校园道路',transit:'公交出行',routing:'路线规划'}[tab]}}</h2><p>{{moduleInfo||'正在加载…'}}</p><span class="tag">即将接入</span></section>
    </aside>
    <div class="top-status"><a href="/" target="_blank" rel="noopener">打开应用页 ↗</a><button @click="editingParking=true">地图停车区标注</button><span class="tag">内部调试</span></div>
    <div v-if="tileError" class="map-message" role="status">底图暂时无法加载，停车区域仍可查看。</div>
    <div class="map-action-stack"><button class="map-action" aria-label="定位到全部停车区域" @click="fitAll"><MapIcon name="locate" /></button><button class="map-action" :class="{active:layerOpen}" aria-label="底图图层" @click="layerOpen=!layerOpen"><MapIcon name="layers" /></button></div>
    <div v-if="layerOpen" class="layer-popover"><strong>地图图层</strong><label><input v-model="useOsm" type="checkbox" @change="toggleOsm"> OpenStreetMap 底图</label><small>保留 OSM 版权署名 · 无需 API Key</small></div>
    <div class="map-legend"><span><i class="dot green"></i>通畅</span><span><i class="dot amber"></i>拥挤</span><span><i class="dot red"></i>已满 / 超出容量</span><small>识别百分比可超过 100%</small></div>
    <div v-if="selectedArea" class="selection-card"><div class="place-icon" :style="{color:color(selectedArea)}"><MapIcon name="parking" /></div><div><strong>{{selectedArea.name}}</strong><span>{{selectedArea.observation?vehicleText(selectedArea):`模拟空位 ${selectedArea.available??'—'} / ${selectedArea.capacity}`}}</span></div><button class="text-button" @click="switchTab('vision')">测试识别</button><button class="icon-button" aria-label="取消区域选择" @click="selected='';paint()"><MapIcon name="close" :size="18" /></button></div>
  </main>
</template>
