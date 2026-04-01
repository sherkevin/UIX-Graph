import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],

  server: {
    port: 3000,
    // 开发代理：/api → 后端 :8000
    // 生产/外网部署时由反向代理承担此职责，此配置仅对 `npm run dev` 生效
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },

  build: {
    // 生产构建产物输出目录（供反向代理 / 静态文件服务器托管）
    outDir: 'dist',
    // 资源文件超过此大小才单独拆分
    chunkSizeWarningLimit: 1000,
  },
})
