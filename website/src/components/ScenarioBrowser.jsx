import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import scenariosUrl from '../data/scenarios.json?url'
import { useDebounced, useJson } from '../lib/hooks'
import { useQuery } from '../lib/url'
import { TASK_TYPES } from '../content/benchmark'
import Segmented from './Segmented'
import { Bone } from './Skeleton'

const TYPE_OPTIONS = [{ value: 'all', label: 'All types' }, ...Object.entries(TASK_TYPES).map(([k, t]) => ({ value: k, label: t.title }))]

function Field({ label, children }) {
  return (
    <div>
      <dt className="text-[0.7rem] font-semibold uppercase tracking-wide text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm text-ink">{children}</dd>
    </div>
  )
}

function Detail({ s, withTrials }) {
  return (
    <article className="card p-5" aria-live="polite" aria-label={`Scenario ${s.id}`}>
      <p className="font-mono text-sm font-semibold text-accent">{s.id}</p>
      <h3 className="mt-1 font-sans text-lg font-semibold leading-snug">{s.task}</h3>
      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Field label="Task type">{TASK_TYPES[s.type].title}</Field>
        <Field label="Domain">{s.domain}</Field>
        <Field label="Difficulty">{s.difficulty}</Field>
        <Field label="Scored on"><code className="font-mono text-xs">{s.key}</code></Field>
      </dl>
      {s.tools && (
        <p className="mt-4 text-sm text-soft">
          Tools offered: {s.tools.map((t) => <code key={t} className="mr-1.5 rounded bg-raised px-1 font-mono text-xs text-ink">{t}</code>)}
        </p>
      )}
      <h4 className="mt-5 font-sans text-xs font-semibold uppercase tracking-wide text-muted">Options</h4>
      <ol className="mt-2 space-y-1.5">
        {s.options.map(([id, text, checker]) => (
          <li key={id} className="rounded-lg border border-line bg-raised/60 px-3 py-2">
            <p className="text-sm text-ink"><span className="mr-2 font-mono text-xs text-muted">{id}</span>{text}</p>
            <p className="mt-0.5 font-mono text-[0.7rem] text-muted">{checker}</p>
          </li>
        ))}
      </ol>
      <h4 className="mt-5 font-sans text-xs font-semibold uppercase tracking-wide text-muted">Why at most one option can win</h4>
      <p className="mt-1 text-sm leading-relaxed text-soft">{s.why}</p>
      <p className="mt-4 text-xs text-muted">Seed family <code className="font-mono">{s.seed}</code></p>
      {withTrials && (
        <Link to={`/benchmark?at=trials&scenario=${s.id}`} className="link mt-4 inline-block text-sm">See its trials in the trial viewer</Link>
      )}
    </article>
  )
}

const ROW = 60 // px: one list row, its task on one line

