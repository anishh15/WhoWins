import trialsUrl from '../data/trials.json?url'
import { useJson } from '../lib/hooks'
import { useQuery } from '../lib/url'
import { TRIAL_NOTE } from '../content/benchmark'
import SeatChip from './SeatChip'
import Segmented from './Segmented'
import { Bone } from './Skeleton'
import { CopyLink } from './Share'
import Transcript from './Transcript'

/** Every (seat, option) pair a trial's transcript annotates, in order of appearance. */
function carried(trial) {
  const seen = new Map()
  for (const msg of trial.messages) for (const line of msg.lines || []) for (const p of line) {
    if (p.k === 'opt' && !seen.has(`${p.seat}${p.o}`)) seen.set(`${p.seat}${p.o}`, p)
  }
  return [...seen.values()]
}

/** The selection in the link (?exp=, ?scenario=, ?trial=), checked against the data. */
function useSelection(data) {
  const exps = data.map((e) => e.key)
  const [q, set] = useQuery({
    exp: [exps, ''],
    scenario: [data.flatMap((e) => e.groups.map((g) => g.scenario)), ''],
    trial: [data.flatMap((e) => e.groups.flatMap((g) => g.trials.map((t) => t.id))), ''],
  })
  // An experiment named in the link wins; else the first one that has the linked scenario; else the Ladder.
  const e = data.find((x) => x.key === q.exp) || data.find((x) => x.groups.some((g) => g.scenario === q.scenario)) || data[0]
  const g = e.groups.find((x) => x.scenario === q.scenario) || e.groups[0]
  const trial = g.trials.find((t) => t.id === q.trial) || g.trials[0]
  return { e, g, trial, set }
}

function Viewer({ data }) {
  const { e, g, trial, set } = useSelection(data)
  const options = carried(trial)
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Segmented label="Experiment" value={e.key} onChange={(v) => set({ exp: v, scenario: '', trial: '' })} options={data.map((x) => ({ value: x.key, label: x.name }))} size="sm" />
        <CopyLink />
      </div>
      <div className="mt-5 grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <div className="space-y-4">
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-muted">Scenario</span>
            <select value={g.scenario} onChange={(ev) => set({ exp: e.key, scenario: ev.target.value, trial: '' })}
              className="mt-1.5 block w-full rounded-xl border border-rule bg-surface px-3 py-2 text-sm font-medium text-ink">
              {e.groups.map((x) => <option key={x.scenario} value={x.scenario}>{x.scenario}: {x.task}</option>)}
            </select>
          </label>
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">Layout</p>
            <ul className="mt-1.5 max-h-80 space-y-1 overflow-y-auto pr-1">
              {g.trials.map((t) => (
                <li key={t.id}>
                  <button type="button" onClick={() => set({ exp: e.key, scenario: g.scenario, trial: t.id })} aria-pressed={t === trial}
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

/** Real trials of every experiment, as the code renders them, shown like the paper's Box 1. */
export default function TrialViewer() {
  const { data, error } = useJson(trialsUrl)
  if (error) return <p className="text-sm text-muted">The trials could not be loaded ({error.message}).</p>
  if (!data) {
    return (
      <div role="status" aria-label="Loading the trials" className="space-y-5">
        <Bone className="h-9 w-full max-w-xl" />
        <div className="grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]"><Bone className="h-80" /><Bone className="h-[30rem]" /></div>
      </div>
    )
  }
  return <Viewer data={data} />
}
