<script setup>
import { ref, computed } from 'vue'
import SearchBox from './SearchBox.vue'
import { AREA_STATUSES, areaStatus, countByStatus } from '../constants/stock.js'
import { matchesSearch } from '../utils/text.js'

const props = defineProps({
  // [{ id, cameraId, productName, compliant, stockLevel }]
  areas: { type: Array, required: true },
  // Show a "Show on map" button per row (phones; on desktop hovering a row highlights it).
  locatable: { type: Boolean, default: false },
})

// `highlight`: camera ids to highlight on the map (empty array to clear).
// `locate`: camera ids the user asked to see on the map.
const emit = defineEmits(['highlight', 'locate'])

const STATUS_ORDER = Object.keys(AREA_STATUSES)
const statusRank = (status) => STATUS_ORDER.indexOf(status)

// One entry per camera, ranked by its most urgent area.
const cameras = computed(() => {
  const byId = new Map()
  for (const area of props.areas) {
    const entry = byId.get(area.cameraId) ?? { id: area.cameraId, areas: [] }
    entry.areas.push({ ...area, status: areaStatus(area) })
    byId.set(area.cameraId, entry)
  }
  return [...byId.values()]
    .map((c) => {
      const worst = c.areas.reduce((w, a) => (statusRank(a.status) < statusRank(w) ? a.status : w), 'full')
      const counts = countByStatus(c.areas)
      return {
        ...c,
        worst,
        products: [...new Set(c.areas.map((a) => a.productName))],
        segments: STATUS_ORDER.filter((key) => counts[key]).map((key) => ({ key, count: counts[key] })),
      }
    })
    .sort((a, b) => statusRank(a.worst) - statusRank(b.worst) || a.id.localeCompare(b.id, undefined, { numeric: true }))
})

const search = ref('')

// Matches camera id, its area ids and its product names.
const filtered = computed(() =>
  cameras.value.filter((c) => matchesSearch(search.value, c.id, ...c.areas.map((a) => a.id), ...c.products)),
)

function highlight(ids) {
  emit('highlight', ids)
}
</script>

<template>
  <div class="cameras-list">
    <SearchBox v-model="search" placeholder="Search camera, area or product" />

    <ul v-if="filtered.length" class="rows">
      <li
        v-for="c in filtered"
        :key="c.id"
        class="row-wrap camera-item"
        @mouseenter="highlight([c.id])"
        @mouseleave="highlight([])"
      >
        <RouterLink
          :to="{ name: 'camera', params: { cameraId: c.id } }"
          class="row camera-row"
          @focus="highlight([c.id])"
          @blur="highlight([])"
        >
          <span class="info">
            <span class="product">Camera {{ c.id }}</span>
            <span class="meta">
              {{ c.areas.length }} {{ c.areas.length === 1 ? 'area' : 'areas' }} ·
              {{ c.products.length }} {{ c.products.length === 1 ? 'product' : 'products' }}
            </span>
            <span class="status-bar" aria-hidden="true">
              <span
                v-for="seg in c.segments"
                :key="seg.key"
                class="segment"
                :style="{ flexGrow: seg.count, background: AREA_STATUSES[seg.key].color }"
                :title="`${seg.count} ${AREA_STATUSES[seg.key].label}`"
              />
            </span>
          </span>
          <span class="chevron" aria-hidden="true">›</span>
        </RouterLink>
        <button v-if="locatable" class="locate" :aria-label="`Show camera ${c.id} on the map`" @click="emit('locate', [c.id])">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" />
            <circle cx="12" cy="9.5" r="2.5" />
          </svg>
        </button>
      </li>
    </ul>
    <p v-else class="empty-state muted">{{ search ? `No cameras match “${search}”.` : 'No cameras.' }}</p>
  </div>
</template>

<style scoped src="../styles/list.css"></style>

<style scoped>
.cameras-list { display: flex; flex-direction: column; min-height: 0; flex: 1; }

/* Camera rows are neutral, like product rows: only the proportion bar shows status colour. */
.camera-row { background: var(--surface); border-left: 1px solid var(--border); }
.camera-row:hover, .camera-row:focus-visible, .camera-item:hover .camera-row {
  background: color-mix(in srgb, var(--accent) 6%, var(--surface));
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
}
.status-bar { display: flex; gap: 2px; height: 5px; margin-top: 6px; border-radius: 3px; overflow: hidden; max-width: 220px; }
.segment { min-width: 4px; }
</style>
