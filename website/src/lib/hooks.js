import { useEffect, useLayoutEffect, useRef, useState } from 'react'

/** Set the document title for a page. */
export function useTitle(title) {
  useEffect(() => {
    document.title = title ? `${title} · WhoWins` : 'WhoWins: Position, Role or Label?'
  }, [title])
}

/** The width of an element, kept current with a ResizeObserver. */
export function useWidth(initial = 0) {
  const ref = useRef(null)
  const [width, setWidth] = useState(initial)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const observer = new ResizeObserver(([entry]) => setWidth(Math.round(entry.contentRect.width)))
    observer.observe(el)
    setWidth(Math.round(el.getBoundingClientRect().width))
    return () => observer.disconnect()
  }, [])
  return [ref, width]
}

/** Fetch a JSON file that Vite emitted as an asset (large data stays out of the JavaScript bundle). */
export function useJson(url) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  useEffect(() => {
    let live = true
    fetch(url)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`${r.status} ${r.statusText}`))))
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e))
    return () => {
      live = false
    }
  }, [url])
  return { data, error }
}
