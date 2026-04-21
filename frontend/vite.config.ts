import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { visualizer } from 'rollup-plugin-visualizer'
import viteCompression from 'vite-plugin-compression'

export default defineConfig({
  plugins: [
    react(),
    visualizer({
      filename: './dist/stats.html',
      open: false,
      gzipSize: true,
      brotliSize: true,
    }),
    viteCompression({
      algorithm: 'gzip',
      ext: '.gz',
    }),
    viteCompression({
      algorithm: 'brotliCompress',
      ext: '.br',
    }),
  ],
  build: {
    chunkSizeWarningLimit: 500,
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
      },
    },
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes('node_modules')) {
            if (id.includes('recharts')) {
              return 'vendor-charts'
            }
            if (id.includes('react') || id.includes('react-dom') || id.includes('react-router-dom') || id.includes('@tanstack/react-query')) {
              return 'vendor-react'
            }
            if (id.includes('framer-motion') || id.includes('lucide-react')) {
              return 'vendor-ui'
            }
            if (id.includes('mapbox-gl') || id.includes('react-map-gl') || id.includes('react-simple-maps') || id.includes('leaflet') || id.includes('react-leaflet') || id.includes('d3-geo')) {
              return 'vendor-maps'
            }
            if (id.includes('three') && !id.includes('three-globe')) {
              return 'vendor-three'
            }
            if (id.includes('react-globe.gl') || id.includes('three-globe') || id.includes('globe.gl')) {
              return 'vendor-globe'
            }
          }
        },
      },
    },
  },
  server: {
    port: 5174,
    host: '0.0.0.0',
    allowedHosts: ['polyedge.aitradepulse.com', 'localhost', '127.0.0.1'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8100',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://127.0.0.1:8100',
        ws: true,
        changeOrigin: true
      }
    }
  },
  preview: {
    host: '0.0.0.0',
    port: 5174,
    allowedHosts: ['polyedge.aitradepulse.com', 'localhost'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8100',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://127.0.0.1:8100',
        ws: true,
        changeOrigin: true
      }
    }
  }
})
