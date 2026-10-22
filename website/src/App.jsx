import { Suspense, lazy, useEffect, useRef } from 'react'
import { Route, Routes, useLocation, useNavigationType } from 'react-router-dom'
import { motion, useReducedMotion } from 'framer-motion'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import { PageSkeleton } from './components/Skeleton'

const Home = lazy(() => import('./pages/Home'))
const Results = lazy(() => import('./pages/Results'))
const Findings = lazy(() => import('./pages/Findings'))
const Matchups = lazy(() => import('./pages/Matchups'))
const Benchmark = lazy(() => import('./pages/Benchmark'))
const Docs = lazy(() => import('./pages/Docs'))
const Paper = lazy(() => import('./pages/Paper'))
const NotFound = lazy(() => import('./pages/NotFound'))

const positions = new Map() // scroll position per history entry, for Back and Forward

/** Run go() on each frame until it returns true or about two seconds pass (a lazy page may still load). */
function whenReady(go) {
  let frame
  let tries = 0
  const step = () => {
    if (!go() && tries++ < 120) frame = requestAnimationFrame(step)
  }
  step()
  return () => cancelAnimationFrame(frame)
}

/**
 * Scrolling between views: Back and Forward return to where the reader was, a link to a section (?at=id)
 * glides to it, a new page starts at the top, and filter or selection changes leave the scroll alone.
 */
function ScrollManager() {
  const location = useLocation()
  const navigation = useNavigationType()
  const reduced = useReducedMotion()
  const at = new URLSearchParams(location.search).get('at')
  const previous = useRef({ pathname: null, at: null })

  useEffect(() => {
    window.history.scrollRestoration = 'manual'
  }, [])

  useEffect(() => {
    const save = () => positions.set(location.key, window.scrollY)
    window.addEventListener('scroll', save, { passive: true })
    return () => window.removeEventListener('scroll', save)
  }, [location.key])

  // Once per navigation: the path, section and motion setting are read as they are at that moment.
  useEffect(() => {
    const was = previous.current
    previous.current = { pathname: location.pathname, at }
    if (navigation === 'POP' && positions.has(location.key)) {
      const y = positions.get(location.key)
      return whenReady(() => {
        if (document.documentElement.scrollHeight < y + window.innerHeight) return false
        window.scrollTo(0, y)
        return true
      })
    }
    if (at && (at !== was.at || location.pathname !== was.pathname)) {
      return whenReady(() => {
        const el = document.getElementById(at)
        el?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' })
        return Boolean(el)
      })
    }
    if (location.pathname !== was.pathname) window.scrollTo(0, 0)
    return undefined
  }, [location.key])
  return null
}

export default function App() {
  const location = useLocation()
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="skip-link" onClick={(e) => {
        e.preventDefault()
        document.getElementById('main')?.focus()
      }}>
        Skip to content
      </a>
      <Navbar />
      <ScrollManager />
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        <Suspense fallback={<PageSkeleton />}>
          {/* A new page fades and rises in; the key is the path, so filters and selections do not replay it. */}
          <motion.div key={location.pathname} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, ease: 'easeOut' }}>
            <Routes location={location}>
              <Route path="/" element={<Home />} />
              <Route path="/results" element={<Results />} />
              <Route path="/findings" element={<Findings />} />
              <Route path="/seats" element={<Matchups />} />
              <Route path="/benchmark" element={<Benchmark />} />
              <Route path="/docs" element={<Docs />} />
              <Route path="/paper" element={<Paper />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </motion.div>
        </Suspense>
      </main>
      <Footer />
    </div>
  )
}
