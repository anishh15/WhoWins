import { familyOf, modeName } from '../lib/data'
import { measures, modes } from '../lib/measures'
import { FamilyAxis, Hit, Marker, Plot, RefLine, YAxis, checkDomain, linear, pctTicks, slots, useTip } from './core'
import { TipBody } from './DotChart'

/** Figure 2: the first-listed line inside one message (upper point) and across two (lower point). */
export default function Boundary({ shown }) {
  const [tip, show, hide] = useTip()
  const merged = measures.first_merged.values
  const separate = measures.first_separate.values
  const rows = modes.filter((m) => merged[m.mm] && separate[m.mm] && shown(m))
  const { xs, ticks, groups, extent } = slots(rows)
  const LABEL = 'Share of decided replies that follow the first-listed of two lines, inside one message and in two messages, per model-mode'
  checkDomain(LABEL, rows.flatMap((m) => [merged[m.mm], separate[m.mm]].flatMap((v) => [v.e, v.l, v.h])), [0, 1])
  return (
    <Plot height={300} margin={{ t: 14, r: 10, b: 42, l: 54 }} tip={tip} label={LABEL}>
      {({ w, h }) => {
        const x = linear(extent, [0, w])
        const y = linear([0, 1], [h, 0])
        return (
          <>
            <YAxis y={y} ticks={pctTicks([0, 0.25, 0.5, 0.75, 1])} w={w} h={h} label="first-listed line wins" />
            <RefLine y={y(0.5)} w={w} />
            <FamilyAxis x={x} h={h} ticks={ticks} groups={groups} />
            <text x={6} y={y(1) + 12} className="fill-[rgb(var(--accent))] text-[11px] italic">both lines in one message</text>
            <text x={6} y={y(0.06)} className="fill-[rgb(var(--accent))] text-[11px] italic">each line in its own message</text>
            {rows.map((m) => {
              const cx = x(xs[m.mm])
              const a = merged[m.mm]
              const b = separate[m.mm]
              const edge = familyOf[m.family].edge
              return (
                <Hit key={m.mm} x={cx} y={y(a.e)} show={show} hide={hide}
                  label={`${modeName(m)}: one message ${a.t}, separate ${b.t}`}
                  content={<TipBody mode={m} lines={[['One message', a], ['Separate messages', b]]} />}>
                  <line x1={cx} x2={cx} y1={y(b.e)} y2={y(a.e)} stroke={edge} strokeOpacity={0.3} strokeWidth={1.4} />
                  {[a, b].map((v, i) => (
                    <g key={i}>
                      <line x1={cx} x2={cx} y1={y(v.l)} y2={y(v.h)} stroke={edge} strokeWidth={1.1} />
                      <Marker x={cx} y={y(v.e)} family={m.family} hollow={m.mode === 'on'} r={3.9} />
                    </g>
                  ))}
                </Hit>
              )
            })}
          </>
        )
      }}
    </Plot>
  )
}
