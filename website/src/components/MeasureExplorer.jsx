import DotChart from '../charts/DotChart'
import { Legend } from '../charts/core'
import { LEVEL, NULL_SHARE, modeName } from '../lib/data'
import { measureRows } from '../lib/download'
import { measures, modes } from '../lib/measures'
import { useQuery } from '../lib/url'
import DataTable from './DataTable'
import Segmented from './Segmented'
import { CopyLink, Downloads } from './Share'

const KEYS = Object.keys(measures)
const GROUPS = [...new Set(Object.values(measures).map((m) => m.group))]
const REF = { rate: `dashed: ${NULL_SHARE}`, diff: 'dashed: zero', nats: 'dashed: zero' }

/** Pick any measure and see every model-mode with its interval, or its two halves; kept in the link. */
export default function MeasureExplorer({ shown }) {
  const [{ m: key, view, half }, set] = useQuery({ m: [KEYS, 'later_wins'], view: [['chart', 'table'], 'chart'], half: [['all', 'halves'], 'all'] })
  const m = measures[key]
  const rows = modes.filter((x) => m.values[x.mm] && shown(x)).map((x) => ({ mode: x, v: m.values[x.mm], D: m.values[x.mm].D, H: m.values[x.mm].H }))
  const hasHalves = rows.some((r) => r.D && r.H)
  const split = half === 'halves' && hasHalves

  return (
    <div className="card p-5 sm:p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <label className="block min-w-0 flex-1">
          <span className="text-xs font-semibold uppercase tracking-wide text-muted">Measure</span>
          <select value={key} onChange={(e) => set({ m: e.target.value })}
            className="mt-1.5 block w-full max-w-xl rounded-xl border border-rule bg-surface px-3 py-2 text-sm font-medium text-ink focus:border-rose">
            {GROUPS.map((g) => (
              <optgroup key={g} label={g}>
                {Object.entries(measures).filter(([, x]) => x.group === g).map(([k, x]) => <option key={k} value={k}>{x.label}</option>)}
              </optgroup>
            ))}
          </select>
        </label>
        <div className="flex flex-wrap gap-2">
          {hasHalves && <Segmented label="Data" size="sm" value={split ? 'halves' : 'all'} onChange={(v) => set({ half: v })}
            options={[{ value: 'all', label: 'All scenarios' }, { value: 'halves', label: 'Two halves' }]} />}
          <Segmented label="View" size="sm" value={view} onChange={(v) => set({ view: v })} options={[{ value: 'chart', label: 'Chart' }, { value: 'table', label: 'Table' }]} />
        </div>
      </div>
      <p className="mt-4 max-w-3xl text-sm leading-relaxed text-soft">
        {m.desc} <span className="text-muted">Over {m.denominator}. Paper: {m.where}.</span>
      </p>
      <div className="mt-5">
        {!rows.length ? (
          <p className="py-16 text-center text-sm text-muted">No model-mode matches the filters for this measure.</p>
        ) : view === 'chart' ? (
          <>
            <DotChart rows={rows} unit={m.unit} refAt={m.null} halves={split} label={`${m.label}, per model-mode`} height={300}
              yLabel={m.unit === 'nats' ? 'nats per reply' : m.label.length < 34 ? m.label.toLowerCase() : undefined} />
            <div className="mt-3">
              <Legend extra={[
                m.null != null && <span key="ref">{REF[m.unit]}</span>,
                <span key="ci">{split ? 'left: discovery half; right (grey): held-out half' : `bars: ${LEVEL} intervals`}</span>,
              ]} />
            </div>
          </>
        ) : (
          <DataTable caption={m.label} rowKey={(r) => r.mode.mm} rows={rows} columns={[
            ['Model-mode', (r) => modeName(r.mode)],
            ['Value', (r) => r.v.t, 'right'],
            [`${LEVEL} interval`, (r) => r.v.c || '', 'right'],
            ...(hasHalves ? [['Discovery half', (r) => r.D?.t || '', 'right'], ['Held-out half', (r) => r.H?.t || '', 'right']] : []),
          ]} />
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <Downloads rows={() => measureRows(measures, [key], rows.map((r) => r.mode))} name={`whowins-${key}`} />
        <CopyLink />
      </div>
    </div>
  )
}
