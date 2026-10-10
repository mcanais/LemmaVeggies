<script setup>
import { ref, computed } from 'vue'
import SearchBox from './SearchBox.vue'
import { AREA_STATUSES, areaStatus, countByStatus } from '../constants/stock.js'
import { matchesSearch } from '../utils/text.js'

const props = defineProps({
  // [{ id, cameraId, productName, compliant, stockLevel }]
  areas: { type: Array, required: true },
  // Show a "Show on map" button per row (phones, where hover isn't available).
  locatable: { type: Boolean, default: false },
})

// `highlight`: area ids to highlight on the map (empty array to clear).
// `locate`: area ids the user asked to see on the map.
const emit = defineEmits(['highlight', 'locate'])

const STATUS_ORDER = Object.keys(AREA_STATUSES)

// Each chip toggles one status on or off.
const selected = ref(new Set(STATUS_ORDER))

function toggle(key) {
  const next = new Set(selected.value)
  next.has(key) ? next.delete(key) : next.add(key)
  selected.value = next
}

const search = ref('')

// Matches product name, area id and camera id.
const searched = computed(() =>
  props.areas.filter((a) => matchesSearch(search.value, a.productName, a.id, a.cameraId)),
)

// Chip counts follow the search, so they always match what the list can show.
const counts = computed(() => countByStatus(searched.value))

const rows = computed(() =>
  searched.value
    .map((area) => ({ ...area, status: areaStatus(area) }))
    .filter((a) => selected.value.has(a.status))
    .sort(
      (a, b) =>
        STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status) ||
        a.productName.localeCompare(b.productName) ||
        a.id.localeCompare(b.id, undefined, { numeric: true }),
    ),
)

function highlight(ids) {
  emit('highlight', ids)
}
</script>

<template>
  <div class="areas-list">
    <SearchBox v-model="search" placeholder="Search product, area or camera" />

    <div class="chips" role="group" aria-label="Filter by status">
      <button
        v-for="(s, key) in AREA_STATUSES"
        :key="key"
        class="chip"
        :aria-pressed="selected.has(key)"
        :style="{ '--chip-color': s.color }"
        @click="toggle(key)"
      >
        <span class="chip-dot" />
        {{ s.label }}
        <span class="chip-count">{{ counts[key] }}</span>
      </button>
    </div>

    <ul v-if="rows.length" class="rows">
      <li v-for="a in rows" :key="a.id" class="row-wrap">
        <RouterLink
          :to="{ name: 'area', params: { areaId: a.id } }"
          class="row"
          :style="{ '--status-color': AREA_STATUSES[a.status].color }"
          @mouseenter="highlight([a.id])"
          @mouseleave="highlight([])"
          @focus="highlight([a.id])"
          @blur="highlight([])"
        >
          <span class="status-icon" aria-hidden="true">{{ AREA_STATUSES[a.status].icon }}</span>
          <span class="info">
            <span class="product">{{ a.productName }}</span>
            <span class="meta">Area {{ a.id }} · Camera {{ a.cameraId }}</span>
          </span>
          <span class="status-pill">{{ AREA_STATUSES[a.status].label }}</span>
          <span class="chevron" aria-hidden="true">›</span>
        </RouterLink>
        <button v-if="locatable" class="locate" aria-label="Show on map" @click="emit('locate', [a.id])">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true">
            <path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" />
            <circle cx="12" cy="9.5" r="2.5" />
          </svg>
        </button>
      </li>
    </ul>
    <p v-else class="empty-state muted">
      {{
        !selected.size
          ? 'Select a status to see its areas.'
          : search
            ? `No areas match “${search}”.`
            : 'No areas match the selected filters.'
      }}
    </p>
  </div>
</template>

<style scoped src="../styles/list.css"></style>

<style scoped>
.areas-list { display: flex; flex-direction: column; min-height: 0; flex: 1; }

.chips { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
@media (max-width: 768px) {
  /* One scrollable line of chips instead of wrapping onto several. */
  .chips { flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; margin: 0 -12px 12px; padding: 0 12px; }
  .chip { flex-shrink: 0; }
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 0.875rem;
  opacity: 0.6;
  transition: opacity 0.15s, background 0.15s;
}
.chip[aria-pressed='true'] {
  opacity: 1;
  border-color: var(--chip-color);
  box-shadow: none;
  background: color-mix(in srgb, var(--chip-color) 12%, var(--surface));
}
.chip-dot { width: 9px; height: 9px; border-radius: 50%; background: var(--chip-color); }
.chip-count {
  font-weight: 700;
  font-size: 0.8rem;
  padding: 0 6px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--chip-color) 20%, transparent);
}

.status-pill {
  flex-shrink: 0;
  font-size: 0.78rem;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 999px;
  color: color-mix(in srgb, var(--status-color) 70%, var(--text));
  background: color-mix(in srgb, var(--status-color) 14%, transparent);
}

@media (max-width: 480px) {
  .status-pill { display: none; }
}
</style>
