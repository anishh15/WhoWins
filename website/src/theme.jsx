import { createContext, useContext, useEffect, useState } from 'react'

const KEY = 'whowins-theme'
const DARK = '(prefers-color-scheme: dark)'
const ThemeContext = createContext(null)

/** The theme the reader chose with the toggle, or null to follow the system. */
function saved() {
  try {
    const v = localStorage.getItem(KEY)
    return v === 'dark' || v === 'light' ? v : null
  } catch {
    return null
  }
}

const systemTheme = () => (window.matchMedia(DARK).matches ? 'dark' : 'light')

export function ThemeProvider({ children }) {
  const [choice, setChoice] = useState(saved)
  const [system, setSystem] = useState(systemTheme)
  const theme = choice ?? system

  // Until the reader toggles, follow the system setting, including changes to it.
  useEffect(() => {
    if (choice) return undefined
    const query = window.matchMedia(DARK)
    const update = () => setSystem(systemTheme())
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [choice])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setChoice(next)
    try {
      localStorage.setItem(KEY, next)
    } catch {
      // Storage can be blocked; the choice still holds for this visit.
    }
  }
  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>
}

export const useTheme = () => useContext(ThemeContext)
