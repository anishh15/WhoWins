import { FAMILIES, familyOf, modeName } from '../lib/data'
import { measures, modes } from '../lib/measures'
import { Hit, Marker, Plot, YAxis, checkDomain, linear, niceTicks, pctTicks, useTip } from './core'
import { TipBody } from './DotChart'

const STEP = 0.05
const down = (v) => Math.floor(v / STEP + 1e-9) * STEP
const up = (v) => Math.ceil(v / STEP - 1e-9) * STEP

/** Convex hull (monotone chain) of points, each first pushed out into a ring of the given radius. */
function hull(points, pad) {
  const ring = points.flatMap(([px, py]) =>
    Array.from({ length: 24 }, (_, i) => [px + pad * Math.cos((i * Math.PI) / 12), py + pad * Math.sin((i * Math.PI) / 12)]))
  ring.sort((a, b) => a[0] - b[0] || a[1] - b[1])
  const turn = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
  const chain = (ps) => {
    const out = []
    for (const p of ps) {
      while (out.length >= 2 && turn(out[out.length - 2], out[out.length - 1], p) <= 0) out.pop()
      out.push(p)
    }
    return out.slice(0, -1)
  }
  return [...chain(ring), ...chain([...ring].reverse())]
}

/** Figure 3: later line wins in free pairs (x) against the operator line's wins when first (y). */
export default function OrderScatter({ shown }) {
  const [tip, show, hide] = useTip()
  const later = measures.later_wins.values
  const op = measures.op_first.values
  const rows = modes.filter((m) => later[m.mm] && op[m.mm] && shown(m))
  const radius = (size) => 3 + 1.6 * Math.log10(size * 10)
  // Axes that hold every interval, in round steps; the paper's figure uses 45 to 95% by 0 to 85%.
  const XD = [down(Math.min(...rows.map((m) => later[m.mm].l))), up(Math.max(...rows.map((m) => later[m.mm].h)))]
  const YD = [0, up(Math.max(...rows.map((m) => op[m.mm].h)) + STEP / 2)]
  const LABEL = 'Per model-mode, how often the later line wins in free pairs against how often the operator line wins when it comes first'
  checkDomain(`${LABEL} (horizontal)`, rows.flatMap((m) => [later[m.mm].l, later[m.mm].h]), XD)
  checkDomain(`${LABEL} (vertical)`, rows.flatMap((m) => [op[m.mm].l, op[m.mm].h]), YD)
  return (
    <Plot height={340} margin={{ t: 12, r: 14, b: 46, l: 54 }} tip={tip} label={LABEL}>
      {({ w, h }) => {
        const x = linear(XD, [0, w])
        const y = linear(YD, [h, 0])
        return (
          <>
            <YAxis y={y} ticks={pctTicks(niceTicks(YD, 4))} w={w} h={h} label="operator line wins when first" />
            {niceTicks(XD, 5).map((v) => (
              <g key={v}>
                <line x1={x(v)} x2={x(v)} y1={0} y2={h} stroke="var(--chart-grid)" />
                <text x={x(v)} y={h + 16} textAnchor="middle" className="fill-[rgb(var(--muted))] text-[10.5px] num">{Math.round(v * 100)}%</text>
              </g>
            ))}
            <text x={w / 2} y={h + 36} textAnchor="middle" className="fill-[rgb(var(--soft))] text-[11px]">later line wins (user, tool, memory pairs)</text>
            <line x1={x(XD[0])} x2={x(XD[1])} y1={y(1 - XD[0])} y2={y(1 - XD[1])} stroke="var(--chart-ref)" strokeWidth={1.1} strokeDasharray="4 3" />
            <text x={x(XD[0] + 0.018)} y={y(1.012 - XD[0] - 0.018)} className="fill-[rgb(var(--accent))] text-[11px] italic"
              transform={`rotate(${(Math.atan2(y(0.4) - y(0.5), x(0.6) - x(0.5)) * 180) / Math.PI},${x(XD[0] + 0.018)},${y(1.012 - XD[0] - 0.018)})`}>
              1 − later wins
            </text>
            {FAMILIES.map((f) => {
              const pts = rows.filter((m) => m.family === f.key).map((m) => [x(later[m.mm].e), y(op[m.mm].e)])
              if (!pts.length) return null
              const poly = hull(pts, 16)
              const top = pts.reduce((a, b) => (b[1] < a[1] ? b : a))
              return (
                <g key={f.key}>
                  <path d={`M${poly.map((p) => p.join(',')).join('L')}Z`} fill={f.tint} stroke={f.edge} strokeOpacity={0.3} />
                  <text x={top[0]} y={top[1] - 22} textAnchor="middle" className="text-[11.5px] font-semibold" style={{ fill: f.text }}>{f.title}</text>
                </g>
              )
            })}
            {[...rows].sort((a, b) => b.size - a.size).map((m) => {
              const a = later[m.mm]
              const b = op[m.mm]
              const edge = familyOf[m.family].edge
              return (
                <Hit key={m.mm} x={x(a.e)} y={y(b.e)} show={show} hide={hide}
                  label={`${modeName(m)}: later wins ${a.t}, operator first ${b.t}`}
                  content={<TipBody mode={m} lines={[['Later wins', a], ['Operator first', b]]} />}>
                  <line x1={x(a.l)} x2={x(a.h)} y1={y(b.e)} y2={y(b.e)} stroke={edge} strokeOpacity={0.5} />
                  <line x1={x(a.e)} x2={x(a.e)} y1={y(b.l)} y2={y(b.h)} stroke={edge} strokeOpacity={0.5} />
                  <Marker x={x(a.e)} y={y(b.e)} family={m.family} hollow={m.mode === 'on'} r={radius(m.size)} />
                </Hit>
              )
            })}
          </>
        )
      }}
    </Plot>
  )
}
