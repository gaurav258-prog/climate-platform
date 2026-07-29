import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Greenfield Tellumen agri UI. Proxies /v1 to the existing FastAPI (no backend changes).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  // maplibre-gl ships its own web worker; Vite's dep optimizer drops the worker file, which
  // silently breaks all worker-side tiling (GeoJSON / vector / symbol / circle) while raster
  // still renders. Excluding it makes Vite serve maplibre unbundled so the worker loads.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  server: {
    port: 5180,
    proxy: {
      '/v1': { target: 'http://localhost:8001', changeOrigin: true },
      '/health': { target: 'http://localhost:8001', changeOrigin: true },
    },
  },
})
