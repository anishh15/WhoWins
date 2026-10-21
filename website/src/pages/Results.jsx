import { useState } from 'react'
import { CheckCircle2 } from 'lucide-react'
import MeasureExplorer from '../components/MeasureExplorer'
import ModeFilters, { filterOf } from '../components/ModeFilters'
import PageHeader from '../components/PageHeader'
import ResultsTable from '../components/ResultsTable'
import Rich from '../components/Rich'
import { DEFINITIONS } from '../content/findings'
import { RESULTS } from '../content/results'
import { table } from '../lib/data'
import { measures } from '../lib/measures'
import { useTitle } from '../lib/hooks'

function ShadeKey() {
  const steps = [5, 15, 25, 35]
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-soft">
      <span className="inline-flex items-center gap-1.5">
        {steps.map((k) => <span key={k} className="h-3.5 w-5 rounded-sm" style={{ background: `rgb(var(--heat-red) / ${k / 100})` }} />)}
        larger rates and positive differences
      </span>
      <span className="inline-flex items-center gap-1.5">
        {steps.slice(0, 3).map((k) => <span key={k} className="h-3.5 w-5 rounded-sm" style={{ background: `rgb(var(--heat-blue) / ${k / 100})` }} />)}
        negative differences
      </span>
      <span><span className="italic text-[rgb(var(--cell-grey))]">grey italic</span>: the 95% interval includes 50% or 0</span>
    </div>
  )
}

export default function Results() {
  useTitle('Results')
  const [filters, setFilters] = useState({ family: 'all', think: 'all' })
  const [showCi, setShowCi] = useState(false)
  const shown = filterOf(filters)
  return (
    <>
      <PageHeader eyebrow="Results" title={RESULTS.title} lead={RESULTS.lead}>
        <p className="mt-5 inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-soft">
          <CheckCircle2 size={14} className="text-accent" aria-hidden="true" />
          {RESULTS.checked.replace('CELLS', table.checked.toLocaleString('en-US'))}
        </p>
      </PageHeader>

      <div className="z-30 border-b border-line bg-bg/90 backdrop-blur-md lg:sticky lg:top-16">
        <div className="page flex flex-wrap items-center justify-between gap-3 py-3">
          <ModeFilters value={filters} onChange={setFilters} />
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-soft">
            <input type="checkbox" checked={showCi} onChange={(e) => setShowCi(e.target.checked)} className="h-4 w-4 accent-[rgb(var(--accent))]" />
            Show 95% intervals in the table
          </label>
        </div>
      </div>

      <section className="page mt-10" aria-labelledby="table-title">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 id="table-title" className="text-2xl font-semibold tracking-tight">{RESULTS.tableTitle}</h2>
            <p className="mt-1 max-w-2xl text-sm text-soft">{RESULTS.tableLead}</p>
          </div>
          <ShadeKey />
        </div>
        <ResultsTable shown={shown} showCi={showCi} />
        <Rich as="p" text={DEFINITIONS} className="mt-4 max-w-4xl text-xs leading-relaxed text-muted" />
      </section>

      <section className="page mt-12" aria-labelledby="glossary-title">
        <h2 id="glossary-title" className="text-2xl font-semibold tracking-tight">What each column measures</h2>
        <dl className="mt-5 grid gap-x-8 gap-y-4 sm:grid-cols-2">
          {table.columns.map((c) => (
            <div key={c.key} className="border-l-2 border-blush pl-4">
              <dt className="text-sm font-semibold text-ink">{c.head.join(' ')} <span className="font-normal text-muted">· {c.group}</span></dt>
              <Rich as="dd" text={measures[c.key].desc} className="mt-1 text-sm leading-relaxed text-soft" />
            </div>
          ))}
        </dl>
      </section>

      <section id="explorer" className="page mt-14" aria-labelledby="explorer-title">
        <h2 id="explorer-title" className="text-2xl font-semibold tracking-tight">{RESULTS.explorerTitle}</h2>
        <p className="mt-1 max-w-3xl text-sm text-soft">{RESULTS.explorerLead}</p>
        <div className="mt-5">
          <MeasureExplorer shown={shown} />
        </div>
      </section>
    </>
  )
}
