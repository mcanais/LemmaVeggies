import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import mockApi from './mock/mockApi.js'

// `npm run dev` proxies /api to the Python server (backend/server.py);
// `npm run dev:mock` serves the random mock instead.
export default defineConfig(({ mode }) => ({
  plugins: [vue(), ...(mode === 'mock' ? [mockApi()] : [])],
  server: {
    proxy: mode === 'mock' ? undefined : { '/api': 'http://127.0.0.1:8000' },
  },
}))
