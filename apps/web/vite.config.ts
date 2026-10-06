import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const apiTarget = process.env.QA_API_PROXY_TARGET ?? 'http://127.0.0.1:8001'

// /reports is proxied too: "View report" opens the uploaded Playwright HTML
// report, which the API serves as static files.
const proxy = {
  '/api': { target: apiTarget, changeOrigin: false },
  '/health': { target: apiTarget, changeOrigin: false },
  '/reports': { target: apiTarget, changeOrigin: false },
}

export default defineConfig({
  plugins: [react()],
  server: { host: '0.0.0.0', port: 5174, strictPort: true, proxy },
  preview: { host: '0.0.0.0', port: 5174, strictPort: true, proxy },
})
