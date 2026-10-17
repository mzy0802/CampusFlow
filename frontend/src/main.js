import { createApp } from 'vue'
import 'leaflet/dist/leaflet.css'
import './style.css'
import './fonts.css'
import App from './App.vue'
import SimulationApp from './SimulationApp.vue'

document.title=location.pathname.startsWith('/debug')?'CampusFlow · 调试与标注':'CampusFlow · 早高峰交通演示'
createApp(location.pathname.startsWith('/debug') ? App : SimulationApp).mount('#app')
