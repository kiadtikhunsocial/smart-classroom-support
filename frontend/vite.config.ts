import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  define: {
    // Production API URL มาจาก VITE_API_URL (ตั้งตอน deploy) — fallback localhost สำหรับ dev.
    // Render/Neon/Vercel deploy ตั้ง VITE_API_URL = https://<render-backend>.onrender.com/api
    __VITE_API_URL__: JSON.stringify(process.env.VITE_API_URL || 'http://localhost:8000/api'),
  },
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  preview: {
    allowedHosts: ['.up.railway.app', '.vercel.app', 'localhost'],
  },
});
