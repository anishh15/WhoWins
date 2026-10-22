import { useRef } from 'react'

const NEXT = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }

/**
 * Mutually exclusive buttons as an ARIA radio group: one tab stop (the checked option), arrow keys
 * move and select with wrap-around, Home and End jump to the ends.
 */
export default function Segmented({ label, options, value, onChange, size = 'md' }) {
  const refs = useRef([])
  const pad = size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-sm'
  const checked = Math.max(0, options.findIndex((o) => o.value === value))

  const select = (i) => {
    const j = (i + options.length) % options.length
    onChange(options[j].value)
    refs.current[j]?.focus()
  }
  const onKeyDown = (e, i) => {
    const to = e.key in NEXT ? i + NEXT[e.key] : e.key === 'Home' ? 0 : e.key === 'End' ? options.length - 1 : null
    if (to === null) return
    e.preventDefault()
    select(to)
  }

  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-full border border-line bg-surface p-1">
      {options.map((o, i) => {
        const on = i === checked
        return (
          <button
            key={o.value}
            ref={(el) => { refs.current[i] = el }}
            type="button"
            role="radio"
            aria-checked={on}
            tabIndex={on ? 0 : -1}
            onClick={() => onChange(o.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`rounded-full font-medium transition-[transform,background-color,color] duration-150 active:scale-95 ${pad} ${on ? 'bg-accent text-surface shadow-sm' : 'text-soft hover:bg-wash hover:text-ink'}`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
