import { ref, onMounted, onUnmounted } from 'vue'

// Reactive window.matchMedia(query).matches.
export function useMediaQuery(query) {
  const mql = typeof window !== 'undefined' ? window.matchMedia(query) : null
  const matches = ref(mql?.matches ?? false)
  const update = (e) => (matches.value = e.matches)
  onMounted(() => mql?.addEventListener('change', update))
  onUnmounted(() => mql?.removeEventListener('change', update))
  return matches
}

// Phone-sized layout. Keep in sync with the 768px breakpoint in styles/style.css.
export const useIsMobile = () => useMediaQuery('(max-width: 768px)')

// False on touch-only devices, where hover tooltips can't be used.
export const useCanHover = () => useMediaQuery('(hover: hover)')
