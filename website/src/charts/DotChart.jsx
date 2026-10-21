import { familyOf, modeName } from '../lib/data'
import { FamilyAxis, Hit, Marker, Plot, RefLine, YAxis, linear, slots, useTip } from './core'

/** Tick values for a domain: about five round steps. */
export function niceTicks([lo, hi], count = 5) {
  const raw = (hi - lo) / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((s) => s * mag).find((s) => s >= raw)
  const out = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-6; v += step) out.push(+v.toFixed(10))
  return out
}

/** A domain that holds every interval, padded and widened to round ticks. */
function domainOf(values, unit) {
  if (unit === 'rate') return [0, 1]
  const lo = Math.min(0, ...values)
  const hi = Math.max(0, ...values)
  const pad = (hi - lo) * 0.08 || 0.05
  const ticks = niceTicks([lo - pad, hi + pad])
  return [Math.min(ticks[0], lo - pad), Math.max(ticks[ticks.length - 1], hi + pad)]
}

/** Tick labels for a measure's unit: percent for rates and differences, nats as numbers. */
function tickLabels(ticks, unit) {
  return ticks.map((t) => {
    if (unit === 'nats') return [t, `${t > 0 ? '+' : ''}${t.toFixed(2)}`.replace('-', '−')]
    const v = Math.round(t * 100)
    return [t, `${unit === 'diff' && v > 0 ? '+' : ''}${v}%`.replace('-', '−')]
  })
}

/** Tooltip body: the model-mode, then label / value / interval lines. */
export function TipBody({ mode, lines }) {
  return (
    <>
      <p className="font-semibold text-ink">{modeName(mode)}</p>
      {lines.map(([label, v]) => v && (
        <p key={label} className="mt-0.5 text-soft">
          {label && <span>{label}: </span>}
          <span className="num font-semibold text-ink">{v.t}</span>
          {v.c && <span className="num text-muted"> {v.c}</span>}
        </p>
      ))}
    </>
  )
}

/**
 * One value per model-mode as a family mark with its 95% interval, laid out like the paper's
 * figures. rows: [{ mode, v, D?, H?, tick? }]; halves draws the two halves beside each other.
 */
export default function DotChart({ rows, unit, refAt, yLabel, label, height = 280, halves = false, domain, ticks, tickLabel = 'all task types', compact = false }) {
  const [tip, show, hide] = useTip()
  const { xs, ticks: sizes, groups, extent } = slots(rows.map((r) => r.mode))
  const values = rows.flatMap((r) => [r.v, r.D, r.H, r.tick].filter(Boolean).flatMap((v) => [v.l ?? v.e, v.h ?? v.e]))
  const dom = domain || domainOf(values, unit)
  const yTicks = ticks || niceTicks(dom)
  const margin = { t: 12, r: 10, b: compact ? 12 : 42, l: 54 }
  return (
    <Plot height={height} margin={margin} label={label} tip={tip}>
      {({ w, h }) => {
        const x = linear(extent, [0, w])
        const y = linear(dom, [h, 0])
        const marks = (v, cx, r, mode, hollow, faded) => (
          <>
            {v.l != null && <line x1={cx} x2={cx} y1={y(v.l)} y2={y(v.h)} stroke={faded ? 'var(--chart-faded)' : familyOf[mode.family].edge} strokeWidth={1.1} />}
            <Marker x={cx} y={y(v.e)} family={mode.family} hollow={hollow} faded={faded} r={r} />
          </>
        )
        return (
          <>
            <YAxis y={y} ticks={tickLabels(yTicks, unit)} w={w} h={h} label={yLabel} />
            {refAt != null && <RefLine y={y(refAt)} w={w} />}
            <FamilyAxis x={x} h={h} ticks={sizes} groups={groups} labels={!compact} />
            {rows.map((r) => {
              const cx = x(xs[r.mode.mm])
              const hollow = r.mode.mode === 'on'
              const lines = halves
                ? [['All', r.v], ['Discovery half', r.D], ['Held-out half', r.H]]
                : [['', r.v], ...(r.tick ? [[tickLabel, r.tick]] : [])]
              return (
                <Hit key={r.mode.mm} x={cx} y={y(r.v.e)} label={`${modeName(r.mode)}: ${r.v.t}`} show={show} hide={hide} content={<TipBody mode={r.mode} lines={lines} />}>
                  {r.tick && <line x1={cx - 5} x2={cx + 5} y1={y(r.tick.e)} y2={y(r.tick.e)} stroke="var(--chart-faded)" strokeWidth={2} />}
                  {halves && r.D && r.H ? (
                    <>
                      {marks(r.D, cx - 3.2, 2.9, r.mode, hollow)}
                      {marks(r.H, cx + 3.2, 2.9, r.mode, true, true)}
                    </>
                  ) : marks(r.v, cx, 3.9, r.mode, hollow)}
                </Hit>
              )
            })}
          </>
        )
      }}
    </Plot>
  )
}
