import DotChart from '../charts/DotChart'
import { Legend } from '../charts/core'
import PageHeader from '../components/PageHeader'
import Rich from '../components/Rich'
import ScrollBox from '../components/ScrollBox'
import SeatChip from '../components/SeatChip'
import { CopyLink, Downloads } from '../components/Share'
import { MATCHUPS } from '../content/matchups'
import { SEAT_INFO } from '../content/benchmark'
import { FAMILIES, LEVEL, NULL_SHARE, modeName } from '../lib/data'
import { measureRows } from '../lib/download'
import { matchups, measures, modeOf, modes } from '../lib/measures'
import { useQuery } from '../lib/url'
import { useTitle } from '../lib/hooks'

const SEAT_KEYS = ['S1', 'S2', 'S3', 'S4', 'S5']
const heat = (e) => `rgb(var(--heat-red) / ${Math.round(35 * Math.min(1, Math.max(0, e))) / 100})`

function Value({ v, big }) {
  if (!v) return <span className="text-muted">n/a</span>
  return (
    <span className="block">
      <span className={`num font-semibold ${big ? 'text-xl' : 'text-base'} ${v.g ? 'italic text-[rgb(var(--cell-grey))]' : 'text-ink'}`}>{v.t}</span>
      {v.c && <span className="num block text-[0.68rem] text-soft">{v.c}</span>}
    </span>
  )
}

/** One cell or merged block of the seat grid, placed by CSS grid lines. */
function Block({ row, col, rows = 1, cols = 1, v, note, label }) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-lg border border-surface/80 p-2 text-center"
      style={{ gridRow: `${row} / span ${rows}`, gridColumn: `${col} / span ${cols}`, background: v ? heat(v.e) : 'rgb(var(--raised))' }}
      aria-label={label}
    >
      <Value v={v} big={rows * cols > 1} />
      {note && <span className="mt-1 text-[0.7rem] leading-tight text-soft">{note}</span>}
    </div>
  )
}

function SeatGrid({ mm }) {
  const cells = matchups[mm]
  const second = measures.sys_second.values[mm]
  const idx = (s) => SEAT_KEYS.indexOf(s) + 2
  return (
    <ScrollBox label="Seat against seat">
      <div className="grid min-w-[34rem] grid-cols-[6.5rem_repeat(5,minmax(0,1fr))] grid-rows-[2.25rem_repeat(5,minmax(4.6rem,auto))] gap-1.5">
        <div className="flex items-end justify-end pb-1 pr-2 text-[0.7rem] leading-tight text-muted" style={{ gridRow: 1, gridColumn: 1 }}>row beats column</div>
        {SEAT_KEYS.map((s) => (
          <div key={`c${s}`} className="flex items-center justify-center" style={{ gridRow: 1, gridColumn: idx(s) }}><SeatChip seat={s} size="lg" /></div>
        ))}
        {SEAT_KEYS.map((s) => (
          <div key={`r${s}`} className="flex items-center gap-2 pr-2" style={{ gridRow: idx(s), gridColumn: 1 }}>
            <SeatChip seat={s} size="lg" />
            <span className="text-xs leading-tight text-soft">{SEAT_INFO[s].source}</span>
          </div>
        ))}
        {['S3', 'S4', 'S5'].map((s) => (
          <div key={`d${s}`} className="rounded-lg border border-dashed border-line" style={{ gridRow: idx(s), gridColumn: idx(s) }} aria-hidden="true" />
        ))}
        <Block row={2} col={2} rows={2} cols={2} v={second} note={MATCHUPS.secondLine} label={`S1 and S2 in one system message: the second line wins ${second?.t}`} />
        <Block row={2} col={4} rows={2} cols={3} v={cells['op>later']} note={MATCHUPS.opFirst} label={`The operator line, first, beats a later line: ${cells['op>later']?.t}`} />
        <Block row={4} col={2} rows={3} cols={2} v={cells['later>op']} note={MATCHUPS.laterOp} label={`A later line beats the operator line: ${cells['later>op']?.t}`} />
        {[['S3', 'S4'], ['S4', 'S3'], ['S3', 'S5'], ['S5', 'S3'], ['S4', 'S5'], ['S5', 'S4']].map(([a, b]) => (
          <Block key={a + b} row={idx(a)} col={idx(b)} v={cells[`${a}>${b}`]} label={`${a} beats ${b}: ${cells[`${a}>${b}`]?.t}`} />
        ))}
      </div>
    </ScrollBox>
  )
}

