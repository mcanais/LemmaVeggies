<script setup>
import { ref, computed, watch } from 'vue'
import CameraImage from '../components/CameraImage.vue'
import StockHistoryChart from '../components/StockHistoryChart.vue'
import TimeRangePicker from '../components/TimeRangePicker.vue'
import ImageTimeline from '../components/ImageTimeline.vue'
import { getArea } from '../api/areas.js'
import { getCamera, getCameraImages, getLatestImageUrl } from '../api/cameras.js'
import { getImageUrl } from '../api/images.js'
import { stockColor, stockLabel } from '../constants/stock.js'
import { imageTimestamp, formatTime } from '../utils/time.js'

const props = defineProps({ areaId: { type: String, required: true } })

const area = ref(null) // full (unranged) area, for the current state
const history = ref([]) // history in the selected range
const camera = ref(null)
const images = ref([])
const selectedImage = ref(null) // null = latest
const latestUrl = ref('')
const range = ref({})
const error = ref(null)

const current = computed(() => area.value?.history.at(-1) ?? null)
const polygon = computed(() => camera.value?.areas.find((a) => a.id === props.areaId)?.imageCoordinates ?? null)
const imageSrc = computed(() => (selectedImage.value ? getImageUrl(selectedImage.value) : latestUrl.value))

function imageLabel(imageId) {
  const ts = imageTimestamp(imageId)
  return ts ? formatTime(ts) : imageId
}

async function loadArea() {
  error.value = null
  area.value = null
  camera.value = null
  selectedImage.value = null
  range.value = {}
  try {
    area.value = await getArea(props.areaId)
    history.value = area.value.history
    latestUrl.value = getLatestImageUrl(area.value.cameraId)
    const [cam, imgs] = await Promise.all([getCamera(area.value.cameraId), getCameraImages(area.value.cameraId)])
    camera.value = cam
    images.value = imgs
  } catch (e) {
    error.value = e.message
  }
}

async function loadRange() {
  if (!area.value) return
  try {
    const [ranged, imgs] = await Promise.all([
      getArea(props.areaId, range.value),
      getCameraImages(area.value.cameraId, range.value),
    ])
    history.value = ranged.history
    images.value = imgs
    if (selectedImage.value && !imgs.includes(selectedImage.value)) selectedImage.value = null
  } catch (e) {
    error.value = e.message
  }
}

watch(() => props.areaId, loadArea, { immediate: true })
watch(range, loadRange)
</script>

<template>
  <RouterLink to="/" class="back">← Back to map</RouterLink>

  <p v-if="error" class="error">Could not load area: {{ error }}</p>
  <p v-else-if="!area" class="muted">Loading…</p>

  <template v-else>
    <header class="area-header">
      <div>
        <h1>{{ area.productName }}</h1>
        <p class="muted">Area {{ area.id }} · Camera {{ area.cameraId }}</p>
      </div>
      <div v-if="current" class="badges">
        <span class="badge">
          <span class="dot" :style="{ background: stockColor(current.stockLevel) }" />
          {{ stockLabel(current.stockLevel) }}
        </span>
        <span class="badge" :class="current.compliant ? 'ok' : 'bad'">
          {{ current.compliant ? '✓ Compliant' : '⚠ Wrong product' }}
        </span>
      </div>
    </header>

    <div class="grid">
      <section class="card camera-card">
        <h2>
          Camera view
          <small class="muted">{{ selectedImage ? imageLabel(selectedImage) : 'latest' }}</small>
        </h2>
        <CameraImage
          :src="imageSrc"
          :polygon="polygon"
          :alt="`Camera ${area.cameraId} showing ${area.productName}`"
        />
        <ImageTimeline v-model="selectedImage" :images="images" :history="area.history" />
      </section>

      <section class="card">
        <h2>Stock history</h2>
        <TimeRangePicker v-model="range" />
        <StockHistoryChart :history="history" class="chart" />
        <p class="muted legend"><span class="wrong-marker">▲</span> Purple triangles mark moments with the wrong product in the area.</p>
      </section>
    </div>
  </template>
</template>

<style scoped>
.back { display: inline-block; margin-bottom: 12px; text-decoration: none; }
.area-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.area-header h1 { margin: 0; font-size: 1.4rem; }
.area-header p { margin: 4px 0 0; }
.badges { display: flex; gap: 8px; flex-wrap: wrap; }
.badge.ok { color: #1f7a4d; }
.badge.bad { color: #a01d22; background: #fde2e2; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 460px), 1fr)); gap: 16px; }
h2 { margin: 0 0 12px; font-size: 1.05rem; }
h2 small { font-weight: 400; margin-left: 6px; }
.chart { margin-top: 12px; }
.legend { font-size: 0.85rem; margin: 8px 0 0; }
.wrong-marker { color: #8e4ec6; }

@media (max-width: 768px) {
  /* Back link becomes a sticky bar so it's always one tap away. */
  .back {
    position: sticky;
    top: 0;
    z-index: 5;
    display: flex;
    align-items: center;
    min-height: 44px;
    margin: -12px -12px 8px;
    padding: 0 12px;
    background: color-mix(in srgb, var(--bg) 92%, transparent);
    backdrop-filter: blur(6px);
    border-bottom: 1px solid var(--border);
  }
  .area-header { flex-direction: column; gap: 8px; margin-bottom: 12px; }
  .area-header h1 { font-size: 1.2rem; }
  .grid { gap: 12px; }
  /* Full-bleed camera image: the card loses its side padding/border. */
  .camera-card { margin: 0 -12px; border-radius: 0; border-left: none; border-right: none; padding: 12px 0; }
  .camera-card h2 { padding: 0 12px; }
  .camera-card :deep(.camera-image) { border-radius: 0; }
  .camera-card :deep(.timeline) { padding: 0 12px; }
}
</style>
