import { useState } from 'react'
import { Check, Download, Link2 } from 'lucide-react'
import { save } from '../lib/download'

const button = 'inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-2.5 py-1 text-xs font-medium text-soft transition hover:border-rose hover:text-accent'

/** Copy the address of the current view, filters and selection included. */
export function CopyLink() {
  const [done, setDone] = useState(false)
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setDone(true)
      setTimeout(() => setDone(false), 1600)
    } catch {
      // Clipboard access can be refused; the address bar still holds the link.
    }
  }
  return (
    <button type="button" onClick={copy} className={button}>
      {done ? <Check size={13} aria-hidden="true" /> : <Link2 size={13} aria-hidden="true" />}
      <span aria-live="polite">{done ? 'Link copied' : 'Copy link'}</span>
    </button>
  )
}

/** CSV and JSON downloads of the aggregates a view shows (rows from lib/download). */
export function Downloads({ rows, name, label = 'Download' }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-xs text-muted">{label}</span>
      {['csv', 'json'].map((f) => (
        <button key={f} type="button" onClick={() => save(rows(), name, f)} className={button} aria-label={`${label} as ${f.toUpperCase()}`}>
          <Download size={13} aria-hidden="true" /> {f.toUpperCase()}
        </button>
      ))}
    </span>
  )
}
