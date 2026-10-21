import { useDeferredValue, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import scenariosUrl from '../data/scenarios.json?url'
import { useJson } from '../lib/hooks'
import { TASK_TYPES } from '../content/benchmark'
import Segmented from './Segmented'

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

/** Search and filter the 1,080 scenarios, and open one to read its options and checkers. */
export default function ScenarioBrowser({ trialScenarios }) {
  const { data, error } = useJson(scenariosUrl)
  const [query, setQuery] = useState('')
  const [type, setType] = useState('all')
  const [domain, setDomain] = useState('all')
  const [difficulty, setDifficulty] = useState('all')
  const [open, setOpen] = useState('fmt-0002') // Box 1's scenario
  const q = useDeferredValue(query.trim().toLowerCase())

  const domains = useMemo(() => {
    const count = {}
    for (const s of data || []) count[s.domain] = (count[s.domain] || 0) + 1
    return Object.entries(count).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  }, [data])

  const hits = useMemo(() => (data || []).filter((s) =>
    (type === 'all' || s.type === type) && (domain === 'all' || s.domain === domain) && (difficulty === 'all' || s.difficulty === difficulty) &&
    (!q || [s.id, s.task, s.seed, s.domain, ...s.options.map((o) => o[1])].some((t) => t.toLowerCase().includes(q)))), [data, type, domain, difficulty, q])

  if (error) return <p className="text-sm text-muted">The scenarios could not be loaded ({error.message}).</p>
  if (!data) return <p className="min-h-[46rem] py-10 text-center text-sm text-muted" role="status">Loading the scenarios…</p>

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
        <ul className="max-h-[26rem] divide-y divide-line overflow-y-auto rounded-2xl border border-line bg-surface lg:order-1 lg:max-h-[40rem]" aria-label="Scenarios">
          {hits.map((s) => (
            <li key={s.id}>
              <button type="button" onClick={() => setOpen(s.id)} aria-pressed={current === s}
                className={`flex w-full items-start gap-3 px-4 py-2.5 text-left transition hover:bg-wash ${current === s ? 'bg-tint/60' : ''}`}>
                <span className="w-[4.6rem] shrink-0 pt-0.5 font-mono text-xs font-semibold text-accent">{s.id}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm text-ink">{s.task}</span>
                  <span className="mt-0.5 block text-xs text-muted">{TASK_TYPES[s.type].title} · {s.domain} · {s.difficulty}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
