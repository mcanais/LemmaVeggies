export const API_BASE = '/api'

// Query parameter names for the optional time range (unix seconds).
const RANGE_PARAMS = { from: 'from', to: 'to' }

export function buildUrl(path, params = {}) {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') query.set(key, value)
  }
  const qs = query.toString()
  return `${API_BASE}${path}${qs ? `?${qs}` : ''}`
}

export function rangeParams({ from, to } = {}) {
  return { [RANGE_PARAMS.from]: from, [RANGE_PARAMS.to]: to }
}

export async function request(path, params) {
  const res = await fetch(buildUrl(path, params))
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status} ${res.statusText}`)
  return res.json()
}
