<script setup>
import { ref, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import CameraImage from '../components/CameraImage.vue'
import ImageTimeline from '../components/ImageTimeline.vue'
import { getArea } from '../api/areas.js'
import { getCamera, getCameraImages, getLatestImageUrl } from '../api/cameras.js'
import { getImageUrl } from '../api/images.js'
import { AREA_STATUSES, UNKNOWN_COLOR, areaStatus, statusAt } from '../constants/stock.js'
import { imageTimestamp, formatTime } from '../utils/time.js'
import { useGoBack } from '../composables/useGoBack.js'

const props = defineProps({ cameraId: { type: String, required: true } })

const router = useRouter()
const goBack = useGoBack()

const areas = ref([]) // [{ id, productName, imageCoordinates, history }]
const images = ref([])
const selectedImage = ref(null) // null = latest
const latestUrl = ref('')
const hoveredId = ref(null)
const error = ref(null)
const loading = ref(true)

const STATUS_ORDER = Object.keys(AREA_STATUSES)

async function load() {
  error.value = null
  loading.value = true
  areas.value = []
  selectedImage.value = null
  try {
    latestUrl.value = getLatestImageUrl(props.cameraId)
    const [camera, imgs] = await Promise.all([getCamera(props.cameraId), getCameraImages(props.cameraId)])
    images.value = imgs
    const details = await Promise.all(camera.areas.map((a) => getArea(a.id)))
    areas.value = camera.areas.map((a, i) => ({ ...a, history: details[i].history }))
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(() => props.cameraId, load, { immediate: true })

// Moment shown: the selected image, or the latest one.
const imageIds = computed(() => [...images.value].sort((a, b) => imageTimestamp(a) - imageTimestamp(b)))
const shownTs = computed(() => imageTimestamp(selectedImage.value ?? imageIds.value.at(-1) ?? '') ?? Infinity)
const imageSrc = computed(() => (selectedImage.value ? getImageUrl(selectedImage.value) : latestUrl.value))

// Each area's state at the shown moment.
const rows = computed(() =>
  areas.value
    .map((a) => {
      const state = statusAt(a.history, shownTs.value)
      const status = state ? areaStatus(state) : null
      return { ...a, status, color: AREA_STATUSES[status]?.color ?? UNKNOWN_COLOR }
    })
    .sort(
      (a, b) =>
        rank(a.status) - rank(b.status) ||
        a.id.localeCompare(b.id, undefined, { numeric: true }),
    ),
)

function rank(status) {
  const i = STATUS_ORDER.indexOf(status)
  return i < 0 ? STATUS_ORDER.length : i
}

const counts = computed(() =>
  STATUS_ORDER.map((key) => ({ key, ...AREA_STATUSES[key], count: rows.value.filter((r) => r.status === key).length })).filter(
    (s) => s.count,
  ),
)

const overlay = computed(() =>
  rows.value.map((r) => ({
    id: r.id,
    polygon: r.imageCoordinates,
    color: r.color,
    label: `${r.productName} · ${AREA_STATUSES[r.status]?.label ?? 'Unknown'}`,
  })),
)

// Timeline marks take the most urgent status among the camera's areas.
function markColor(ts) {
  let worst = null
  for (const a of areas.value) {
    const state = statusAt(a.history, ts)
    if (state && rank(areaStatus(state)) < rank(worst)) worst = areaStatus(state)
  }
  return AREA_STATUSES[worst]?.color ?? UNKNOWN_COLOR
}

function openArea(areaId) {
  router.push({ name: 'area', params: { areaId } })
}

function showOnMap() {
  router.push({ name: 'store', query: { camera: props.cameraId } })
}
</script>

<template>
  <button class="back" @click="goBack">← Back</button>

  <p v-if="error" class="error">Could not load camera: {{ error }}</p>
  <p v-else-if="loading" class="muted">Loading…</p>

  <template v-else>
    <header class="camera-header">
      <div>
        <h1>Camera {{ cameraId }}</h1>
        <p class="muted">{{ areas.length }} areas</p>
      </div>
      <button class="pill-button" @click="showOnMap">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" />
          <circle cx="12" cy="9.5" r="2.5" />
        </svg>
        Show on map
      </button>
    </header>

    <div class="badges">
      <span v-for="s in counts" :key="s.key" class="badge">
        <span class="dot" :style="{ background: s.color }" />
        {{ s.label }} <strong>{{ s.count }}</strong>
      </span>
    </div>

    <div class="grid">
      <section class="card camera-card">
        <h2>
          Camera view
          <small class="muted">{{ selectedImage ? formatTime(imageTimestamp(selectedImage)) : 'latest' }}</small>
        </h2>
        <CameraImage
          :src="imageSrc"
          :areas="overlay"
          :highlighted-id="hoveredId"
          :alt="`Camera ${cameraId}`"
          @select="openArea"
          @hover="hoveredId = $event"
        />
        <ImageTimeline v-model="selectedImage" :images="images" :mark-color="markColor" />
      </section>

      <section class="card">
        <h2>Areas</h2>
        <ul class="rows">
          <li v-for="r in rows" :key="r.id">
            <RouterLink
              :to="{ name: 'area', params: { areaId: r.id } }"
              class="row"
              :class="{ active: r.id === hoveredId }"
              :style="{ '--status-color': r.color }"
              @mouseenter="hoveredId = r.id"
              @mouseleave="hoveredId = null"
              @focus="hoveredId = r.id"
              @blur="hoveredId = null"
            >
              <span class="status-icon" aria-hidden="true">{{ AREA_STATUSES[r.status]?.icon ?? '?' }}</span>
              <span class="info">
                <span class="product">{{ r.productName }}</span>
                <span class="meta">Area {{ r.id }}</span>
              </span>
              <span class="status-pill">{{ AREA_STATUSES[r.status]?.label ?? 'Unknown' }}</span>
              <span class="chevron" aria-hidden="true">›</span>
            </RouterLink>
          </li>
        </ul>
      </section>
    </div>
  </template>
</template>

<style scoped src="../styles/list.css"></style>

<style scoped>
.camera-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.camera-header h1 { margin: 0; font-size: 1.4rem; }
.camera-header p { margin: 4px 0 0; }
.badges { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 460px), 1fr)); gap: 16px; align-items: start; }
h2 { margin: 0 0 12px; font-size: 1.05rem; }
h2 small { font-weight: 400; margin-left: 6px; }
.rows { overflow: visible; }
.row.active { border-color: var(--status-color); background: color-mix(in srgb, var(--status-color) 10%, var(--surface)); }
.status-pill {
  flex-shrink: 0;
  font-size: 0.78rem;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 999px;
  color: color-mix(in srgb, var(--status-color) 70%, var(--text));
  background: color-mix(in srgb, var(--status-color) 14%, transparent);
}

@media (max-width: 768px) {
  .camera-header { margin-bottom: 8px; }
  .badges { margin-bottom: 12px; }
  .camera-header h1 { font-size: 1.2rem; }
  .grid { gap: 12px; }
  /* Full-bleed camera image: the card loses its side padding/border. */
  .camera-card { margin: 0 -12px; border-radius: 0; border-left: none; border-right: none; padding: 12px 0; }
  .camera-card h2 { padding: 0 12px; }
  .camera-card :deep(.camera-image) { border-radius: 0; }
  .camera-card :deep(.timeline) { padding: 0 12px; }
}
</style>
