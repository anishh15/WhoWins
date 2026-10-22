import { useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { FAMILIES, familyOf } from '../lib/data'
import { useSeenOnce, useWidth } from '../lib/hooks'

/** A linear scale from [d0, d1] to [r0, r1]. */
export const linear = ([d0, d1], [r0, r1]) => (v) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0)

/** The round step that splits a span into about count parts. */
function niceStep(span, count) {
  const raw = span / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  return [1, 2, 2.5, 5, 10].map((s) => s * mag).find((s) => s >= raw)
}

/** Tick values for a domain: about count round steps. */
export function niceTicks([lo, hi], count = 5) {
  const step = niceStep(hi - lo, count)
  const out = []
  for (let v = Math.ceil(lo / step - 1e-9) * step; v <= hi + step * 1e-6; v += step) out.push(+v.toFixed(10))
  return out
}

/** The domain widened outwards to round steps, so its ends are ticks and every value stays inside. */
export function niceDomain([lo, hi], count = 5) {
  const step = niceStep(hi - lo, count)
  return [+(Math.floor(lo / step + 1e-9) * step).toFixed(10), +(Math.ceil(hi / step - 1e-9) * step).toFixed(10)]
}

/** Report, as a console error, any value a chart would draw outside its axis. */
export function checkDomain(label, values, [lo, hi]) {
  const out = values.filter((v) => v != null && (v < lo - 1e-9 || v > hi + 1e-9))
  if (out.length) console.error(`Chart "${label}": ${out.length} value(s) outside the axis [${lo}, ${hi}]`)
}

/** Percent tick labels from a list of shares. */
export const pctTicks = (ticks, signed = false) =>
  ticks.map((t) => {
    const v = Math.round(t * 100)
    return [t, `${signed && v > 0 ? '+' : ''}${v}%`.replace('-', '−')]
  })

/**
 * x positions as in the paper's figures: families in order, models by size, thinking off left of
 * the size tick and on right of it. Returns positions, size ticks, family groups and the extent.
 */
export function slots(modes, { gap = 0.55, offset = 0.22 } = {}) {
  const xs = {}
  const ticks = []
  const groups = []
  let x = 0
  for (const fam of FAMILIES) {
    const models = [...new Map(modes.filter((m) => m.family === fam.key).sort((a, b) => a.size - b.size).map((m) => [m.model, m])).values()]
    if (!models.length) continue
    const x0 = x
    for (const model of models) {
      const own = modes.filter((m) => m.model === model.model)
      for (const m of own) xs[m.mm] = x + (own.length === 1 ? 0 : offset * (m.mode === 'on' ? 1 : -1))
      ticks.push([x, String(model.size)])
      x += 1
    }
    groups.push([x0, x - 1, fam.key])
    x += gap
  }
  return { xs, ticks, groups, extent: [-0.5, x - gap - 0.5] }
}

/** Tooltip state for a chart: show(x, y, content) in plot coordinates, hide(). */
export function useTip() {
  const [tip, setTip] = useState(null)
  return [tip, (x, y, content) => setTip({ x, y, content }), () => setTip(null)]
}

/**
 * A responsive SVG plot with margins and an HTML tooltip layer; children({ w, h }) draws inside the margins.
 * It fades and rises in once, the first time it scrolls into view (not with reduced motion).
 */
export function Plot({ height, margin, label, tip, minWidth = 300, children }) {
  const [ref, width] = useWidth()
  const [seenRef, seen] = useSeenOnce(useReducedMotion())
  const full = Math.max(width, minWidth)
  const w = full - margin.l - margin.r
  const h = height - margin.t - margin.b
  const left = tip ? Math.min(Math.max(tip.x + margin.l, 90), full - 90) : 0
  return (
    <div ref={ref} className="relative w-full min-w-0">
      <div ref={seenRef} className={`transition-[opacity,transform] duration-700 ease-out ${seen ? 'opacity-100' : 'translate-y-2 opacity-0'}`}>
        <svg width={full} height={height} role="img" aria-label={label} className="block overflow-visible font-sans">
          <g transform={`translate(${margin.l},${margin.t})`}>{children({ w, h })}</g>
        </svg>
      </div>
      {tip && (
        <div
          className="pointer-events-none absolute left-0 top-0 z-20 w-max max-w-[15rem] rounded-lg border border-line bg-surface px-3 py-2 text-xs leading-snug text-ink shadow-lift"
          style={{ transform: `translate(${left}px, ${tip.y + margin.t - 12}px) translate(-50%, -100%)` }}
          role="status"
        >
          {tip.content}
        </div>
      )}
    </div>
  )
}

