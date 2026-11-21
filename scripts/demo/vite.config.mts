import base from '../../frontend/vite.config.ts'

export default {
  ...base,
  cacheDir: process.env.T14_STATE_DIR ? `${process.env.T14_STATE_DIR}/vite` : base.cacheDir,
  plugins: [
    ...(base.plugins ?? []),
    {
      name: 't14-demo-notice',
      transformIndexHtml() {
        return [{
          tag: 'style',
          children: 'html { scroll-padding-bottom: 3.5rem } body { padding-bottom: 3.5rem }',
          injectTo: 'head',
        }, {
          tag: 'aside',
          attrs: {
            'aria-label': 'Tryb pokazowy',
            style: 'position:fixed;inset:auto 0 0;z-index:20;pointer-events:none;background:#33260d;color:#ffdf9b;padding:.38rem .8rem;text-align:center;font:600 .875rem system-ui',
          },
          children: 'Tryb pokazowy · Persony, interakcje i kontakt są symulowane. Karty radaru mają własne źródła.',
          injectTo: 'body-prepend' as const,
        }]
      },
    },
  ],
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:5014' },
  },
}
