import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Crafter chat view. Dev server proxies /api to the controller (FastAPI :8790).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8790',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    globals: false,
  },
});