function Layouts({ mm }) {
  // gpt-oss receives the operator line as its developer message; Qwen as a system message.
  const role = modeOf[mm].family === 'gpt-oss' ? 'developer' : 'system'
  const tiles = [['op_real_first', `Real ${role} message, first`], ['op_label_first', 'Labelled user text, first'], ['op_real_last', `Real ${role} message, last`], ['op_label_last', 'Labelled user text, last']]
  return (
    <div className="grid grid-cols-2 gap-2">
      {tiles.map(([k, label]) => {
        const v = measures[k].values[mm]
        return (
          <div key={k} className="rounded-xl border border-line p-3" style={{ background: v ? heat(v.e) : 'rgb(var(--raised))' }}>
            <p className="text-xs font-medium text-soft">{label}</p>
            <div className="mt-1.5">{v ? <Value v={v} /> : <span className="text-sm text-muted">{MATCHUPS.noLate}</span>}</div>
          </div>
        )
      })}
    </div>
  )
}

const MODES = modes.map((m) => m.mm)
const GRID_KEYS = ['s3_over_s4', 's3_over_s5', 's5_over_s4', 'op_first', 'sys_second', 'op_real_first', 'op_label_first', 'op_real_last', 'op_label_last']
const PANELS = [['s3_over_s4', '(a) user beats tool result'], ['s3_over_s5', '(b) user beats memory note'], ['s5_over_s4', '(c) memory note beats tool result']]

export default function Matchups() {
  useTitle('Seat matchups')
  const [{ model: mm }, set] = useQuery({ model: [MODES, 'qwen3-8b-nothink'] })
  return (
    <>
      <PageHeader eyebrow="Matchups" title="Which seat beats which" lead={MATCHUPS.lead} />
      <div className="page mt-10 grid gap-8 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <section className="card min-w-0 p-5 sm:p-6" aria-labelledby="grid-title">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <h2 id="grid-title" className="text-xl font-semibold">Head to head</h2>
            <label className="text-sm">
              <span className="sr-only">Model-mode</span>
              <select value={mm} onChange={(e) => set({ model: e.target.value })} className="rounded-xl border border-rule bg-surface px-3 py-2 text-sm font-medium text-ink">
                {FAMILIES.map((f) => (
                  <optgroup key={f.key} label={f.title}>
                    {modes.filter((m) => m.family === f.key).map((m) => <option key={m.mm} value={m.mm}>{modeName(m)}</option>)}
                  </optgroup>
                ))}
              </select>
            </label>
          </div>
          <Rich as="p" text={MATCHUPS.gridNote} className="mb-5 mt-2 text-sm leading-relaxed text-soft" />
          <SeatGrid mm={mm} />
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
            <Downloads rows={() => measureRows(measures, GRID_KEYS, [modeOf[mm]])} name={`whowins-matchups-${mm}`} />
            <CopyLink />
          </div>
        </section>
        <aside className="min-w-0 space-y-6">
          <section className="card p-5 sm:p-6" aria-labelledby="layouts-title">
            <h2 id="layouts-title" className="text-xl font-semibold">The operator line in four layouts</h2>
            <Rich as="p" text={MATCHUPS.layouts} className="mb-4 mt-2 text-sm leading-relaxed text-soft" />
            <Layouts mm={mm} />
          </section>
          <section className="rounded-2xl border border-line bg-raised/70 p-5 text-sm leading-relaxed text-soft">
            <Rich as="p" text={MATCHUPS.reading} />
          </section>
        </aside>
      </div>
      <section className="page mt-14" aria-labelledby="pairs-title">
        <h2 id="pairs-title" className="text-2xl font-semibold tracking-tight">Every model-mode, seat against seat</h2>
        <p className="mt-1 max-w-3xl text-sm text-soft">{MATCHUPS.pairsLead}</p>
        <div className="mt-6 grid gap-5 lg:grid-cols-3">
          {PANELS.map(([key, title]) => {
            const m = measures[key]
            const rows = modes.filter((x) => m.values[x.mm]).map((x) => ({ mode: x, v: m.values[x.mm] }))
            return (
              <figure key={key} className="card min-w-0 p-4">
                <figcaption className="mb-2 text-sm font-semibold text-ink">{title}</figcaption>
                <DotChart rows={rows} unit="rate" refAt={0.5} ticks={[0, 0.5, 1]} height={230} label={`${m.label}, per model-mode`} />
              </figure>
            )
          })}
        </div>
        <div className="mt-3"><Legend extra={[<span key="r">dashed: {NULL_SHARE}</span>, <span key="b">bars: {LEVEL} intervals</span>]} /></div>
      </section>
    </>
  )
}
