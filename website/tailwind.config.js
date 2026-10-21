/** @type {import('tailwindcss').Config} */
const token = (name) => `rgb(var(--${name}) / <alpha-value>)`

export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  darkMode: ['class'],
  theme: {
    extend: {
      colors: {
        bg: token('bg'),
        surface: token('surface'),
        raised: token('raised'),
        tint: token('tint'),
        wash: token('wash'),
        line: token('line'),
        rule: token('rule'),
        ink: token('ink'),
        soft: token('soft'),
        muted: token('muted'),
        accent: token('accent'),
        rose: token('rose'),
        blush: token('blush'),
        steel: token('steel'),
      },
      fontFamily: {
        serif: ['"Source Serif 4 Variable"', '"Times New Roman"', 'Times', 'serif'],
        sans: ['"Inter Variable"', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
        mono: ['"JetBrains Mono Variable"', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      maxWidth: { page: '76rem' },
      boxShadow: {
        card: '0 1px 2px rgb(var(--shadow) / 0.06), 0 8px 24px -12px rgb(var(--shadow) / 0.18)',
        lift: '0 2px 4px rgb(var(--shadow) / 0.08), 0 18px 40px -18px rgb(var(--shadow) / 0.35)',
      },
    },
  },
  plugins: [],
}
