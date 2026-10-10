// Lowercase and strip accents so "maca" matches "MAÇA".
export function normalize(text) {
  return String(text).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

// True when every word of the query appears in at least one of the fields.
export function matchesSearch(query, ...fields) {
  const words = normalize(query).split(/\s+/).filter(Boolean)
  if (!words.length) return true
  const haystack = normalize(fields.join(' '))
  return words.every((w) => haystack.includes(w))
}
