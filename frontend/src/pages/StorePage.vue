<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StoreMap from '../components/StoreMap.vue'
import StatusPieChart from '../components/StatusPieChart.vue'
import CamerasList from '../components/CamerasList.vue'
import ProductsList from '../components/ProductsList.vue'
import MobileTabBar from '../components/MobileTabBar.vue'
import CameraSheet from '../components/CameraSheet.vue'
import { getAreas } from '../api/areas.js'
import { AREA_STATUSES, areaStatus, countByStatus } from '../constants/stock.js'
import { useIsMobile, useCanHover } from '../composables/useMediaQuery.js'

const REFRESH_MS = 60_000

const areas = ref([])
const error = ref(null)
const loading = ref(true)
const lastUpdated = ref(null)
const filter = ref(null) // null | 'wrong' | 'empty' | 'half' | 'full' (phone only)
const highlightedIds = ref([]) // areas hovered/located from a list, shown on the map
const highlightedCameraIds = ref([]) // cameras hovered/located from a list, ringed as a whole
const locatedLabel = ref(null) // set while something picked with "Show on map" is highlighted
const listTab = ref('cameras') // 'cameras' | 'products'

const isMobile = useIsMobile()
// Without hover (touch screens) the lists need a button to show a row on the map.
const canHover = useCanHover()
const mobileTab = ref('map') // 'map' | 'cameras' | 'products' | 'stats'
const selectedCameraId = ref(null) // camera tapped on the map (touch), shown in the sheet
const map = ref(null)
const mapCard = ref(null)

const route = useRoute()
const router = useRouter()

