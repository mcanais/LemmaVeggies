<script setup>
import { computed } from 'vue'
import { AREA_STATUSES, UNKNOWN_COLOR, areaStatus, countByStatus } from '../constants/stock.js'
import { TILE, BLOCK } from '../constants/storeLayout.js'

const props = defineProps({
  cameraId: { type: String, required: true },
  areas: { type: Array, required: true },
  box: { type: Object, required: true },
  isDimmed: { type: Function, default: () => false },
  // Area ids highlighted from outside the map (e.g. hovering the areas list).
  highlightedIds: { type: Array, default: () => [] },
  // The camera tapped on the map (touch), outlined as a whole.
  selected: { type: Boolean, default: false },
  // Camera located from outside the map (cameras list, CameraPage): pulsing ring.
  highlighted: { type: Boolean, default: false },
  // Another camera is highlighted, so this one steps back.
  faded: { type: Boolean, default: false },
})

// The whole camera is one target: `activate` fires on click/tap/Enter and the
// map decides whether that navigates (desktop) or opens the camera sheet (touch).
const emit = defineEmits(['hover', 'leave', 'activate'])

const PAD = BLOCK.pad

// Every tile is the same size; areas fill the block row by row.
const cells = computed(() =>
  props.areas.map((area, i) => ({
    area,
    x: props.box.x + PAD + (i % TILE.cols) * (TILE.size + TILE.gap),
    y: props.box.y + BLOCK.header + Math.floor(i / TILE.cols) * (TILE.size + TILE.gap),
    w: TILE.size,
    h: TILE.size,
  })),
)

const highlightedSet = computed(() => new Set(props.highlightedIds))
const highlightedCells = computed(() => cells.value.filter((c) => highlightedSet.value.has(c.area.id)))

// Wrong-product areas are purple; the others are coloured by stock level.
function cellColor(area) {
  return AREA_STATUSES[areaStatus(area)]?.color ?? UNKNOWN_COLOR
}

const ariaLabel = computed(() => {
  const counts = countByStatus(props.areas)
  const parts = Object.entries(AREA_STATUSES)
    .filter(([key]) => counts[key])
    .map(([key, s]) => `${counts[key]} ${s.label.toLowerCase()}`)
  return `Camera ${props.cameraId}: ${parts.join(', ')}`
})
</script>

<template>
  <g
    class="camera-block"
    :class="{ selected, faded }"
    role="link"
    tabindex="0"
    :aria-label="ariaLabel"
    @click.stop="emit('activate', cameraId)"
    @keydown.enter="emit('activate', cameraId)"
    @mouseenter="emit('hover', cameraId, $event.currentTarget)"
    @focus="emit('hover', cameraId, $event.currentTarget)"
    @mouseleave="emit('leave')"
    @blur="emit('leave')"
  >
    <rect :data-camera-id="cameraId" :x="box.x" :y="box.y" :width="box.width" :height="box.height" rx="6" class="gondola" />
    <text :x="box.x + PAD" :y="box.y + 14" class="camera-label">{{ cameraId }}</text>
    <g
      v-for="cell in cells"
      :key="cell.area.id"
      class="cell"
      :class="{
        dimmed: isDimmed(cell.area) && !highlightedSet.has(cell.area.id),
        faded: highlightedSet.size > 0 && !highlightedSet.has(cell.area.id),
      }"
    >
      <rect
        :data-area-id="cell.area.id"
        :x="cell.x"
        :y="cell.y"
        :width="cell.w"
        :height="cell.h"
        rx="3"
        :fill="cellColor(cell.area)"
        :class="{ noncompliant: !cell.area.compliant }"
      />
      <text
        v-if="!cell.area.compliant"
        :x="cell.x + cell.w / 2"
        :y="cell.y + cell.h / 2"
        class="warn"
        text-anchor="middle"
        dominant-baseline="central"
      >✕</text>
    </g>
    <!-- Drawn after all cells so the rings aren't covered by neighbouring cells. -->
    <rect
      v-for="cell in highlightedCells"
      :key="cell.area.id"
      :x="cell.x - 3"
      :y="cell.y - 3"
      :width="cell.w + 6"
      :height="cell.h + 6"
      rx="5"
      class="highlight-ring"
    />
    <rect
      v-if="highlighted"
      :x="box.x - 4"
      :y="box.y - 4"
      :width="box.width + 8"
      :height="box.height + 8"
      rx="9"
      class="highlight-ring"
    />
  </g>
</template>

<style scoped>
.camera-block { cursor: pointer; outline: none; transition: opacity 0.15s; }
.camera-block.faded { opacity: 0.4; }
.gondola { fill: var(--surface); stroke: var(--border); stroke-width: 1.5; transition: stroke 0.15s; }
.camera-block:hover .gondola, .camera-block:focus-visible .gondola { stroke: var(--text); stroke-width: 2.5; }
.camera-block.selected .gondola { stroke: var(--accent); stroke-width: 3; }
.camera-label { font-size: 12px; font-weight: 600; fill: var(--muted); }
.cell { transition: opacity 0.15s; }
.cell rect { stroke: rgba(0, 0, 0, 0.15); stroke-width: 1; }
.cell rect.noncompliant { stroke: #1c2024; stroke-width: 2; stroke-dasharray: 4 2; }
.cell.dimmed { opacity: 0.15; }
.cell.faded:not(.dimmed) { opacity: 0.45; }
.highlight-ring {
  fill: none;
  stroke: var(--text);
  stroke-width: 3;
  pointer-events: none;
  animation: pulse 1.2s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { stroke-opacity: 1; }
  50% { stroke-opacity: 0.35; }
}
.warn { font-size: 30px; font-weight: 800; fill: #fff; pointer-events: none; paint-order: stroke; stroke: rgba(0, 0, 0, 0.35); stroke-width: 2px; }
</style>
