import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BASE = '/WhoWins/'

// Preload the faces the first screen uses (Latin sans, serif and serif italic), so text never flashes or reflows.
const MAIN_FACES = /(inter-latin-wght-normal|source-serif-4-latin-opsz-(normal|italic))-[\w-]+\.woff2$/

function preloadFonts() {
  return {
    name: 'preload-main-fonts',
    transformIndexHtml: {
      order: 'post',
      handler(html, ctx) {
        const files = Object.keys(ctx.bundle || {}).filter((f) => MAIN_FACES.test(f))
        return files.map((f) => ({
          tag: 'link',
          attrs: { rel: 'preload', as: 'font', type: 'font/woff2', href: BASE + f, crossorigin: '' },
          injectTo: 'head',
        }))
      },
    },
  }
}

export default defineConfig({
  plugins: [react(), preloadFonts()],
  base: BASE,
})
