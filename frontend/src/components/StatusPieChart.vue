<script setup>
import { computed } from 'vue'
import { Doughnut } from 'vue-chartjs'
import { Chart as ChartJS, ArcElement, Tooltip } from 'chart.js'
import { AREA_STATUSES } from '../constants/stock.js'

ChartJS.register(ArcElement, Tooltip)

const props = defineProps({
  // { wrong, empty, half, full } area counts
  counts: { type: Object, required: true },
})

const total = computed(() => Object.values(props.counts).reduce((sum, n) => sum + n, 0))

const slices = computed(() =>
  Object.entries(AREA_STATUSES).map(([key, s]) => ({
    key,
    ...s,
    count: props.counts[key] ?? 0,
    percent: total.value ? Math.round(((props.counts[key] ?? 0) / total.value) * 100) : 0,
  })),
)

const data = computed(() => ({
  labels: slices.value.map((s) => s.label),
  datasets: [
    {
      data: slices.value.map((s) => s.count),
      backgroundColor: slices.value.map((s) => s.color),
      hoverBackgroundColor: slices.value.map((s) => s.color),
      // No borders: the gaps between slices are transparent, so the card
      // background shows through in both light and dark themes.
      borderWidth: 0,
      spacing: 3,
      borderRadius: 4,
      hoverOffset: 6,
    },
  ],
}))

const options = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  cutout: '64%',
  layout: { padding: 6 },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: 'rgba(17, 17, 19, 0.92)',
      padding: 10,
      cornerRadius: 6,
      boxPadding: 4,
      usePointStyle: true,
      callbacks: {
        label: (item) => {
          const s = slices.value[item.dataIndex]
          return ` ${s.count} areas (${s.percent}%)`
        },
      },
    },
  },
}
</script>

<template>
  <div class="status-pie">
    <div class="chart">
      <Doughnut :data="data" :options="options" />
    </div>
    <ul class="legend">
      <li v-for="s in slices" :key="s.key">
        <span class="swatch" :style="{ background: s.color }" />
        <span class="label">{{ s.label }}</span>
        <strong>{{ s.count }}</strong>
        <span class="muted percent">{{ s.percent }}%</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.status-pie { display: flex; align-items: center; gap: 24px; flex-wrap: wrap; }
.chart { position: relative; width: 190px; height: 190px; flex-shrink: 0; margin: 0 auto; }
.center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  line-height: 1.1;
}
.center strong { font-size: 1.9rem; }
.center span { font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.06em; }
.legend { list-style: none; margin: 0; padding: 0; flex: 1; min-width: 180px; }
.legend li { display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--border); }
.legend li:last-child { border-bottom: none; }
.swatch { width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0; }
.label { flex: 1; }
.percent { width: 3.2em; text-align: right; font-size: 0.85rem; }
</style>
