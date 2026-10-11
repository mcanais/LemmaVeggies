<script setup>
const model = defineModel({ type: String, required: true })

defineProps({
  // { [tabKey]: number } shown as a badge when > 0
  badges: { type: Object, default: () => ({}) },
})

const TABS = [
  { key: 'map', label: 'Map', icon: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z' },
  { key: 'cameras', label: 'Cameras', icon: 'M3 8a2 2 0 0 1 2-2h2l2-2h6l2 2h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM12 10a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7z' },
  { key: 'products', label: 'Products', icon: 'M21 8l-9-5-9 5 9 5 9-5zM3 8v8l9 5 9-5V8M12 13v8' },
  { key: 'stats', label: 'Stats', icon: 'M12 3a9 9 0 1 0 9 9h-9zM15 3.5A9 9 0 0 1 20.5 9H15z' },
]
</script>

<template>
  <nav class="tabbar" aria-label="Sections">
    <button
      v-for="t in TABS"
      :key="t.key"
      class="tabbar-item"
      :class="{ active: model === t.key }"
      :aria-current="model === t.key ? 'page' : undefined"
      @click="model = t.key"
    >
      <span class="icon-wrap">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" aria-hidden="true">
          <path :d="t.icon" />
        </svg>
        <span v-if="badges[t.key]" class="badge-count">{{ badges[t.key] }}</span>
      </span>
      <span class="label">{{ t.label }}</span>
    </button>
  </nav>
</template>

<style scoped>
.tabbar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 40;
  display: flex;
  height: calc(var(--tabbar-h) + env(safe-area-inset-bottom));
  padding-bottom: env(safe-area-inset-bottom);
  background: var(--surface);
  border-top: 1px solid var(--border);
  box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.06);
}
.tabbar-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border: none;
  border-radius: 0;
  background: none;
  color: var(--muted);
  font-size: 0.72rem;
  font-weight: 600;
  padding: 0;
}
.tabbar-item.active { color: var(--accent); }
.icon-wrap { position: relative; display: flex; }
.badge-count {
  position: absolute;
  top: -6px;
  right: -12px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: #e5484d;
  color: #fff;
  font-size: 0.68rem;
  line-height: 18px;
  text-align: center;
}
</style>
