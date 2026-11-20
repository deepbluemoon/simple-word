/// <reference types="vitest" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: '127.0.0.1',
    port: 9502,
    strictPort: true,
    proxy: {
      '^/(simplify|feedback|health)$': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.spec.ts'],
    globals: false,
    coverage: {
      provider: 'v8',
      include: ['src/lib/**', 'src/stores/**', 'src/api/**', 'src/components/**', 'src/views/**'],
      thresholds: {
        'src/lib/**': { lines: 80 },
        'src/stores/**': { lines: 80 },
        'src/api/**': { lines: 80 },
      },
    },
  },
})