/** A long list that renders only the rows in view, so scrolling and filtering stay light. */
function VirtualList({ items, label, children }) {
  const ref = useRef(null)
  const [row, setRow] = useState(0) // first row in view; changes every row's height of scroll, not every pixel
  const [height, setHeight] = useState(640)
  useLayoutEffect(() => {
    const el = ref.current
    const observer = new ResizeObserver(() => setHeight(el.clientHeight))
    observer.observe(el)
    return () => observer.disconnect()
  }, [])
  useLayoutEffect(() => {
    ref.current.scrollTop = 0
    setRow(0)
  }, [items])
  const first = Math.max(0, row - 6)
  const last = Math.min(items.length, row + Math.ceil(height / ROW) + 6)
  return (
    <div ref={ref} onScroll={(e) => setRow(Math.floor(e.currentTarget.scrollTop / ROW))}
      className="h-[26rem] overflow-y-auto rounded-2xl border border-line bg-surface lg:order-1 lg:h-[40rem]">
      <ul aria-label={label} className="relative" style={{ height: items.length * ROW }}>
        {items.slice(first, last).map((item, i) => (
          <li key={item.id} aria-setsize={items.length} aria-posinset={first + i + 1}
            className="absolute inset-x-0 border-b border-line" style={{ top: (first + i) * ROW, height: ROW }}>
            {children(item)}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Search and filter every scenario, and open one (kept in the link as ?sid=) to read its options and checkers. */
export default function ScenarioBrowser({ trialScenarios }) {
  const { data, error } = useJson(scenariosUrl)
  const [query, setQuery] = useState('')
  const [type, setType] = useState('all')
  const [domain, setDomain] = useState('all')
  const [difficulty, setDifficulty] = useState('all')
  const [{ sid: open }, set] = useQuery({ sid: [(data || []).map((s) => s.id), 'fmt-0002'] }) // Box 1's scenario by default
  const q = useDebounced(query.trim().toLowerCase())

  const domains = useMemo(() => {
    const count = {}
    for (const s of data || []) count[s.domain] = (count[s.domain] || 0) + 1
    return Object.entries(count).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  }, [data])

  const hits = useMemo(() => (data || []).filter((s) =>
    (type === 'all' || s.type === type) && (domain === 'all' || s.domain === domain) && (difficulty === 'all' || s.difficulty === difficulty) &&
    (!q || [s.id, s.task, s.seed, s.domain, ...s.options.map((o) => o[1])].some((t) => t.toLowerCase().includes(q)))), [data, type, domain, difficulty, q])

  if (error) return <p className="text-sm text-muted">The scenarios could not be loaded ({error.message}).</p>
  if (!data) {
    return (
      <div role="status" aria-label="Loading the scenarios" className="space-y-3">
        <Bone className="h-11" />
        <Bone className="h-8 w-3/4" />
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]"><Bone className="h-[40rem]" /><Bone className="h-[40rem]" /></div>
      </div>
    )
  }

  const current = hits.find((s) => s.id === open) || hits[0]
  return (
    <div>
      <div className="flex flex-col gap-3">
        <label className="relative block">
          <span className="sr-only">Search scenarios</span>
          <Search size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden="true" />
          <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search tasks, options, ids or domains"
            className="w-full rounded-full border border-rule bg-surface py-2.5 pl-10 pr-4 text-sm text-ink placeholder:text-muted focus:border-rose" />
        </label>
        <div className="flex flex-wrap items-center gap-2">
          <Segmented label="Task type" options={TYPE_OPTIONS} value={type} onChange={setType} size="sm" />
          <select aria-label="Domain" value={domain} onChange={(e) => setDomain(e.target.value)} className="rounded-full border border-rule bg-surface px-3 py-1.5 text-xs font-medium text-ink">
            <option value="all">All domains</option>
            {domains.map(([d, n]) => <option key={d} value={d}>{d} ({n})</option>)}
          </select>
          <select aria-label="Difficulty" value={difficulty} onChange={(e) => setDifficulty(e.target.value)} className="rounded-full border border-rule bg-surface px-3 py-1.5 text-xs font-medium text-ink">
            <option value="all">Any difficulty</option>
            {['easy', 'medium', 'hard'].map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>
      </div>
      <p className="mt-4 text-sm text-muted" aria-live="polite">{hits.length.toLocaleString('en-US')} of {data.length.toLocaleString('en-US')} scenarios</p>
      <div className="mt-3 grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
        <div className="lg:order-2">
          {current ? <Detail s={current} withTrials={trialScenarios.has(current.id)} /> : (
            <p className="card px-5 py-16 text-center text-sm text-muted">No scenario matches. Try fewer words or another filter.</p>
          )}
        </div>
        {hits.length ? (
          <VirtualList items={hits} label="Scenarios">
            {(s) => (
              <button type="button" onClick={() => set({ sid: s.id })} aria-pressed={current === s} title={s.task}
                className={`flex h-full w-full items-start gap-3 px-4 py-2.5 text-left transition-colors hover:bg-wash ${current === s ? 'bg-tint/60' : ''}`}>
                <span className="w-[4.6rem] shrink-0 pt-0.5 font-mono text-xs font-semibold text-accent">{s.id}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink">{s.task}</span>
                  <span className="mt-0.5 block truncate text-xs text-muted">{TASK_TYPES[s.type].title} · {s.domain} · {s.difficulty}</span>
                </span>
              </button>
            )}
          </VirtualList>
        ) : <div className="lg:order-1" />}
      </div>
    </div>
  )
}
