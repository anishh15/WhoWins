import { Fragment, useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import { FAMILIES, LEVEL, NULL_SHARE, familyOf, modeName, table } from '../lib/data'
import ScrollBox from './ScrollBox'
import { measures, modeOf } from '../lib/measures'

/** The paper's cell shading: red k% or blue k% over the page, as xcolor mixes it over white. */
const shade = (s) => (s ? `rgb(var(--heat-${s[0] === 'r' ? 'red' : 'blue'}) / ${s[1] / 100})` : undefined)
const numeric = (t) => (t === 'n/a' ? null : parseFloat(t.replace('−', '-')))

function Tip({ tip }) {
  const { row, col, x, y } = tip
  const m = measures[col.key]
  const v = m.values[row.mm]
  return (
    <div className="pointer-events-none absolute left-0 top-0 z-30 w-max max-w-[16rem] rounded-lg border border-line bg-surface px-3 py-2 text-xs leading-snug shadow-lift" style={{ transform: `translate(${x}px, ${y - 8}px) translate(-50%, -100%)` }} role="status">
      <p className="font-semibold text-ink">{modeName(modeOf[row.mm])}</p>
      <p className="text-muted">{m.label}</p>
      {v ? (
        <>
          <p className="mt-1 text-soft"><span className="num font-semibold text-ink">{v.t}</span>{v.c && <span className="num text-muted"> {v.c}</span>}</p>
          {v.D && <p className="text-soft">Discovery half <span className="num text-ink">{v.D.t}</span>, held-out half <span className="num text-ink">{v.H?.t}</span></p>}
          {v.g && <p className="mt-1 italic text-muted">The {LEVEL} interval includes {m.null === 0 ? 'zero' : NULL_SHARE}.</p>}
        </>
      ) : (
        <p className="mt-1 text-soft">Not possible: the template rejects a late system message.</p>
      )}
    </div>
  )
}

function SortButton({ col, sort, onSort }) {
  const active = sort.key === col.key
  const Icon = !active ? ArrowUpDown : sort.dir === 'desc' ? ArrowDown : ArrowUp
  return (
    <button type="button" onClick={() => onSort(col.key)} className="group inline-flex flex-col items-end gap-0.5 text-right leading-tight hover:text-accent" aria-label={`Sort by ${measures[col.key].label}`}>
      {col.head.map((line) => <span key={line}>{line}</span>)}
      <Icon size={12} className={active ? 'text-accent' : 'text-muted opacity-60 group-hover:opacity-100'} aria-hidden="true" />
    </button>
  )
}

/**
 * Table 3 of the paper: every value exactly as the paper prints it, with its shading and grey marks.
 * Hover a cell for its interval and the two halves. sort is { key, dir } (key null: the paper's order).
 */
export default function ResultsTable({ shown, showCi, sort, onSort }) {
  const [tip, setTip] = useState(null)
  const wrap = useRef(null)
  const cols = table.columns
  const groups = cols.reduce((acc, c) => {
    const last = acc[acc.length - 1]
    if (last && last.name === c.group) last.span += 1
    else acc.push({ name: c.group, span: 1 })
    return acc
  }, [])

  const rows = useMemo(() => {
    const visible = table.rows.filter((r) => shown(modeOf[r.mm]))
    if (!sort.key) return visible
    const i = cols.findIndex((c) => c.key === sort.key)
    const sign = sort.dir === 'desc' ? -1 : 1
    return [...visible].sort((a, b) => {
      const va = numeric(a.cells[i].t)
      const vb = numeric(b.cells[i].t)
      if (va === null) return 1
      if (vb === null) return -1
      return sign * (va - vb)
    })
  }, [shown, sort, cols])

  const hover = (row, col, e) => {
    const cell = e.currentTarget.getBoundingClientRect()
    const box = wrap.current.getBoundingClientRect()
    setTip({ row, col, x: cell.left - box.left + cell.width / 2, y: cell.top - box.top })
  }

  const body = (row, prev, banded) => {
    const m = modeOf[row.mm]
    const first = !banded || !prev || modeOf[prev.mm].model !== m.model
    return (
      <tr key={row.mm} className="border-b border-line/60 last:border-0 hover:bg-wash/60">
        <th scope="row" className="sticky left-0 z-10 whitespace-nowrap bg-surface px-3 py-1.5 text-left font-medium text-ink">
          {first ? (
            <span className="inline-flex items-center gap-2">
              {!banded && <span className="h-2 w-2 rounded-full" style={{ background: familyOf[m.family].mark }} aria-hidden="true" />}
              {m.display}
            </span>
          ) : <span className="sr-only">{m.display}</span>}
        </th>
        <td className="px-2 py-1.5 text-center text-muted">{m.mode}</td>
        {row.cells.map((c, j) => {
          const v = measures[cols[j].key].values[row.mm]
          return (
            <td key={cols[j].key} className="num px-2.5 py-1.5 text-right" style={{ background: shade(c.s) }}
              onMouseEnter={(e) => hover(row, cols[j], e)} onMouseLeave={() => setTip(null)}>
              <span className={c.g ? 'italic text-[rgb(var(--cell-grey))]' : 'text-ink'}>{c.t}</span>
              {showCi && v?.c && <span className="block text-[0.68rem] leading-tight text-muted">{v.c}</span>}
            </td>
          )
        })}
      </tr>
    )
  }

  return (
    <div ref={wrap} className="relative">
      <ScrollBox label="Main results table" className="rounded-2xl border border-line bg-surface shadow-card">
      <table className="w-full min-w-[60rem] border-collapse text-[0.82rem]" aria-label="Who wins, per model-mode (Table 3 of the paper)">
        <thead>
          <tr className="bg-tint/70 text-[0.72rem] font-semibold uppercase tracking-wide text-accent">
            <td colSpan={2} className="sticky left-0 z-10 bg-tint/95" />
            {groups.map((g) => (
              <th key={g.name} colSpan={g.span} scope="colgroup" className="border-l border-surface/70 px-2 py-2 text-center">{g.name}</th>
            ))}
          </tr>
          <tr className="border-b border-rule bg-tint/40 text-[0.75rem] font-semibold text-soft">
            <th scope="col" className="sticky left-0 z-10 bg-[rgb(var(--wash))] px-3 py-2 text-left">Model</th>
            <th scope="col" className="px-2 py-2">Think</th>
            {cols.map((c) => (
              <th key={c.key} scope="col" className="px-2.5 py-2 text-right align-bottom" aria-sort={sort.key === c.key ? (sort.dir === 'desc' ? 'descending' : 'ascending') : 'none'}>
                <SortButton col={c} sort={sort} onSort={onSort} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sort.key
            ? rows.map((r) => body(r, null, false))
            : FAMILIES.map((f) => {
              const own = rows.filter((r) => modeOf[r.mm].family === f.key)
              if (!own.length) return null
              return (
                <Fragment key={f.key}>
                  <tr className="bg-wash">
                    <th colSpan={2 + cols.length} scope="rowgroup" className="sticky left-0 px-3 py-1.5 text-left font-serif text-[0.9rem] font-semibold italic" style={{ color: f.text }}>
                      {f.title}
                    </th>
                  </tr>
                  {own.map((r, i) => body(r, own[i - 1], true))}
                </Fragment>
              )
            })}
        </tbody>
      </table>
      </ScrollBox>
      {tip && <Tip tip={tip} />}
    </div>
  )
}
