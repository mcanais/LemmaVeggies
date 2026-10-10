import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import mockApi from './mock/mockApi.js'

export default defineConfig({
  plugins: [vue(), mockApi()],
})
