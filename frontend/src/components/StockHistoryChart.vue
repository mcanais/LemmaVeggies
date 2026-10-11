<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Filler } from 'chart.js'
import { STOCK_LEVELS, AREA_STATUSES, stockLabel } from '../constants/stock.js'
import { useIsMobile } from '../composables/useMediaQuery.js'

ChartJS.register(LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Filler)

const props = defineProps({
  // [{ timestamp, compliant, stockLevel }]
  history: { type: Array, required: true },
})

const NONCOMPLIANT_COLOR = AREA_STATUSES.wrong.color
const isMobile = useIsMobile()
const VALUE_LABELS = Object.fromEntries(Object.values(STOCK_LEVELS).map((l) => [l.value, l.label]))

const data = computed(() => ({
  labels: props.history.map((h) =>
    new Date(h.timestamp * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  ),
  datasets: [
    {
      label: 'Stock',
      data: props.history.map((h) => STOCK_LEVELS[h.stockLevel]?.value ?? null),
      // Smooth curve between readings; 'monotone' never overshoots past Full or Empty.
      cubicInterpolationMode: 'monotone',
      tension: 0.4,
      // Points sit exactly on the y min/max, so don't clip them to the chart area.
      clip: false,
      borderColor: '#2f6f4f',
      backgroundColor: 'rgba(47, 111, 79, 0.12)',
      fill: true,
      pointRadius: props.history.map((h) => (h.compliant ? 4 : 8)),
      pointStyle: props.history.map((h) => (h.compliant ? 'circle' : 'crossRot')),
      pointBackgroundColor: props.history.map((h) =>
        h.compliant ? STOCK_LEVELS[h.stockLevel]?.color : NONCOMPLIANT_COLOR,
      ),
      // Crosses are drawn by their stroke only, so they take the status colour.
      pointBorderColor: props.history.map((h) => (h.compliant ? '#ffffff' : NONCOMPLIANT_COLOR)),
      pointBorderWidth: props.history.map((h) => (h.compliant ? 1 : 3)),
    },
  ],
}))

const options = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  // Room for the largest point (radius 8) above "Full" and below "Empty".
  layout: { padding: { top: 10, bottom: 4, left: 4, right: 10 } },
  scales: {
    x: {
      // Fewer, unrotated time labels on narrow screens.
      ticks: { maxTicksLimit: isMobile.value ? 6 : 12, maxRotation: isMobile.value ? 0 : 50 },
    },
    y: {
      min: 0,
      max: 1,
      ticks: { stepSize: 0.5, callback: (v) => VALUE_LABELS[v] ?? '' },
    },
  },
  plugins: {
    tooltip: {
      callbacks: {
        title: (items) => new Date(props.history[items[0].dataIndex].timestamp * 1000).toLocaleString(),
        label: (item) => {
          const h = props.history[item.dataIndex]
          return [`Stock: ${stockLabel(h.stockLevel)}`, h.compliant ? 'Compliant' : '✕ Wrong product']
        },
      },
    },
  },
}))
</script>

<template>
  <div class="chart">
    <p v-if="!history.length" class="muted">No data in this time range.</p>
    <Line v-else :data="data" :options="options" />
  </div>
</template>

<style scoped>
.chart { position: relative; height: 280px; }
@media (max-width: 768px) {
  .chart { height: 220px; }
}
</style>
