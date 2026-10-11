<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import CameraImage from '../components/CameraImage.vue'
import StockHistoryChart from '../components/StockHistoryChart.vue'
import TimeRangePicker from '../components/TimeRangePicker.vue'
import ImageTimeline from '../components/ImageTimeline.vue'
import { getArea } from '../api/areas.js'
import { getCamera, getCameraImages, getLatestImageUrl } from '../api/cameras.js'
import { getImageUrl } from '../api/images.js'
import { stockColor, stockLabel, statusColorAt } from '../constants/stock.js'
import { imageTimestamp, formatTime } from '../utils/time.js'
import { useGoBack } from '../composables/useGoBack.js'

const props = defineProps({ areaId: { type: String, required: true } })

const area = ref(null) // full (unranged) area, for the current state
const history = ref([]) // history in the selected range
const camera = ref(null)
const images = ref([])
const selectedImage = ref(null) // null = latest
const latestUrl = ref('')
const range = ref({})
const error = ref(null)

const router = useRouter()
const goBack = useGoBack()

const current = computed(() => area.value?.history.at(-1) ?? null)
const polygon = computed(() => camera.value?.areas.find((a) => a.id === props.areaId)?.imageCoordinates ?? null)
const imageSrc = computed(() => (selectedImage.value ? getImageUrl(selectedImage.value) : latestUrl.value))

const markColor = (ts) => statusColorAt(area.value?.history ?? [], ts)

function showOnMap() {
  router.push({ name: 'store', query: { locate: props.areaId } })
}

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
  <button class="back" @click="goBack">← Back</button>

  <p v-if="error" class="error">Could not load area: {{ error }}</p>
  <p v-else-if="!area" class="muted">Loading…</p>

  <template v-else>
    <header class="area-header">
      <div>
        <h1>{{ area.productName }}</h1>
        <p class="muted">
          Area {{ area.id }} ·
          <RouterLink :to="{ name: 'camera', params: { cameraId: area.cameraId } }">Camera {{ area.cameraId }}</RouterLink>
        </p>
      </div>
      <div class="badges">
        <template v-if="current">
          <span v-if="current.compliant" class="badge">
            <span class="dot" :style="{ background: stockColor(current.stockLevel) }" />
            {{ stockLabel(current.stockLevel) }}
          </span>
          <!-- An empty area holds no product, so compliance doesn't apply. -->
          <span v-if="!current.compliant" class="badge bad">
            ✕ Wrong product
          </span>
          <span v-if="current.occupancy != null" class="badge" title="Share of the area covered by produce">
            {{ Math.round(current.occupancy * 100) }}% occupied
          </span>
        </template>
        <button class="pill-button" @click="showOnMap">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" />
            <circle cx="12" cy="9.5" r="2.5" />
          </svg>
          Show on map
        </button>
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
        <ImageTimeline v-model="selectedImage" :images="images" :mark-color="markColor" />
      </section>

      <section class="card">
        <h2>Stock history</h2>
        <TimeRangePicker v-model="range" :min="area.history[0]?.timestamp" :max="area.history.at(-1)?.timestamp" />
        <StockHistoryChart :history="history" class="chart" />
        <p class="muted legend">
          <span class="wrong-marker">✕</span> Purple crosses mark moments with the wrong product in the area.
          <template v-if="history.some((h) => h.occupancy != null)">
            <span class="occupancy-marker">- -</span> Dashed line: share of the area covered by produce.
          </template>
        </p>
      </section>
    </div>
  </template>
</template>

<style scoped>
.area-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.area-header h1 { margin: 0; font-size: 1.4rem; }
.area-header p { margin: 4px 0 0; }
.badges { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.badge.ok { color: #1f7a4d; }
/* Same purple as wrong-product areas on the map (AREA_STATUSES.wrong). */
.badge.bad {
  --wrong: #8e4ec6;
  color: color-mix(in srgb, var(--wrong) 75%, var(--text));
  background: color-mix(in srgb, var(--wrong) 16%, transparent);
  border-color: color-mix(in srgb, var(--wrong) 45%, transparent);
}
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 460px), 1fr)); gap: 16px; }
h2 { margin: 0 0 12px; font-size: 1.05rem; }
h2 small { font-weight: 400; margin-left: 6px; }
.chart { margin-top: 12px; }
.legend { font-size: 0.85rem; margin: 8px 0 0; }
.wrong-marker { color: #8e4ec6; font-weight: 700; }
.occupancy-marker { color: #2f6fd6; font-weight: 700; margin-left: 8px; }

@media (max-width: 768px) {
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
