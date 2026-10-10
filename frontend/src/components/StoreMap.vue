<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import Panzoom from '@panzoom/panzoom'
import CameraBlock from './CameraBlock.vue'
import { computeLayout } from '../constants/storeLayout.js'
import { AREA_STATUSES, UNKNOWN_COLOR, areaStatus } from '../constants/stock.js'
import { useCanHover } from '../composables/useMediaQuery.js'

const props = defineProps({
  // { [cameraId]: [area] }
  areasByCamera: { type: Object, required: true },
  isDimmed: { type: Function, default: () => false },
  highlightedIds: { type: Array, default: () => [] },
  // Phone mode: the map fills its parent's height and can be pinch-zoomed and panned.
  zoomable: { type: Boolean, default: false },
})

// On touch devices a tap selects an area (`select`) instead of navigating;
// tapping the empty floor emits `clear`.
const emit = defineEmits(['select', 'clear'])

const router = useRouter()
const canHover = useCanHover()

const layout = computed(() =>
  computeLayout(Object.fromEntries(Object.entries(props.areasByCamera).map(([id, areas]) => [id, areas.length]))),
)

const blocks = computed(() =>
  layout.value.blocks.map((b) => ({ ...b, areas: props.areasByCamera[b.cameraId] })),
)

const container = ref(null)
const viewport = ref(null)
const target = ref(null)
const svg = ref(null)

// --- Tooltip (hover devices only)
const tooltip = ref(null) // { area, x, y, align }

// Anchor the tooltip above the hovered cell, relative to the map container.
function showTooltip(area, el) {
  if (!canHover.value) return
  const c = container.value.getBoundingClientRect()
  const r = el.getBoundingClientRect()
  const x = r.left + r.width / 2 - c.left
  // Near the sides, align the tooltip to the cell's edge so it stays inside the map.
  const align = x < c.width * 0.15 ? 'left' : x > c.width * 0.85 ? 'right' : 'center'
  tooltip.value = { area, x: align === 'left' ? r.left - c.left : align === 'right' ? r.right - c.left : x, y: r.top - c.top, align }
}

function hideTooltip() {
  tooltip.value = null
}

// --- Tap vs drag: a pointer that moved more than this isn't a tap.
const TAP_SLOP = 6
let downAt = null
let dragged = false

function onPointerDown(e) {
  downAt = { x: e.clientX, y: e.clientY }
  dragged = false
}

function onPointerMove(e) {
  if (downAt && Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > TAP_SLOP) dragged = true
}

function onActivate(area) {
  if (dragged) return
  if (canHover.value) router.push({ name: 'area', params: { areaId: area.id } })
  else emit('select', area)
}

function onBackgroundClick() {
  if (!dragged) emit('clear')
}

// --- Pinch-zoom / pan (zoomable mode)
let panzoom = null

function initPanzoom() {
  if (panzoom || !target.value) return
  panzoom = Panzoom(target.value, { minScale: 1, maxScale: 6, step: 0.4, contain: 'outside', cursor: 'grab' })
  viewport.value.addEventListener('wheel', panzoom.zoomWithWheel)
}

function destroyPanzoom() {
  if (!panzoom) return
  viewport.value?.removeEventListener('wheel', panzoom.zoomWithWheel)
  panzoom.reset({ animate: false })
  panzoom.destroy()
  panzoom = null
}

onMounted(() => props.zoomable && initPanzoom())
onBeforeUnmount(destroyPanzoom)
watch(
  () => props.zoomable,
  async (on) => {
    await nextTick()
    on ? initPanzoom() : destroyPanzoom()
  },
)

const zoomIn = () => panzoom?.zoomIn()
const zoomOut = () => panzoom?.zoomOut()
const resetZoom = () => panzoom?.reset()

// Zoom and pan so the given areas are centred on screen.
function focusAreas(ids) {
  if (!panzoom || !ids.length) return
  const rects = ids
    .map((id) => svg.value.querySelector(`[data-area-id="${CSS.escape(id)}"]`))
    .filter(Boolean)
    .map((el) => el.getBBox())
  if (!rects.length) return

  const x1 = Math.min(...rects.map((r) => r.x))
  const y1 = Math.min(...rects.map((r) => r.y))
  const x2 = Math.max(...rects.map((r) => r.x + r.width))
  const y2 = Math.max(...rects.map((r) => r.y + r.height))

  // SVG units → px inside the (unscaled) target; the SVG is letterboxed ("meet").
  const W = target.value.offsetWidth
  const H = target.value.offsetHeight
  const k = Math.min(W / layout.value.width, H / layout.value.height)
  const ox = (W - layout.value.width * k) / 2
  const oy = (H - layout.value.height * k) / 2
  const cx = ox + ((x1 + x2) / 2) * k
  const cy = oy + ((y1 + y2) / 2) * k

  const MARGIN = 80
  const scale = Math.max(1, Math.min(4, W / ((x2 - x1) * k + MARGIN), H / ((y2 - y1) * k + MARGIN)))

  // Panzoom's transform is scale(s) translate(x, y) around the centre, so
  // translating by (centre - point) puts that point in the middle.
  panzoom.zoom(scale, { animate: false })
  setTimeout(() => panzoom?.pan(W / 2 - cx, H / 2 - cy, { animate: true }))
}

