import { useLayoutEffect, useRef, useState } from 'react'

/**
 * A box that scrolls sideways when its content is wider than the screen. Only then does it show a
 * "swipe" hint and a fade on the right edge, and the fade goes once the end is reached.
 */
export default function ScrollBox({ label, className = '', fade = 'rgb(var(--surface))', children }) {
  const ref = useRef(null)
  const [state, setState] = useState({ over: false, end: true })
  useLayoutEffect(() => {
    const el = ref.current
    const update = () => {
      const next = { over: el.scrollWidth > el.clientWidth + 1, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 2 }
      setState((s) => (s.over === next.over && s.end === next.end ? s : next))
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    el.addEventListener('scroll', update, { passive: true })
    return () => {
      observer.disconnect()
      el.removeEventListener('scroll', update)
    }
  }, [])
  return (
    <div>
      {state.over && <p className="mb-2 text-xs text-muted" aria-hidden="true">Swipe to see all columns →</p>}
      <div className="relative">
        <div ref={ref} tabIndex={state.over ? 0 : undefined} role="region" aria-label={label} className={`overflow-x-auto ${className}`}>
          {children}
        </div>
        {state.over && !state.end && (
          <div aria-hidden="true" className="pointer-events-none absolute inset-y-px right-px w-12 rounded-r-2xl" style={{ background: `linear-gradient(to left, ${fade}, transparent)` }} />
        )}
      </div>
    </div>
  )
}
