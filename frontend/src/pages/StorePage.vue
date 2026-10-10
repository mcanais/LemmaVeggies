<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import StoreMap from '../components/StoreMap.vue'
import StatusPieChart from '../components/StatusPieChart.vue'
import AreasList from '../components/AreasList.vue'
import ProductsList from '../components/ProductsList.vue'
import MobileTabBar from '../components/MobileTabBar.vue'
import AreaSheet from '../components/AreaSheet.vue'
import { getAreas } from '../api/areas.js'
import { AREA_STATUSES, areaStatus, countByStatus } from '../constants/stock.js'
import { useIsMobile } from '../composables/useMediaQuery.js'

const REFRESH_MS = 60_000

const areas = ref([])
const error = ref(null)
const loading = ref(true)
const lastUpdated = ref(null)
const filter = ref(null) // null | 'wrong' | 'empty' | 'half' | 'full'
const highlightedIds = ref([]) // areas hovered in the list, shown on the map
const listTab = ref('areas') // 'areas' | 'products'

const isMobile = useIsMobile()
const mobileTab = ref('map') // 'map' | 'areas' | 'products' | 'stats'
const selectedId = ref(null) // area tapped on the map (touch), shown in the sheet
const map = ref(null)

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

const productCount = computed(() => new Set(areas.value.map((a) => a.productName)).size)

function selectTab(tab) {
  listTab.value = tab
  highlightedIds.value = []
}

const selectedArea = computed(() => areas.value.find((a) => a.id === selectedId.value) ?? null)

// The tapped area is ringed on the map too.
const mapHighlights = computed(() =>
  selectedId.value && !highlightedIds.value.includes(selectedId.value)
    ? [...highlightedIds.value, selectedId.value]
    : highlightedIds.value,
)

// Areas needing action now, shown as a badge on the Areas tab.
const urgentCount = computed(() => counts.value.wrong + counts.value.empty)

// "Show on map" from a list: jump to the map and centre on those areas.
async function locate(ids) {
  highlightedIds.value = ids
  selectedId.value = ids.length === 1 ? ids[0] : null
  mobileTab.value = 'map'
  await nextTick()
  map.value?.focusAreas(ids)
}

function clearMapSelection() {
  selectedId.value = null
  highlightedIds.value = []
}

// Leaving the map closes the sheet; highlights from the lists only make sense on the map.
watch(mobileTab, (tab) => {
  if (tab !== 'map') selectedId.value = null
})
watch(isMobile, () => clearMapSelection())

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
            :highlighted-ids="mapHighlights"
            @select="selectedId = $event.id"
            @clear="clearMapSelection"
          />
          <button v-if="highlightedIds.length > 1" class="clear-highlight" @click="clearMapSelection">
            Showing {{ highlightedIds.length }} areas <span aria-hidden="true">×</span>
          </button>
        </div>
      </div>

      <KeepAlive>
        <AreasList
          v-if="mobileTab === 'areas'"
          class="card m-panel"
          locatable
          :areas="areas"
          @locate="locate"
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

      <MobileTabBar v-model="mobileTab" :badges="{ areas: urgentCount }" />
    </template>

    <!-- Desktop / tablet -->
    <template v-else>
      <div class="filters" role="group" aria-label="Filter areas">
        <button v-for="f in filters" :key="f.key" :aria-pressed="filter === f.key" @click="toggle(f.key)">
          <span class="dot" :style="{ background: f.color }" />
          {{ f.label }} <strong>{{ f.count }}</strong>
        </button>
      </div>

      <div class="layout">
        <div class="card map-card">
          <StoreMap
            :areas-by-camera="areasByCamera"
            :is-dimmed="isDimmed"
            :highlighted-ids="mapHighlights"
            @select="selectedId = $event.id"
            @clear="selectedId = null"
          />
        </div>

        <section class="card list-card">
          <div class="tabs" role="tablist" aria-label="List by">
            <button role="tab" class="tab" :aria-selected="listTab === 'areas'" @click="selectTab('areas')">
              Areas <span class="tab-count">{{ areas.length }}</span>
            </button>
            <button role="tab" class="tab" :aria-selected="listTab === 'products'" @click="selectTab('products')">
              Products <span class="tab-count">{{ productCount }}</span>
            </button>
          </div>
          <!-- KeepAlive preserves each list's filters/expanded rows when switching tabs. -->
          <KeepAlive>
            <AreasList v-if="listTab === 'areas'" :areas="areas" @highlight="highlightedIds = $event" />
            <ProductsList v-else :areas="areas" @highlight="highlightedIds = $event" />
          </KeepAlive>
        </section>

        <section class="card stats-card">
          <h2>Area statistics</h2>
          <StatusPieChart :counts="counts" />
        </section>
      </div>
    </template>

    <!-- Touch devices: tapping a tile previews the area here. -->
    <AreaSheet :area="selectedArea" @close="selectedId = null" />
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
  /* The map gets most of the width; the list keeps a readable column. */
  grid-template-columns: minmax(0, 1fr) clamp(340px, 24vw, 460px);
  grid-template-areas:
    'map list'
    'stats list';
  gap: 16px;
  align-items: start;
}
.map-card { grid-area: map; padding: 12px; }
.stats-card { grid-area: stats; }
.stats-card h2 { margin: 0 0 12px; font-size: 1.1rem; }
/* The list fills the height of the map + stats column without stretching it;
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
.mobile .filters {
  flex-wrap: nowrap;
  overflow-x: auto;
  scrollbar-width: none;
  margin: 0 -12px 10px;
  padding: 0 12px;
}
.mobile .filters button { flex-shrink: 0; }

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
    grid-template-areas: 'map' 'list' 'stats';
  }
  .list-card { height: 560px; min-height: 0; }
}
</style>