defineExpose({ focusAreas, resetZoom })
</script>

<template>
  <div ref="container" class="map-container" :class="{ zoomable }">
    <div
      ref="viewport"
      class="map-viewport"
      @scroll="hideTooltip"
      @pointerdown.capture="onPointerDown"
      @pointermove.capture="onPointerMove"
    >
      <div ref="target" class="map-target">
        <svg
          ref="svg"
          :viewBox="`0 0 ${layout.width} ${layout.height}`"
          preserveAspectRatio="xMidYMid meet"
          class="store-map"
          role="img"
          aria-label="Store floor plan"
          @click="onBackgroundClick"
        >
          <rect x="0" y="0" :width="layout.width" :height="layout.height" rx="12" class="floor" />
          <template v-if="layout.entrance">
            <rect v-bind="layout.entrance" class="entrance" />
            <text
              :x="layout.entrance.x + layout.entrance.width / 2"
              :y="layout.entrance.y - 8"
              text-anchor="middle"
              class="floor-label"
            >Entrance</text>
          </template>
          <CameraBlock
            v-for="b in blocks"
            :key="b.cameraId"
            v-bind="b"
            :is-dimmed="isDimmed"
            :highlighted-ids="highlightedIds"
            @hover="showTooltip"
            @leave="hideTooltip"
            @activate="onActivate"
          />
        </svg>
      </div>
    </div>

    <div v-if="zoomable" class="zoom-controls">
      <button aria-label="Zoom in" @click="zoomIn">+</button>
      <button aria-label="Zoom out" @click="zoomOut">−</button>
      <button aria-label="Reset zoom" @click="resetZoom">⤢</button>
    </div>

    <div
      v-if="tooltip"
      class="tooltip"
      :class="`align-${tooltip.align}`"
      :style="{ left: `${tooltip.x}px`, top: `${tooltip.y}px` }"
      role="tooltip"
    >
      <strong class="product">{{ tooltip.area.productName }}</strong>
	  <span v-if="!tooltip.area.compliant" class="warn">⚠ Wrong product</span>
      <span class="details">
        <span class="dot" :style="{ background: AREA_STATUSES[areaStatus(tooltip.area)]?.color ?? UNKNOWN_COLOR }" />
        {{ tooltip.area.id }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.map-container { position: relative; }
.map-viewport { overflow-x: auto; }
/* Below this width tiles get too small to read, so the map scrolls instead. */
.store-map { display: block; width: 100%; min-width: 900px; height: auto; }

/* Zoomable (phone) mode: fill the parent; Panzoom moves .map-target inside a clipped viewport. */
.map-container.zoomable { height: 100%; }
.zoomable .map-viewport {
  height: 100%;
  overflow: hidden;
  border-radius: 10px;
  background: var(--floor);
  touch-action: none;
}
.zoomable .map-target { width: 100%; height: 100%; }
.zoomable .store-map { min-width: 0; height: 100%; }

.zoom-controls {
  position: absolute;
  right: 10px;
  bottom: 10px;
  display: flex;
  flex-direction: column;
  border-radius: 10px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
}
.zoom-controls button {
  width: 44px;
  height: 44px;
  padding: 0;
  border: none;
  border-radius: 0;
  font-size: 1.3rem;
  line-height: 1;
}
.zoom-controls button + button { border-top: 1px solid var(--border); }
.floor { fill: var(--floor); stroke: var(--border); stroke-width: 2; }
.entrance { fill: var(--accent); opacity: 0.6; }
.floor-label { font-size: 13px; fill: var(--muted); }

.tooltip {
  position: absolute;
  z-index: 10;
  display: flex;
  flex-direction: column;
  gap: 2px;
  max-width: 260px;
  padding: 6px 10px;
  margin-top: -8px;
  border-radius: 6px;
  background: #1c2024;
  color: #fff;
  font-size: 0.85rem;
  line-height: 1.3;
  pointer-events: none;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}
.tooltip.align-center { transform: translate(-50%, -100%); }
.tooltip.align-left { transform: translate(0, -100%); }
.tooltip.align-right { transform: translate(-100%, -100%); }
.product { font-weight: 600; }
.details { display: inline-flex; align-items: center; gap: 6px; color: #c9ccd1; }
.warn { color: #ffd166; }
</style>
