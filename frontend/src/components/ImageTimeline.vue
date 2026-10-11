<script setup>
import { ref, computed } from 'vue'
import { UNKNOWN_COLOR } from '../constants/stock.js'
import { imageTimestamp, formatTime } from '../utils/time.js'
import { useMediaQuery } from '../composables/useMediaQuery.js'

const props = defineProps({
  // Image ids of the camera, any order.
  images: { type: Array, required: true },
  // (timestamp) => colour of the image mark at that moment.
  markColor: { type: Function, default: () => UNKNOWN_COLOR },
})

// Selected image id; null means "latest".
const model = defineModel({ type: String, default: null })

const HOUR = 3600
const narrow = useMediaQuery('(max-width: 400px)')

const items = computed(() =>
  props.images
    .map((id) => ({ id, ts: imageTimestamp(id) }))
    .filter((i) => i.ts !== null)
    .sort((a, b) => a.ts - b.ts),
)

const min = computed(() => items.value[0]?.ts ?? 0)
const max = computed(() => items.value.at(-1)?.ts ?? 0)
const span = computed(() => max.value - min.value)

function position(ts) {
  return span.value ? ((ts - min.value) / span.value) * 100 : 50
}

const selectedIndex = computed(() => {
  const i = model.value ? items.value.findIndex((item) => item.id === model.value) : -1
  return i >= 0 ? i : items.value.length - 1
})
const selected = computed(() => items.value[selectedIndex.value])
const isLatest = computed(() => selectedIndex.value === items.value.length - 1)

// Hour labels along the axis; every 2 hours on long ranges to avoid crowding.
const ticks = computed(() => {
  if (!span.value) return []
  const step = narrow.value ? 3 * HOUR : span.value > 12 * HOUR ? 2 * HOUR : HOUR
  const out = []
  for (let t = Math.ceil(min.value / step) * step; t <= max.value; t += step) {
    out.push({ ts: t, left: position(t), label: formatTime(t) })
  }
  return out
})

function select(index) {
  const i = Math.max(0, Math.min(items.value.length - 1, index))
  if (items.value[i]) model.value = items.value[i].id
}

// --- Dragging: the whole track is the hit area and snaps to the nearest image.
const track = ref(null)
const dragging = ref(false)

function seek(clientX) {
  const rect = track.value.getBoundingClientRect()
  const frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
  const target = min.value + frac * span.value
  let nearest = 0
  items.value.forEach((item, i) => {
    if (Math.abs(item.ts - target) < Math.abs(items.value[nearest].ts - target)) nearest = i
  })
  if (nearest !== selectedIndex.value || !model.value) select(nearest)
}

function onPointerDown(e) {
  if (!items.value.length) return
  dragging.value = true
  track.value.setPointerCapture(e.pointerId)
  seek(e.clientX)
}

function onPointerMove(e) {
  if (dragging.value) seek(e.clientX)
}

function onPointerUp() {
  dragging.value = false
}

function onKeydown(e) {
  const moves = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1 }
  if (e.key in moves) select(selectedIndex.value + moves[e.key])
  else if (e.key === 'Home') select(0)
  else if (e.key === 'End') select(items.value.length - 1)
  else return
  e.preventDefault()
}
</script>

<template>
  <div class="timeline">
    <p v-if="!items.length" class="muted empty">No images in this time range.</p>

    <template v-else>
      <div class="controls">
        <button class="nav" :disabled="selectedIndex === 0" aria-label="Previous image" @click="select(selectedIndex - 1)">‹</button>
        <div class="current">
          <strong>{{ formatTime(selected.ts) }}</strong>
          <span class="muted">{{ selectedIndex + 1 }} / {{ items.length }}</span>
        </div>
        <button class="nav" :disabled="isLatest" aria-label="Next image" @click="select(selectedIndex + 1)">›</button>
      </div>

      <div class="track-wrap">
        <div
          ref="track"
          class="track"
          :class="{ dragging }"
          @pointerdown="onPointerDown"
          @pointermove="onPointerMove"
          @pointerup="onPointerUp"
          @pointercancel="onPointerUp"
        >
          <div class="rail" />
          <div class="progress" :style="{ width: `${position(selected.ts)}%` }" />
          <span
            v-for="(item, i) in items"
            :key="item.id"
            class="mark"
            :class="{ active: i === selectedIndex }"
            :style="{ left: `${position(item.ts)}%`, background: markColor(item.ts) }"
          />
          <div
            class="handle"
            :style="{ left: `${position(selected.ts)}%`, '--handle-color': markColor(selected.ts) }"
            role="slider"
            tabindex="0"
            aria-label="Image time"
            :aria-valuemin="0"
            :aria-valuemax="items.length - 1"
            :aria-valuenow="selectedIndex"
            :aria-valuetext="formatTime(selected.ts)"
            @keydown="onKeydown"
          />
        </div>

        <div class="axis" aria-hidden="true">
          <span v-for="t in ticks" :key="t.ts" class="tick" :style="{ left: `${t.left}%` }">{{ t.label }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.timeline { margin-top: 14px; }
.empty { margin: 0; font-size: 0.9rem; }

.controls { display: flex; align-items: center; gap: 8px; margin-bottom: 30px; }
.nav { width: 32px; height: 32px; padding: 0; font-size: 1.2rem; line-height: 1; border-radius: 50%; }
.nav:disabled { opacity: 0.35; cursor: default; }
.current { display: flex; align-items: baseline; gap: 8px; min-width: 110px; justify-content: center; }
.current strong { font-variant-numeric: tabular-nums; }
.current .muted { font-size: 0.8rem; }

.track-wrap { padding: 0 14px; }
.track {
  position: relative;
  height: 28px;
  cursor: pointer;
  touch-action: none;
  user-select: none;
}
.track.dragging { cursor: grabbing; }
.rail, .progress {
  position: absolute;
  top: 50%;
  height: 6px;
  margin-top: -3px;
  border-radius: 3px;
}
.rail { left: 0; right: 0; background: var(--border); }
.progress { left: 0; background: color-mix(in srgb, var(--accent) 45%, transparent); }

.mark {
  position: absolute;
  top: 50%;
  width: 10px;
  height: 10px;
  margin: -5px 0 0 -5px;
  border-radius: 50%;
  border: 2px solid var(--surface);
  transition: transform 0.15s;
}
.mark.active { transform: scale(1.3); }

.handle {
  position: absolute;
  top: 50%;
  width: 20px;
  height: 20px;
  margin: -10px 0 0 -10px;
  border-radius: 50%;
  background: var(--surface);
  border: 3px solid var(--handle-color, var(--accent));
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
  cursor: grab;
  outline: none;
  transition: transform 0.1s;
}
.track.dragging .handle { cursor: grabbing; transform: scale(1.15); }
.handle:focus-visible { box-shadow: 0 0 0 4px color-mix(in srgb, var(--handle-color, var(--accent)) 35%, transparent); }

.axis { position: relative; height: 22px; margin-top: 4px; }
.tick {
  position: absolute;
  top: 0;
  transform: translateX(-50%);
  font-size: 0.72rem;
  color: var(--muted);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.tick::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 50%;
  width: 1px;
  height: 4px;
  background: var(--muted);
  opacity: 0.6;
}

/* Bigger, thumb-friendly controls on touch screens. */
@media (pointer: coarse) {
  .nav { width: 44px; height: 44px; min-height: 44px; }
  .track { height: 44px; }
  .handle { width: 28px; height: 28px; margin: -14px 0 0 -14px; }
  .mark { width: 12px; height: 12px; margin: -6px 0 0 -6px; }
}
</style>
