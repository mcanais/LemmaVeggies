export const STOCK_LEVELS = {
  empty: { label: 'Empty', value: 0, color: '#e5484d' },
  half: { label: 'Half', value: 0.5, color: '#f5c518' },
  full: { label: 'Full', value: 1, color: '#30a46c' },
}

export const UNKNOWN_COLOR = '#9aa0a6'

export function stockColor(level) {
  return STOCK_LEVELS[level]?.color ?? UNKNOWN_COLOR
}

export function stockLabel(level) {
  return STOCK_LEVELS[level]?.label ?? 'Unknown'
}

// One status per area: a wrong product overrides the stock level, so the
// statuses are mutually exclusive and add up to the total number of areas.
// Ordered from most to least urgent.
export const AREA_STATUSES = {
  wrong: { label: 'Wrong product', color: '#8e4ec6', icon: '⚠' },
  empty: { label: STOCK_LEVELS.empty.label, color: STOCK_LEVELS.empty.color, icon: '○' },
  half: { label: STOCK_LEVELS.half.label, color: STOCK_LEVELS.half.color, icon: '◐' },
  full: { label: STOCK_LEVELS.full.label, color: STOCK_LEVELS.full.color, icon: '●' },
}

export function areaStatus(area) {
  return area.compliant ? area.stockLevel : 'wrong'
}

export function countByStatus(areas) {
  const counts = Object.fromEntries(Object.keys(AREA_STATUSES).map((key) => [key, 0]))
  for (const area of areas) {
    const status = areaStatus(area)
    if (status in counts) counts[status]++
  }
  return counts
}
