<script setup>
import { ref, computed } from 'vue'
import SearchBox from './SearchBox.vue'
import { AREA_STATUSES, areaStatus, countByStatus } from '../constants/stock.js'
import { matchesSearch } from '../utils/text.js'

const props = defineProps({
  // [{ id, cameraId, productName, compliant, stockLevel }]
  areas: { type: Array, required: true },
  // Show a "Show on map" button per product (phones, where hover isn't available).
  locatable: { type: Boolean, default: false },
})

// `highlight`: area ids to highlight on the map (empty array to clear).
// `locate`: area ids the user asked to see on the map.
const emit = defineEmits(['highlight', 'locate'])

const STATUS_ORDER = Object.keys(AREA_STATUSES)
const statusRank = (status) => STATUS_ORDER.indexOf(status)

// One entry per product (grouped by name, since areas carry no product id),
// ranked by its most urgent area.
const products = computed(() => {
  const byName = new Map()
  for (const area of props.areas) {
    const entry = byName.get(area.productName) ?? { name: area.productName, areas: [] }
    entry.areas.push({ ...area, status: areaStatus(area) })
    byName.set(area.productName, entry)
  }
  return [...byName.values()]
    .map((p) => {
      p.areas.sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }))
      const worst = p.areas.reduce((w, a) => (statusRank(a.status) < statusRank(w) ? a.status : w), 'full')
      const counts = countByStatus(p.areas)
      return {
        ...p,
        ids: p.areas.map((a) => a.id),
        worst,
        segments: STATUS_ORDER.filter((key) => counts[key]).map((key) => ({ key, count: counts[key] })),
        cameras: [...new Set(p.areas.map((a) => a.cameraId))],
      }
    })
    .sort((a, b) => statusRank(a.worst) - statusRank(b.worst) || a.name.localeCompare(b.name))
})

const search = ref('')

// Matches product name, its area ids and its camera ids.
const filtered = computed(() =>
  products.value.filter((p) => matchesSearch(search.value, p.name, ...p.ids, ...p.cameras)),
)

const expanded = ref(new Set())

function toggleExpanded(name) {
  const next = new Set(expanded.value)
  next.has(name) ? next.delete(name) : next.add(name)
  expanded.value = next
}

function highlight(ids) {
  emit('highlight', ids)
}
</script>

<template>
  <div class="products-list">
    <SearchBox v-model="search" placeholder="Search product, area or camera" />

    <ul v-if="filtered.length" class="rows">
      <li
        v-for="p in filtered"
        :key="p.name"
        class="product-item"
        @mouseenter="highlight(p.ids)"
        @mouseleave="highlight([])"
      >
        <div class="row-wrap">
          <button
            class="row product-row"
            :aria-expanded="expanded.has(p.name)"
            @click="toggleExpanded(p.name)"
            @focus="highlight(p.ids)"
            @blur="highlight([])"
          >
            <span class="info">
              <span class="product">{{ p.name }}</span>
              <span class="meta">
                {{ p.areas.length }} {{ p.areas.length === 1 ? 'area' : 'areas' }} ·
                {{ p.cameras.length === 1 ? 'Camera' : 'Cameras' }} {{ p.cameras.join(', ') }}
              </span>
              <span class="status-bar" aria-hidden="true">
                <span
                  v-for="seg in p.segments"
                  :key="seg.key"
                  class="segment"
                  :style="{ flexGrow: seg.count, background: AREA_STATUSES[seg.key].color }"
                  :title="`${seg.count} ${AREA_STATUSES[seg.key].label}`"
                />
              </span>
            </span>
            <span class="chevron expand" aria-hidden="true">›</span>
          </button>
          <button v-if="locatable" class="locate" aria-label="Show on map" @click="emit('locate', p.ids)">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true">
              <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" />
              <circle cx="12" cy="9.5" r="2.5" />
            </svg>
          </button>
        </div>

        <div v-if="expanded.has(p.name)" class="product-areas">
          <RouterLink
            v-for="a in p.areas"
            :key="a.id"
            :to="{ name: 'area', params: { areaId: a.id } }"
            class="area-chip"
            :style="{ '--status-color': AREA_STATUSES[a.status].color }"
            @mouseenter="highlight([a.id])"
            @mouseleave="highlight(p.ids)"
            @focus="highlight([a.id])"
            @blur="highlight([])"
          >
            <span class="chip-dot" />
            {{ a.id }}
            <span class="muted">{{ AREA_STATUSES[a.status].label }}</span>
          </RouterLink>
        </div>
      </li>
    </ul>
    <p v-else class="empty-state muted">{{ search ? `No products match “${search}”.` : 'No products.' }}</p>
  </div>
</template>

<style scoped src="../styles/list.css"></style>

<style scoped>
.products-list { display: flex; flex-direction: column; min-height: 0; flex: 1; }

/* Product rows are neutral: only the proportion bar (and each area's chip) shows status colour. */
.product-row {
  width: 100%;
  font: inherit;
  text-align: left;
  background: var(--surface);
  cursor: pointer;
  border-left: 1px solid var(--border);
}
.product-row:hover, .product-row:focus-visible, .product-item:hover .product-row {
  background: color-mix(in srgb, var(--accent) 6%, var(--surface));
  border-color: color-mix(in srgb, var(--accent) 40%, var(--border));
}
.expand { transition: transform 0.15s; }
.product-row[aria-expanded='true'] .expand { transform: rotate(90deg); }
.status-bar { display: flex; gap: 2px; height: 5px; margin-top: 6px; border-radius: 3px; overflow: hidden; max-width: 220px; }
.segment { min-width: 4px; }

.product-areas { display: flex; flex-wrap: wrap; gap: 6px; padding: 8px 0 4px 16px; }
.area-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  font-size: 0.8rem;
  color: var(--text);
  text-decoration: none;
}
.chip-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--status-color); }
.area-chip:hover, .area-chip:focus-visible {
  outline: none;
  border-color: var(--status-color);
  background: color-mix(in srgb, var(--status-color) 10%, var(--surface));
}
</style>
