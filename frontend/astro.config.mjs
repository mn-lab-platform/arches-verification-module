import { defineConfig } from 'astro/config';
import preact from '@astrojs/preact';

export default defineConfig({
  base: '/verify/',
  output: 'static',
  integrations: [preact()],
});
