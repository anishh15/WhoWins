import { ArrowUp } from 'lucide-react'

/** A compact list of the page's sections, linking with the site's ?at= convention. */
export default function Contents({ route, items }) {
  return (
    <nav aria-label="On this page" className="rounded-2xl border border-line bg-raised/70 px-4 py-3">
      <p className="eyebrow mb-2">On this page</p>
      <ol className="flex flex-wrap gap-x-4 gap-y-1.5 text-sm">
        {items.map(([id, label], i) => (
          <li key={id}>
            <a href={`#/${route}?at=${id}`} className="text-soft hover:text-accent">
              <span className="mr-1 text-muted">{i + 1}.</span>{label}
            </a>
          </li>
        ))}
      </ol>
    </nav>
  )
}

/** Back to the top of the page, moving focus to the main content. */
export function BackToTop() {
  const top = () => {
    window.scrollTo({ top: 0 })
    document.getElementById('main')?.focus({ preventScroll: true })
  }
  return (
    <p className="mt-6 text-right">
      <button type="button" onClick={top} className="inline-flex items-center gap-1 text-xs font-medium text-muted hover:text-accent">
        <ArrowUp size={13} aria-hidden="true" /> Back to top
      </button>
    </p>
  )
}
