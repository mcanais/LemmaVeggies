<script setup>
import { ref, computed, watch, useId } from 'vue'

const props = defineProps({
  src: { type: String, required: true },
  // { top_left, top_right, bottom_right, bottom_left } as [x, y] pixels; may be negative.
  polygon: { type: Object, default: null },
  alt: { type: String, default: 'Camera image' },
  // Overview mode, instead of `polygon`: every area outlined in its own colour.
  // [{ id, polygon, color, label }]
  areas: { type: Array, default: null },
  // Area id drawn thicker (e.g. hovered in a list).
  highlightedId: { type: String, default: null },
})

// `select`: an area polygon was clicked (overview mode). `hover`: area id or null.
const emit = defineEmits(['select', 'hover'])

// Unique per instance so several images on a page don't share a mask.
const maskId = `area-mask-${useId()}`

const size = ref(null)
const failed = ref(false)

watch(() => props.src, () => (failed.value = false))

function onLoad(e) {
  size.value = { width: e.target.naturalWidth, height: e.target.naturalHeight }
}

function toPoints(p) {
  return [p.top_left, p.top_right, p.bottom_right, p.bottom_left].map(([x, y]) => `${x},${y}`).join(' ')
}

const points = computed(() => (props.polygon ? toPoints(props.polygon) : null))

const shapes = computed(() =>
  (props.areas ?? []).filter((a) => a.polygon).map((a) => ({ ...a, points: toPoints(a.polygon) })),
)
</script>

<template>
  <div class="camera-image">
    <p v-if="failed" class="muted placeholder">Image unavailable</p>
    <template v-else>
      <img :src="src" :alt="alt" @load="onLoad" @error="failed = true" />
      <svg
        v-if="size && areas"
        :viewBox="`0 0 ${size.width} ${size.height}`"
        preserveAspectRatio="none"
        class="overlay overview"
      >
        <g
          v-for="a in shapes"
          :key="a.id"
          class="area"
          :class="{ active: a.id === highlightedId }"
          :style="{ '--area-color': a.color }"
          @click="emit('select', a.id)"
          @mouseenter="emit('hover', a.id)"
          @mouseleave="emit('hover', null)"
        >
          <title>{{ a.label }}</title>
          <polygon :points="a.points" class="halo" vector-effect="non-scaling-stroke" />
          <polygon :points="a.points" class="fill" vector-effect="non-scaling-stroke" />
        </g>
      </svg>
      <svg
        v-else-if="size && points"
        :viewBox="`0 0 ${size.width} ${size.height}`"
        preserveAspectRatio="none"
        class="overlay"
        aria-hidden="true"
      >
        <defs>
          <mask :id="maskId">
            <rect width="100%" height="100%" fill="white" />
            <polygon :points="points" fill="black" />
          </mask>
        </defs>
        <!-- Spotlight: dim everything outside the area. -->
        <rect width="100%" height="100%" class="dim" :mask="`url(#${maskId})`" />
        <!-- Dark halo under the outline keeps it readable on bright shelves. -->
        <polygon :points="points" class="halo" vector-effect="non-scaling-stroke" />
        <polygon :points="points" class="outline" vector-effect="non-scaling-stroke" />
      </svg>
    </template>
  </div>
</template>

<style scoped>
.camera-image { position: relative; overflow: hidden; border-radius: 8px; background: #000; line-height: 0; }
img { width: 100%; height: auto; display: block; }
.overlay { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }

/* One fixed highlight colour, distinct from the stock/status colours. */
.overlay { --area-highlight: #22d3ee; }
.dim { fill: #000; opacity: 0.55; }
.halo { fill: none; stroke: rgba(0, 0, 0, 0.7); stroke-width: 8; stroke-linejoin: round; }
.outline {
  fill: var(--area-highlight);
  fill-opacity: 0.12;
  stroke: var(--area-highlight);
  stroke-width: 3.5;
  stroke-linejoin: round;
  animation: area-pulse 1.6s ease-in-out infinite;
}
@keyframes area-pulse {
  0%, 100% { stroke-opacity: 1; fill-opacity: 0.12; }
  50% { stroke-opacity: 0.55; fill-opacity: 0.22; }
}
@media (prefers-reduced-motion: reduce) {
  .outline { animation: none; }
}
/* Overview mode: areas are clickable, coloured by status. */
.overview { pointer-events: auto; }
.area { cursor: pointer; }
.area .fill {
  fill: var(--area-color);
  fill-opacity: 0.22;
  stroke: var(--area-color);
  stroke-width: 3;
  stroke-linejoin: round;
  transition: fill-opacity 0.15s, stroke-width 0.15s;
}
.area .halo { stroke-width: 7; }
.area:hover .fill, .area.active .fill { fill-opacity: 0.4; stroke-width: 5; }
.area:hover .halo, .area.active .halo { stroke-width: 9; }
.placeholder { line-height: 1.4; padding: 40px; text-align: center; background: var(--floor); margin: 0; }
</style>
