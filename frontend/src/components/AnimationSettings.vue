<script setup>
import {ref} from 'vue'
const open=ref(false),count=ref(Number(localStorage.getItem('campusflow.animation.count'))||1000),saved=ref(false)
function save(){count.value=Math.max(100,Math.min(1000,Math.round(count.value/50)*50));localStorage.setItem('campusflow.animation.count',String(count.value));saved.value=true}
</script>
<template><div class="animation-settings"><button @click="open=!open">早高峰动效设置</button><section v-if="open"><h3>地图图标显示上限</h3><label>{{count}} 个 <input type="range" min="100" max="1000" step="50" v-model.number="count"></label><p>4000 人、3400 辆车的总需求不变。此处只设置抽样显示的 100—1000 个图标，不改变停车和导航统计。</p><button @click="save">保存并通知展示页</button><span v-if="saved">已保存，打开的展示页会更新显示数量。</span><a href="/" target="_blank" rel="noopener">打开动画展示 ↗</a></section></div></template>
<style scoped>.animation-settings{position:absolute;right:20px;top:75px;z-index:1300;font-size:12px}.animation-settings button{background:#fffef8;border:1px solid #ccc;border-radius:5px;padding:10px;cursor:pointer}.animation-settings section{width:280px;background:white;padding:18px;box-shadow:0 4px 20px #0003;border-radius:8px;margin-top:8px}.animation-settings label,.animation-settings a,.animation-settings span{display:block;margin-top:12px}.animation-settings p{font-size:11px;line-height:1.8;margin:12px 0;color:#777}.animation-settings input{width:100%}</style>
