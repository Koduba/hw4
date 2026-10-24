import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const API = 'http://127.0.0.1:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // FastAPI backend (hw4/backend) serves the catalogue and product photos.
    proxy: { '/api': API, '/media': API },
  },
})
