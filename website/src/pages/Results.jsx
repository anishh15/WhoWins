import MeasureExplorer from '../components/MeasureExplorer'
import ModeFilters, { useModeFilters } from '../components/ModeFilters'
import PageHeader from '../components/PageHeader'
import ResultsTable from '../components/ResultsTable'
import Rich from '../components/Rich'
import { CopyLink, Downloads } from '../components/Share'
import { DEFINITIONS, SCOPE } from '../content/findings'
import { RESULTS } from '../content/results'
import { LEVEL, NULL_SHARE, fill, table } from '../lib/data'
import { measureRows } from '../lib/download'
import { measures, modes } from '../lib/measures'
import { useTitle } from '../lib/hooks'
import { useQuery } from '../lib/url'

const KEYS = table.columns.map((c) => c.key)

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
      <span><span className="italic text-[rgb(var(--cell-grey))]">grey italic</span>: the {LEVEL} interval includes {NULL_SHARE} or zero</span>
    </div>
  )
}

export default function Results() {
  useTitle('Results')
  const filters = useModeFilters()
  const [{ sort: sortKey, dir, ci }, set] = useQuery({ sort: [KEYS, ''], dir: [['desc', 'asc'], 'desc'], ci: [['1'], ''] })
  const sort = { key: sortKey || null, dir }
  // A click sorts high to low, a second click low to high, a third restores the paper's order.
  const onSort = (key) => set(key !== sortKey ? { sort: key, dir: 'desc' } : dir === 'desc' ? { dir: 'asc' } : { sort: '', dir: 'desc' })
  const tableRows = () => measureRows(measures, KEYS, modes.filter(filters.shown))
  return (
    <>
      <PageHeader eyebrow="Results" title={RESULTS.title} lead={RESULTS.lead}>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <p className="rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-soft">{fill(RESULTS.badge)}</p>
          <Downloads rows={tableRows} name="whowins-table3" label="Download data" />
        </div>
      </PageHeader>

      <div className="z-30 border-b border-line bg-bg/95 lg:sticky lg:top-16">
        <div className="page flex flex-wrap items-center justify-between gap-3 py-3">
          <ModeFilters filters={filters} />
          <div className="flex flex-wrap items-center gap-3">
            <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-soft">
              <input type="checkbox" checked={ci === '1'} onChange={(e) => set({ ci: e.target.checked ? '1' : '' })} className="h-4 w-4 accent-[rgb(var(--accent))]" />
              Show {LEVEL} intervals in the table
            </label>
            <CopyLink />
          </div>
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
        <ResultsTable shown={filters.shown} showCi={ci === '1'} sort={sort} onSort={onSort} />
        <div className="mt-4 max-w-4xl space-y-2 text-xs leading-relaxed text-muted">
          <Rich as="p" text={DEFINITIONS} />
          <Rich as="p" text={SCOPE} />
        </div>
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
          <MeasureExplorer shown={filters.shown} />
        </div>
      </section>
    </>
  )
}
