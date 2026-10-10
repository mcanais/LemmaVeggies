<script setup>
// v-model: { from, to } as unix seconds (undefined = unbounded).
const model = defineModel({ type: Object, default: () => ({}) })

function toInput(seconds) {
  if (!seconds) return ''
  const d = new Date(seconds * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function fromInput(value) {
  return value ? Math.floor(new Date(value).getTime() / 1000) : undefined
}

function update(key, value) {
  model.value = { ...model.value, [key]: fromInput(value) }
}
</script>

<template>
  <div class="range">
    <label>From <input type="datetime-local" :value="toInput(model.from)" @change="update('from', $event.target.value)" /></label>
    <label>To <input type="datetime-local" :value="toInput(model.to)" @change="update('to', $event.target.value)" /></label>
    <button :disabled="!model.from && !model.to" @click="model = {}">All time</button>
  </div>
</template>

<style scoped>
.range { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
label { display: inline-flex; gap: 6px; align-items: center; font-size: 0.9rem; color: var(--muted); }
input { font: inherit; padding: 4px 6px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); color: var(--text); }

@media (max-width: 768px) {
  .range { flex-direction: column; align-items: stretch; }
  label { justify-content: space-between; }
  input { flex: 1; min-height: 44px; max-width: 70%; }
}
</style>
