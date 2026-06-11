import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // dev mode: forward API calls to the FastAPI backend
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