async function load() {
  try {
    areas.value = await getAreas()
    lastUpdated.value = new Date()
    error.value = null
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

let timer
onMounted(() => {
  load()
  timer = setInterval(load, REFRESH_MS)
})
onUnmounted(() => clearInterval(timer))

const areasByCamera = computed(() => {
  const groups = {}
  for (const area of areas.value) (groups[area.cameraId] ??= []).push(area)
  return groups
})

const counts = computed(() => countByStatus(areas.value))

const cameraCount = computed(() => Object.keys(areasByCamera.value).length)
const productCount = computed(() => new Set(areas.value.map((a) => a.productName)).size)

function selectTab(tab) {
  listTab.value = tab
  clearMapSelection()
}

// List hover only highlights while nothing is located, so hovering doesn't wipe a locate.
function hoverAreas(ids) {
  if (!locatedLabel.value) highlightedIds.value = ids
}
function hoverCameras(ids) {
  if (!locatedLabel.value) highlightedCameraIds.value = ids
}

// Cameras with an area needing action now, shown as a badge on the Cameras tab.
const urgentCount = computed(
  () => Object.values(areasByCamera.value).filter((list) => list.some((a) => ['wrong', 'empty'].includes(areaStatus(a)))).length,
)

// "Show on map": jump to the map and centre on those areas.
async function locate(ids) {
  const located = areas.value.filter((a) => ids.includes(a.id))
  if (!located.length) return
  const names = new Set(located.map((a) => a.productName))
  clearMapSelection()
  highlightedIds.value = located.map((a) => a.id)
  locatedLabel.value = names.size === 1 ? [...names][0] : `${located.length} areas`
  await showMap()
  map.value?.focusAreas(highlightedIds.value)
}

// "Show on map" for whole cameras: ring them rather than their areas.
async function locateCameras(ids) {
  const located = ids.filter((id) => id in areasByCamera.value)
  if (!located.length) return
  clearMapSelection()
  highlightedCameraIds.value = located
  locatedLabel.value = located.length === 1 ? `Camera ${located[0]}` : `${located.length} cameras`
  await showMap()
  map.value?.focusCameras(located)
}

async function showMap() {
  mobileTab.value = 'map'
  await nextTick()
  if (!isMobile.value) mapCard.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
}

function clearMapSelection() {
  selectedCameraId.value = null
  highlightedIds.value = []
  highlightedCameraIds.value = []
  locatedLabel.value = null
}

// Leaving the map closes the sheet; highlights from the lists only make sense on the map.
watch(mobileTab, (tab) => {
  if (tab !== 'map') selectedCameraId.value = null
})
watch(isMobile, () => clearMapSelection())

// Other pages link here with ?locate=<areaId>[,<areaId>…] or ?camera=<cameraId>.
// Handled once the areas are loaded, then dropped from the URL so a refresh
// doesn't locate again.
watch(
  [() => route.query.locate, () => route.query.camera, loading],
  ([areaIds, cameraIds, isLoading]) => {
    if ((!areaIds && !cameraIds) || isLoading) return
    if (cameraIds) locateCameras(String(cameraIds).split(','))
    else locate(String(areaIds).split(','))
    router.replace({ query: {} })
  },
  { immediate: true },
)

const filters = computed(() =>
  Object.entries(AREA_STATUSES).map(([key, s]) => ({ key, label: s.label, color: s.color, count: counts.value[key] })),
)

function toggle(key) {
  filter.value = filter.value === key ? null : key
}

function isDimmed(area) {
  return filter.value !== null && areaStatus(area) !== filter.value
}
</script>

<template>
  <div
    class="store-page"
    :class="{ mobile: isMobile }"
    :style="isMobile ? { '--sheet-bottom': 'calc(var(--tabbar-h) + env(safe-area-inset-bottom))', '--sheet-safe-bottom': '0px' } : null"
  >
    <section class="toolbar">
      <h1>Store overview</h1>
      <span v-if="lastUpdated" class="muted updated">Updated {{ lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) }}</span>
      <button class="refresh" aria-label="Refresh" @click="load">
        <span aria-hidden="true">↻</span><span class="refresh-label">Refresh</span>
      </button>
    </section>

    <p v-if="error" class="error">Could not load areas: {{ error }}</p>
    <p v-else-if="loading" class="muted">Loading…</p>

    <!-- Phone: one section at a time, switched from the bottom tab bar. -->
    <template v-else-if="isMobile">
      <div v-show="mobileTab === 'map'" class="m-panel m-map">
        <div class="filters" role="group" aria-label="Filter areas">
          <button v-for="f in filters" :key="f.key" :aria-pressed="filter === f.key" @click="toggle(f.key)">
            <span class="dot" :style="{ background: f.color }" />
            {{ f.label }} <strong>{{ f.count }}</strong>
          </button>
        </div>
        <div class="m-map-wrap">
          <StoreMap
            ref="map"
            zoomable
            :areas-by-camera="areasByCamera"
            :is-dimmed="isDimmed"
            :highlighted-ids="highlightedIds"
            :highlighted-camera-ids="highlightedCameraIds"
            :selected-camera-id="selectedCameraId"
            @select="selectedCameraId = $event"
            @clear="clearMapSelection"
          />
          <button v-if="locatedLabel" class="clear-highlight" @click="clearMapSelection">
            Showing {{ locatedLabel }} <span aria-hidden="true">×</span>
          </button>
        </div>
      </div>

      <KeepAlive>
        <CamerasList
          v-if="mobileTab === 'cameras'"
          class="card m-panel"
          locatable
          :areas="areas"
          @locate="locateCameras"
        />
        <ProductsList
          v-else-if="mobileTab === 'products'"
          class="card m-panel"
          locatable
          :areas="areas"
          @locate="locate"
        />
      </KeepAlive>

      <section v-if="mobileTab === 'stats'" class="card m-panel m-stats">
        <h2>Area statistics</h2>
        <StatusPieChart :counts="counts" />
      </section>

      <MobileTabBar v-model="mobileTab" :badges="{ cameras: urgentCount }" />
    </template>

    <!-- Desktop / tablet -->
    <template v-else>
      <div class="layout">
        <div ref="mapCard" class="card map-card">
          <StoreMap
            :areas-by-camera="areasByCamera"
            :highlighted-ids="highlightedIds"
            :highlighted-camera-ids="highlightedCameraIds"
            :selected-camera-id="selectedCameraId"
            @select="selectedCameraId = $event"
            @clear="clearMapSelection"
          />
          <button v-if="locatedLabel" class="clear-highlight" @click="clearMapSelection">
            Showing {{ locatedLabel }} <span aria-hidden="true">×</span>
          </button>
        </div>

        <section class="card list-card">
          <div class="tabs" role="tablist" aria-label="List by">
            <button role="tab" class="tab" :aria-selected="listTab === 'cameras'" @click="selectTab('cameras')">
              Cameras <span class="tab-count">{{ cameraCount }}</span>
            </button>
            <button role="tab" class="tab" :aria-selected="listTab === 'products'" @click="selectTab('products')">
              Products <span class="tab-count">{{ productCount }}</span>
            </button>
          </div>
          <!-- KeepAlive preserves each list's search/filters when switching tabs. -->
          <KeepAlive>
            <CamerasList v-if="listTab === 'cameras'" :locatable="!canHover" :areas="areas" @highlight="hoverCameras" @locate="locateCameras" />
            <ProductsList v-else :locatable="!canHover" :areas="areas" @highlight="hoverAreas" @locate="locate" />
          </KeepAlive>
        </section>

        <section class="card stats-card">
          <h2>Area statistics</h2>
          <StatusPieChart :counts="counts" />
        </section>
      </div>
    </template>

    <!-- Touch devices: tapping a camera previews it here. -->
    <CameraSheet
      :camera-id="selectedCameraId"
      :areas="areasByCamera[selectedCameraId] ?? []"
      @close="selectedCameraId = null"
    />
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 12px; }
.toolbar h1 { margin: 0; font-size: 1.4rem; margin-right: auto; }
.refresh { display: inline-flex; align-items: center; gap: 6px; }
.filters { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.filters button { display: inline-flex; align-items: center; gap: 6px; }
.layout {
  display: grid;
  /* The tall map takes the width its height needs; the list and stats share the rest. */
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: 1fr auto;
  grid-template-areas:
    'map list'
    'map stats';
  gap: 16px;
  align-items: start;
}
.map-card { grid-area: map; padding: 12px; position: relative; }
.stats-card { grid-area: stats; }
.stats-card h2 { margin: 0 0 12px; font-size: 1.1rem; }
/* The list fills the height left next to the map without stretching it;
   its rows scroll inside. */
.list-card { grid-area: list; align-self: stretch; height: 0; min-height: 100%; display: flex; flex-direction: column; }

.tabs { display: flex; gap: 4px; margin-bottom: 12px; border-bottom: 1px solid var(--border); }
.tab {
  border: none;
  border-radius: 0;
  background: none;
  padding: 6px 12px 8px;
  margin-bottom: -1px;
  font-weight: 600;
  color: var(--muted);
  border-bottom: 2px solid transparent;
}
.tab[aria-selected='true'] { color: var(--text); border-bottom-color: var(--accent); box-shadow: none; }
.tab-count {
  font-size: 0.75rem;
  padding: 0 6px;
  margin-left: 2px;
  border-radius: 999px;
  background: var(--border);
}

/* ---- Phone layout ---- */
.store-page.mobile {
  /* Exactly fills the screen between the app header and the tab bar. */
  height: calc(100dvh - var(--app-header-h) - env(safe-area-inset-top) - var(--tabbar-h) - env(safe-area-inset-bottom) - 24px);
  display: flex;
  flex-direction: column;
}
.mobile .toolbar { flex-wrap: nowrap; margin-bottom: 10px; }
.mobile .toolbar h1 { font-size: 1.15rem; }
.mobile .updated { font-size: 0.8rem; }
.mobile .refresh { width: 44px; justify-content: center; padding: 0; }
.mobile .refresh-label { display: none; }
/* Compact chips that wrap, so all of them are visible without scrolling. */
.mobile .filters { gap: 6px; margin-bottom: 10px; }
.mobile .filters button { padding: 4px 10px; font-size: 0.85rem; min-height: 36px; border-radius: 999px; }

.m-panel { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.m-map-wrap { position: relative; flex: 1; min-height: 0; }
.m-stats { overflow-y: auto; }
.m-stats h2 { margin: 0 0 12px; font-size: 1.1rem; }

.clear-highlight {
  position: absolute;
  top: 10px;
  left: 50%;
  transform: translateX(-50%);
  border-radius: 999px;
  padding: 6px 14px;
  font-size: 0.85rem;
  font-weight: 600;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}

@media (max-width: 1100px) {
  .layout {
    grid-template-columns: 1fr;
    grid-template-rows: auto;
    grid-template-areas: 'map' 'list' 'stats';
  }
  .list-card { height: 560px; min-height: 0; }
}
</style>
