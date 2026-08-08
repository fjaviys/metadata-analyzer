import { defineConfig } from 'astro/config';
import vue from '@astrojs/vue';
import tailwind from '@astrojs/tailwind';
import node from '@astrojs/node';

// https://astro.build
// SSR con adaptador Node: soporta rutas dinámicas (results/[id]) en producción.
export default defineConfig({
  output: 'server',
  adapter: node({ mode: 'standalone' }),
  integrations: [vue(), tailwind()],
  server: { host: '0.0.0.0', port: 4321 },
});
