import { useTheme } from '../theme'

// The paper's figures, copied into src/assets by site_data.py; a "-dark" file is the dark-theme variant.
const FILES = import.meta.glob('../assets/fig*.png', { eager: true, query: '?url', import: 'default' })

/** The URL of a figure for the active theme, falling back to the light figure. */
export function useFigure(file) {
  const { theme } = useTheme()
  const light = FILES[`../assets/${file}`]
  return theme === 'dark' ? FILES[`../assets/${file.replace(/\.png$/, '-dark.png')}`] || light : light
}
