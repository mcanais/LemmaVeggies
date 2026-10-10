<script setup>
const model = defineModel({ type: String, default: '' })

defineProps({
  placeholder: { type: String, default: 'Search…' },
})
</script>

<template>
  <div class="search">
    <span class="icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
        <circle cx="11" cy="11" r="7" />
        <line x1="16.5" y1="16.5" x2="21" y2="21" />
      </svg>
    </span>
    <input
      v-model="model"
      type="search"
      :placeholder="placeholder"
      :aria-label="placeholder"
      @keydown.esc="model = ''"
    />
    <button v-if="model" class="clear" aria-label="Clear search" @click="model = ''">×</button>
  </div>
</template>

<style scoped>
.search { position: relative; margin-bottom: 12px; }
.icon {
  position: absolute;
  left: 10px;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  color: var(--muted);
  pointer-events: none;
}
input {
  width: 100%;
  font: inherit;
  font-size: 0.9rem;
  padding: 7px 32px 7px 32px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--text);
}
input:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 20%, transparent); }
input::-webkit-search-cancel-button { display: none; }
.clear {
  position: absolute;
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
  width: 22px;
  height: 22px;
  min-height: 0;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: none;
  color: var(--muted);
  font-size: 1.1rem;
  line-height: 1;
}
.clear:hover { color: var(--text); background: var(--border); }

@media (pointer: coarse) {
  /* iOS zooms the page when focusing inputs under 16px. */
  input { font-size: 16px; min-height: 44px; }
  .clear { width: 32px; height: 32px; }
}
</style>
