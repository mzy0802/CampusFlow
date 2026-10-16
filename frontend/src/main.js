import { createApp } from 'vue'
import 'leaflet/dist/leaflet.css'
import './style.css'
import App from './App.vue'
import NavigationApp from './NavigationApp.vue'

document.title=location.pathname.startsWith('/debug')?'CampusFlow · 调试与标注':'CampusFlow · 校园导航'
createApp(location.pathname.startsWith('/debug') ? App : NavigationApp).mount('#app')
