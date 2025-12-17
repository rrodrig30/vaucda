import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import fs from 'fs'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file from backend directory
  const envDir = path.resolve(__dirname, '../backend')
  const env = loadEnv(mode, envDir, '')

  // Determine if HTTPS should be enabled
  const useHttps = env.USE_HTTPS === 'true'
  const protocol = useHttps ? 'https' : 'http'
  const wsProtocol = useHttps ? 'wss' : 'ws'
  const backendPort = env.BACKEND_PORT || '8002'
  const frontendPort = parseInt(env.FRONTEND_PORT || '3005')

  return {
    plugins: [react()],
    envDir: envDir,  // Load .env from backend directory
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
    },
    server: {
      host: '0.0.0.0',  // Listen on all network interfaces for network access
      port: frontendPort,
      strictPort: true,  // Fail if port is not available, don't auto-increment
      ...(useHttps && {
        https: {
          key: fs.readFileSync(path.resolve(__dirname, '../ssl/key.pem')),
          cert: fs.readFileSync(path.resolve(__dirname, '../ssl/cert.pem')),
        },
      }),
      proxy: {
        '/api': {
          target: `${protocol}://localhost:${backendPort}`,
          changeOrigin: true,
          secure: false,  // Accept self-signed certificates
        },
        '/ws': {
          target: `${wsProtocol}://localhost:${backendPort}`,
          ws: true,
          secure: false,
        },
      },
    },
    build: {
      outDir: 'dist',
      sourcemap: true,
      rollupOptions: {
        output: {
          manualChunks: {
            'react-vendor': ['react', 'react-dom', 'react-router-dom'],
            'redux-vendor': ['@reduxjs/toolkit', 'react-redux'],
            'form-vendor': ['react-hook-form', '@hookform/resolvers', 'zod'],
          },
        },
      },
    },
  }
})
