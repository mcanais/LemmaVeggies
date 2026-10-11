import { useRouter } from 'vue-router'

// Back to the previous page in the app; to the store when the page was opened directly.
export function useGoBack() {
  const router = useRouter()
  return () => (window.history.state?.back ? router.back() : router.push({ name: 'store' }))
}
