import base from '../../frontend/vite.config.ts'

export default {
  ...base,
  server: {
    host: '127.0.0.1',
    port: 5195,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:5035' },
  },
}
