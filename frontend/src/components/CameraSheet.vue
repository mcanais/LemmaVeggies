<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { AREA_STATUSES, countByStatus } from '../constants/stock.js'

const props = defineProps({
  // Camera to preview, or null to hide.
  cameraId: { type: String, default: null },
  // That camera's areas: [{ id, productName, compliant, stockLevel }]
  areas: { type: Array, default: () => [] },
})

const emit = defineEmits(['close'])

const router = useRouter()

const statuses = computed(() => {
  const counts = countByStatus(props.areas)
  return Object.entries(AREA_STATUSES)
    .filter(([key]) => counts[key])
    .map(([key, s]) => ({ key, ...s, count: counts[key] }))
})

// One bullet per product, with how many of the camera's areas it holds.
const products = computed(() => {
  const counts = new Map()
  for (const a of props.areas) counts.set(a.productName, (counts.get(a.productName) ?? 0) + 1)
  return [...counts].map(([name, count]) => ({ name, count }))
})

function open() {
  router.push({ name: 'camera', params: { cameraId: props.cameraId } })
}

// --- Swipe down to dismiss
const SWIPE_CLOSE = 60
const dragY = ref(0)
let startY = null

function onPointerDown(e) {
  startY = e.clientY
  e.currentTarget.setPointerCapture(e.pointerId)
}
function onPointerMove(e) {
  if (startY !== null) dragY.value = Math.max(0, e.clientY - startY)
}
function onPointerUp() {
  if (dragY.value > SWIPE_CLOSE) emit('close')
  dragY.value = 0
  startY = null
}

watch(() => props.cameraId, () => (dragY.value = 0))

function onKeydown(e) {
  if (e.key === 'Escape' && props.cameraId) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Transition name="sheet">
    <section
      v-if="cameraId"
      class="sheet"
      role="dialog"
      aria-label="Camera details"
      :style="{ transform: dragY ? `translateY(${dragY}px)` : undefined }"
    >
      <div
        class="grabber"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
      >
        <span class="grabber-bar" />
      </div>

      <div class="content">
        <div class="title-row">
          <h2>Camera {{ cameraId }}</h2>
          <button class="close" aria-label="Close" @click="emit('close')">×</button>
        </div>
        <div class="details">
          <span v-for="s in statuses" :key="s.key" class="status-pill" :style="{ '--status-color': s.color }">
            {{ s.icon }} {{ s.count }} {{ s.label }}
          </span>
        </div>
        <ul class="products">
          <li v-for="p in products" :key="p.name">
            {{ p.name }}<span v-if="p.count > 1" class="muted"> × {{ p.count }}</span>
          </li>
        </ul>
        <button class="open" @click="open">Open camera ›</button>
      </div>
    </section>
  </Transition>
</template>

<style scoped>
.sheet {
  position: fixed;
  left: 0;
  right: 0;
  /* Set by the page: sits above the mobile tab bar. */
  bottom: var(--sheet-bottom, 0px);
  z-index: 30;
  max-width: 640px;
  margin: 0 auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom: none;
  border-radius: 16px 16px 0 0;
  box-shadow: 0 -6px 24px rgba(0, 0, 0, 0.18);
  /* On desktop (no tab bar) keep clear of the home indicator. */
  padding-bottom: var(--sheet-safe-bottom, env(safe-area-inset-bottom));
}
.grabber { display: flex; justify-content: center; padding: 10px 0 6px; touch-action: none; cursor: grab; }
.grabber-bar { width: 40px; height: 5px; border-radius: 3px; background: var(--border); }
.content { padding: 0 16px 14px; }
.title-row { display: flex; align-items: flex-start; gap: 8px; }
.title-row h2 { margin: 0; font-size: 1.1rem; flex: 1; line-height: 1.3; }
.close {
  width: 36px;
  height: 36px;
  min-height: 36px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: var(--bg);
  font-size: 1.3rem;
  line-height: 1;
  color: var(--muted);
}
.details { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin: 8px 0; font-size: 0.9rem; }
.products { margin: 0 0 14px; padding-left: 20px; max-height: 30vh; overflow-y: auto; font-size: 0.9rem; line-height: 1.5; }
.status-pill {
  font-size: 0.8rem;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 999px;
  color: color-mix(in srgb, var(--status-color) 70%, var(--text));
  background: color-mix(in srgb, var(--status-color) 16%, transparent);
}
.open {
  width: 100%;
  min-height: 48px;
  border: none;
  border-radius: 10px;
  background: var(--accent);
  color: var(--surface);
  font-weight: 700;
  font-size: 1rem;
}

.sheet-enter-active, .sheet-leave-active { transition: transform 0.22s ease, opacity 0.22s ease; }
.sheet-enter-from, .sheet-leave-to { transform: translateY(100%); opacity: 0; }
</style>
