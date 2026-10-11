<script setup>
// v-model: { from, to } as unix seconds (undefined = unbounded).
const model = defineModel({ type: Object, default: () => ({}) })

defineProps({
  // Span of the available data (unix seconds), so native pickers open on days that have data.
  min: { type: Number, default: null },
  max: { type: Number, default: null },
})

function toInput(seconds) {
  if (!seconds) return ''
  const d = new Date(seconds * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// Parsed by hand: "YYYY-MM-DDTHH:mm" is local time, which some mobile browsers misread as UTC.
function fromInput(value) {
  const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(value ?? '')
  if (!m) return undefined
  const [, y, mo, d, h, mi] = m.map(Number)
  return Math.floor(new Date(y, mo - 1, d, h, mi).getTime() / 1000)
}

function update(key, value) {
  const seconds = fromInput(value)
  if (seconds === model.value[key]) return
  model.value = { ...model.value, [key]: seconds }
}
</script>

<template>
  <div class="range">
    <label>
      From
      <input
        type="datetime-local"
        :value="toInput(model.from)"
        :min="toInput(min)"
        :max="toInput(model.to ?? max)"
        @change="update('from', $event.target.value)"
        @blur="update('from', $event.target.value)"
      />
    </label>
    <label>
      To
      <input
        type="datetime-local"
        :value="toInput(model.to)"
        :min="toInput(model.from ?? min)"
        :max="toInput(max)"
        @change="update('to', $event.target.value)"
        @blur="update('to', $event.target.value)"
      />
    </label>
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
  input {
    /* iOS collapses an empty native date input to nothing; give it a real box. */
    -webkit-appearance: none;
    appearance: none;
    display: block;
    flex: 1;
    min-width: 0;
    max-width: 70%;
    min-height: 44px;
    font-size: 16px; /* below 16px iOS zooms the page on focus */
    text-align: left;
  }
  input::-webkit-date-and-time-value { text-align: left; min-height: 1.4em; }
}
</style>
