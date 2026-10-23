import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The ACAPS backend (uvicorn acaps.api.app:app) listens on :8000 by default.
// In dev, /api and /openapi.json are proxied so the browser sees one origin.
const backend = process.env.VITE_BACKEND_URL ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': backend, '/openapi.json': backend } },
  build: { target: 'es2022', chunkSizeWarningLimit: 900 },
})
