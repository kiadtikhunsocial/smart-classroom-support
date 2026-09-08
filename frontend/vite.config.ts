import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  define: {
    // Railway build doesn't reliably inject .env — pin the production API URL here.
    __VITE_API_URL__: JSON.stringify(process.env.VITE_API_URL || 'https://backend-production-728f.up.railway.app/api'),
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
    allowedHosts: ['frontend-production-5c575.up.railway.app', '.up.railway.app', 'localhost'],
  },
});
