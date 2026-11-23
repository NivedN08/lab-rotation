import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The Python server (lab/server.py) runs on port 8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
  },
})
