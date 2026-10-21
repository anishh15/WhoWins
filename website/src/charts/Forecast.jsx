import { familyOf, modeName } from '../lib/data'
import { measures, modes } from '../lib/measures'
import { FamilyAxis, Hit, Marker, Plot, YAxis, linear, pctTicks, slots, useTip } from './core'
import { TipBody } from './DotChart'

/** Figure 5: share of the gap recovered by the position fit (bar), task-aware fit (tick) and seats fit (mark). */
export default function Forecast({ shown }) {
  const [tip, show, hide] = useTip()
  const pos = measures.share_position.values
  const task = measures.share_task.values
  const seats = measures.share_seats.values
  const rows = modes.filter((m) => pos[m.mm] && task[m.mm] && seats[m.mm] && shown(m))
  const { xs, ticks, groups, extent } = slots(rows, { offset: 0.2 })
  return (
    <Plot height={300} margin={{ t: 12, r: 10, b: 42, l: 54 }} tip={tip}
      label="Share of the gap from a uniform guess to the empirical reference recovered by the position, task-aware and seats fits, per model-mode">
      {({ w, h }) => {
        const x = linear(extent, [0, w])
        const y = linear([0, 1], [h, 0])
        const bw = Math.max(3, Math.min(9, (x(1) - x(0)) * 0.3))
        return (
          <>
            <YAxis y={y} ticks={pctTicks([0, 0.25, 0.5, 0.75, 1])} w={w} h={h} label="share of gap recovered" />
            <FamilyAxis x={x} h={h} ticks={ticks} groups={groups} />
            {rows.map((m) => {
              const cx = x(xs[m.mm])
              const [p, t, s] = [pos[m.mm], task[m.mm], seats[m.mm]]
              return (
                <Hit key={m.mm} x={cx} y={y(s.e)} show={show} hide={hide}
                  label={`${modeName(m)}: position ${p.t}, task-aware ${t.t}, seats ${s.t}`}
                  content={<TipBody mode={m} lines={[['Position fit', p], ['Task-aware fit', t], ['Seats fit', s]]} />}>
                  <rect x={cx - bw / 2} y={y(p.e)} width={bw} height={y(0) - y(p.e)} fill="var(--chart-bar)" />
                  <line x1={cx - bw / 2 - 1} x2={cx + bw / 2 + 1} y1={y(t.e)} y2={y(t.e)} stroke="rgb(var(--ink))" strokeWidth={1.6} />
                  <line x1={cx} x2={cx} y1={y(p.e)} y2={y(s.e)} stroke={familyOf[m.family].edge} strokeWidth={1.1} />
                  <Marker x={cx} y={y(s.e)} family={m.family} hollow={m.mode === 'on'} r={3.6} />
                </Hit>
              )
            })}
          </>
        )
      }}
    </Plot>
  )
}
