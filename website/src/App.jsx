import { Suspense, lazy, useEffect } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import Navbar from './components/Navbar'
import Footer from './components/Footer'

const Home = lazy(() => import('./pages/Home'))
const Results = lazy(() => import('./pages/Results'))
const Findings = lazy(() => import('./pages/Findings'))
const Matchups = lazy(() => import('./pages/Matchups'))
const Benchmark = lazy(() => import('./pages/Benchmark'))
const Docs = lazy(() => import('./pages/Docs'))
const Paper = lazy(() => import('./pages/Paper'))
const NotFound = lazy(() => import('./pages/NotFound'))

// A new page starts at the top, unless the link points at a section of it (?at=id), which may only
// appear once the page's code has loaded.
function ScrollToTop() {
  const { pathname, search } = useLocation()
  useEffect(() => {
    const id = new URLSearchParams(search).get('at')
    if (!id) {
      window.scrollTo(0, 0)
      return undefined
    }
    let frame
    let tries = 0
    const go = () => {
      const el = document.getElementById(id)
      if (el) el.scrollIntoView()
      else if (tries++ < 120) frame = requestAnimationFrame(go)
    }
    go()
    return () => cancelAnimationFrame(frame)
  }, [pathname, search])
  return null
}

function Loading() {
  return (
    <div className="page flex min-h-[60vh] items-center justify-center" role="status">
      <span className="text-sm text-muted">Loading…</span>
    </div>
  )
}

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" className="skip-link" onClick={(e) => {
        e.preventDefault()
        document.getElementById('main')?.focus()
      }}>
        Skip to content
      </a>
      <Navbar />
      <ScrollToTop />
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/results" element={<Results />} />
            <Route path="/findings" element={<Findings />} />
            <Route path="/seats" element={<Matchups />} />
            <Route path="/benchmark" element={<Benchmark />} />
            <Route path="/docs" element={<Docs />} />
            <Route path="/paper" element={<Paper />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </main>
      <Footer />
    </div>
  )
}
