import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to FastAPI, so the browser only ever talks to one
// origin and there is no CORS to configure -- including when the app is served
// behind a sandbox preview host.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: false,
    // The preview proxy rewrites the Host header, so accept any host.
    allowedHosts: true,
    proxy: {
      '/api': {
        target: process.env.MOVEIN_API_URL || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '0.0.0.0',
    port: 4173,
    allowedHosts: true,
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
