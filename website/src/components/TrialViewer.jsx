import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import trialsUrl from '../data/trials.json?url'
import { useJson } from '../lib/hooks'
import { TRIAL_NOTE } from '../content/benchmark'
import SeatChip from './SeatChip'
import Segmented from './Segmented'
import Transcript from './Transcript'

/** The options a trial puts in play, read from its own transcript, with the seat that carries each. */
function carried(trial) {
  const seen = new Map()
  for (const msg of trial.messages) for (const line of msg.lines || []) for (const p of line) {
    if (p.k === 'opt' && !seen.has(`${p.seat}${p.o}`)) seen.set(`${p.seat}${p.o}`, p)
  }
  return [...seen.values()]
}

/** Real trials of every experiment, as the code renders them, shown like the paper's Box 1. */
export default function TrialViewer() {
  const { data, error } = useJson(trialsUrl)
  const [params] = useSearchParams()
  const [exp, setExp] = useState('ladder')
  const [group, setGroup] = useState(0)
  const [index, setIndex] = useState(0)

  // A link from the scenario browser opens that scenario's Ladder trials.
  useEffect(() => {
    const want = params.get('scenario')
    if (!data || !want) return
    for (const e of data) {
      const g = e.groups.findIndex((x) => x.scenario === want)
      if (g >= 0) {
        setExp(e.key)
        setGroup(g)
        setIndex(0)
        return
      }
    }
  }, [data, params])

  if (error) return <p className="text-sm text-muted">The trials could not be loaded ({error.message}).</p>
  if (!data) return <p className="min-h-[32rem] py-10 text-center text-sm text-muted" role="status">Loading the trials…</p>

  const e = data.find((x) => x.key === exp)
  const g = e.groups[Math.min(group, e.groups.length - 1)]
  const trial = g.trials[Math.min(index, g.trials.length - 1)]
  const options = carried(trial)
  return (
    <div>
      <Segmented label="Experiment" value={exp} onChange={(v) => { setExp(v); setGroup(0); setIndex(0) }} options={data.map((x) => ({ value: x.key, label: x.name }))} size="sm" />
      <div className="mt-5 grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <div className="space-y-4">
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Scenario</span>
            <select value={group} onChange={(ev) => { setGroup(Number(ev.target.value)); setIndex(0) }}
              className="mt-1.5 block w-full rounded-xl border border-rule bg-surface px-3 py-2 text-sm font-medium text-ink">
              {e.groups.map((x, i) => <option key={x.scenario} value={i}>{x.scenario}: {x.task}</option>)}
            </select>
          </label>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Layout</p>
            <ul className="mt-1.5 max-h-80 space-y-1 overflow-y-auto pr-1">
              {g.trials.map((t, i) => (
                <li key={t.id}>
                  <button type="button" onClick={() => setIndex(i)} aria-pressed={t === trial}
                    className={`w-full rounded-lg px-3 py-1.5 text-left text-sm transition ${t === trial ? 'bg-accent text-surface' : 'text-soft hover:bg-wash hover:text-ink'}`}>
                    {t.label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <div className="min-w-0">
          <figure className="card overflow-hidden">
            <figcaption className="flex flex-wrap items-center justify-between gap-2 border-b border-blush/70 bg-tint/60 px-4 py-2.5">
              <span className="font-serif text-[0.95rem] font-semibold text-accent">{e.name}: {trial.label}</span>
              <code className="font-mono text-[0.7rem] text-soft">{trial.id}</code>
            </figcaption>
            <div className="px-4 py-4">
              <Transcript trial={trial} />
            </div>
            {options.length > 0 && (
              <div className="border-t border-line px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-muted">Options in play</p>
                <ul className="mt-2 space-y-1">
                  {options.map((p) => (
                    <li key={`${p.seat}${p.o}`} className="flex items-baseline gap-2 text-sm text-soft">
                      {p.seat ? <SeatChip seat={p.seat} /> : <span className="font-mono text-xs text-muted">{trial.ranks ? `priority ${trial.ranks[p.o]}` : ''}</span>}
                      <span className="font-mono text-xs text-muted">{p.o}</span>
                      <span className="text-ink">{p.s}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </figure>
          <p className="mt-3 text-xs leading-relaxed text-muted">{TRIAL_NOTE}</p>
        </div>
      </div>
    </div>
  )
}
