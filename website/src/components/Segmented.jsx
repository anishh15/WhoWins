/** A row of mutually exclusive buttons (a radio group), used for filters and view switches. */
export default function Segmented({ label, options, value, onChange, size = 'md' }) {
  const pad = size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-sm'
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex flex-wrap gap-1 rounded-full border border-line bg-surface p-1">
      {options.map((o) => {
        const on = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={`rounded-full font-medium transition ${pad} ${on ? 'bg-accent text-surface shadow-sm' : 'text-soft hover:bg-wash hover:text-ink'}`}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
