import { familyOf } from '../lib/data'
import { FamilyAxis, Hit, Marker, Plot, YAxis, checkDomain, linear, pctTicks, slots, useTip } from './core'

const SIDE = 0.17

/** One panel of Figure 6: thinking off (filled, left) to on (hollow, right) per Qwen size; grey when the change's interval includes zero. */
export default function Thinking({ rows, domain, ticks, label, yLabel }) {
  const [tip, show, hide] = useTip()
  const sizes = rows.map((r) => ({ mm: r.model, model: r.model, family: r.family, size: r.size, mode: 'off' }))
  const { xs, ticks: sizeTicks, groups, extent } = slots(sizes)
  checkDomain(label, rows.flatMap((r) => [r.off, r.on]), domain)
  return (
    <Plot height={250} margin={{ t: 12, r: 10, b: 42, l: 54 }} tip={tip} label={label}>
      {({ w, h }) => {
        const x = linear(extent, [0, w])
        const y = linear(domain, [h, 0])
        return (
          <>
            <YAxis y={y} ticks={pctTicks(ticks)} w={w} h={h} label={yLabel} />
            <FamilyAxis x={x} h={h} ticks={sizeTicks} groups={groups} />
            {rows.map((r) => {
              const cx = x(xs[r.model])
              const dx = x(SIDE) - x(0)
              const faded = Boolean(r.g)
              return (
                <Hit key={r.model} x={cx} y={y(r.on)} show={show} hide={hide}
                  label={`${r.display}: thinking off ${r.offText}, on ${r.onText}, change ${r.t}`}
                  content={(
                    <>
                      <p className="font-semibold text-ink">{r.display}</p>
                      <p className="mt-0.5 text-soft">Off <span className="num font-semibold text-ink">{r.offText}</span>, on <span className="num font-semibold text-ink">{r.onText}</span></p>
                      <p className="text-soft">Change <span className="num font-semibold text-ink">{r.t}</span> <span className="num text-muted">{r.c}</span></p>
                    </>
                  )}>
                  <line x1={cx - dx} x2={cx + dx} y1={y(r.off)} y2={y(r.on)} stroke={faded ? 'var(--chart-faded)' : familyOf[r.family].edge} strokeWidth={1.2} />
                  <Marker x={cx - dx} y={y(r.off)} family={r.family} faded={faded} r={4} />
                  <Marker x={cx + dx} y={y(r.on)} family={r.family} hollow faded={faded} r={4} />
                </Hit>
              )
            })}
          </>
        )
      }}
    </Plot>
  )
}
