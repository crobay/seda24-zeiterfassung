import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    https: {
      key: fs.readFileSync('/root/zeiterfassung/frontend/ssl/key.pem'),
      cert: fs.readFileSync('/root/zeiterfassung/frontend/ssl/cert.pem')
    }
  }
})
