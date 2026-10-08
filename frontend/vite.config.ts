import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: process.env.SENTINEL_API_URL || 'http://127.0.0.1:18087', changeOrigin: false },
      '/downloads': { target: process.env.SENTINEL_API_URL || 'http://127.0.0.1:18087', changeOrigin: false },
    },
  },
})
