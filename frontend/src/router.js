import { createRouter, createWebHistory } from 'vue-router'
import StorePage from './pages/StorePage.vue'
import AreaPage from './pages/AreaPage.vue'
import CameraPage from './pages/CameraPage.vue'

export default createRouter({
  history: createWebHistory(),
  routes: [
    // `wide` lets the page use (almost) the full window width.
    { path: '/', name: 'store', component: StorePage, meta: { wide: true } },
    { path: '/areas/:areaId', name: 'area', component: AreaPage, props: true },
    { path: '/cameras/:cameraId', name: 'camera', component: CameraPage, props: true },
  ],
})