/** A family mark: circle, square or triangle; filled for thinking off, hollow for on, grey when faded. */
export function Marker({ x, y, family, hollow, faded, r = 4.2 }) {
  const fam = familyOf[family]
  const stroke = faded ? 'var(--chart-faded)' : fam.edge
  const fill = hollow ? 'rgb(var(--surface))' : faded ? 'var(--chart-faded)' : fam.mark
  const common = { fill, stroke, strokeWidth: 1.3 }
  if (fam.shape === 'square') {
    const s = r * 1.62
    return <rect x={x - s / 2} y={y - s / 2} width={s} height={s} {...common} />
  }
  if (fam.shape === 'triangle') {
    const t = r * 1.25
    return <polygon points={`${x},${y - t * 1.1} ${x + t},${y + t * 0.75} ${x - t},${y + t * 0.75}`} {...common} />
  }
  return <circle cx={x} cy={y} r={r} {...common} />
}

/** An invisible, focusable hit area around a mark that shows its tooltip on hover or focus. */
export function Hit({ x, y, label, show, hide, content, children }) {
  const open = () => show(x, y, content)
  return (
    <g tabIndex={0} role="img" aria-label={label} onMouseEnter={open} onFocus={open} onMouseLeave={hide} onBlur={hide} className="cursor-default outline-none [&:focus-visible>circle:first-child]:stroke-[rgb(var(--accent))]">
      <circle cx={x} cy={y} r={11} fill="transparent" stroke="transparent" strokeWidth={1.5} />
      {children}
    </g>
  )
}

/** Horizontal gridlines with labels on the left. */
export function YAxis({ y, ticks, w, label, h }) {
  return (
    <g>
      {ticks.map(([v, text]) => (
        <g key={v}>
          <line x1={0} x2={w} y1={y(v)} y2={y(v)} stroke="var(--chart-grid)" strokeWidth={1} />
          <text x={-8} y={y(v)} dy="0.32em" textAnchor="end" className="fill-[rgb(var(--muted))] text-[10.5px] num">
            {text}
          </text>
        </g>
      ))}
      {label && (
        <text transform={`translate(${-44},${h / 2}) rotate(-90)`} textAnchor="middle" className="fill-[rgb(var(--soft))] text-[11px]">
          {label}
        </text>
      )}
    </g>
  )
}

/** A dashed reference line (50% or zero), as in the paper. */
export function RefLine({ y, w }) {
  return <line x1={0} x2={w} y1={y} y2={y} stroke="var(--chart-ref)" strokeWidth={1.1} strokeDasharray="4 3" />
}

/** Size ticks (when there is room) and family names under a slot chart, the axis broken between families. */
export function FamilyAxis({ x, h, ticks, groups, labels = true }) {
  return (
    <g transform={`translate(0,${h})`}>
      {groups.map(([x0, x1, fam]) => (
        <g key={fam}>
          <line x1={x(x0 - 0.42)} x2={x(x1 + 0.42)} y1={0} y2={0} stroke="rgb(var(--soft))" strokeWidth={0.8} />
          {labels && (
            <text x={(x(x0) + x(x1)) / 2} y={32} textAnchor="middle" className="text-[11px] font-semibold" style={{ fill: familyOf[fam].text }}>
              {familyOf[fam].title}
            </text>
          )}
        </g>
      ))}
      {labels && x(1) - x(0) >= 20 && ticks.map(([v, text]) => (
        <text key={v} x={x(v)} y={15} textAnchor="middle" className="fill-[rgb(var(--muted))] text-[10px] num">
          {text}
        </text>
      ))}
    </g>
  )
}

/** The legend shared by the figures: family marks and the filled/hollow convention. */
export function Legend({ extra = [] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-soft">
      {FAMILIES.map((f) => (
        <span key={f.key} className="inline-flex items-center gap-1.5">
          <svg width="14" height="14" aria-hidden="true"><Marker x={7} y={7} family={f.key} r={4} /></svg>
          {f.title}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5">
        <svg width="26" height="14" aria-hidden="true">
          <circle cx={6} cy={7} r={4} fill="rgb(var(--ink))" stroke="rgb(var(--ink))" strokeWidth={1.2} />
          <circle cx={19} cy={7} r={4} fill="rgb(var(--surface))" stroke="rgb(var(--ink))" strokeWidth={1.2} />
        </svg>
        thinking off / on
      </span>
      {extra}
    </div>
  )
}
