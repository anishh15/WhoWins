import { Link } from 'react-router-dom'
import ChartCard from '../components/ChartCard'
import Contents, { BackToTop } from '../components/Contents'
import Insight from '../components/Insight'
import PageHeader from '../components/PageHeader'
import Rich from '../components/Rich'
import { FINDING_CHARTS } from '../charts/FindingCharts'
import { DEFINITIONS, IMPLICATIONS, INSIGHTS, SCOPE } from '../content/findings'
import { useTitle } from '../lib/hooks'

const CONTENTS = [...INSIGHTS.map((ins) => [ins.id, ins.claim.replace(/\.$/, '')]), ['implications', 'Implications']]

export default function Findings() {
  useTitle('Findings')
  return (
    <>
      <PageHeader
        eyebrow="Findings"
        title="The study’s findings"
        lead="Each finding as the paper states it, with a chart drawn from the same data as the paper’s figure."
      />
      <div className="page mt-8 space-y-4">
        <div className="max-w-4xl space-y-2 rounded-xl border border-line bg-raised/70 px-4 py-3 text-sm leading-relaxed text-soft">
          <Rich as="p" text={DEFINITIONS} />
          <Rich as="p" text={SCOPE} className="text-muted" />
        </div>
        <Contents route="findings" items={CONTENTS} />
      </div>
      <div className="page">
        {INSIGHTS.map((ins, i) => {
          const c = FINDING_CHARTS[ins.chart]()
          return (
            <section key={ins.id} id={ins.id} className="scroll-mt-24 border-b border-line py-12">
              {ins.section && <p className="eyebrow mb-4">{ins.section}</p>}
              <div className="grid gap-8 lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.15fr)] lg:items-start">
                <div className="min-w-0">
                  <Insight number={`${i + 1}`} claim={ins.claim} bold={ins.bold} evidence={ins.evidence} details={ins.details} />
                </div>
                <div className="min-w-0 lg:sticky lg:top-24">
                  <ChartCard title={c.title} chart={c.chart} table={c.table} legend={c.legend} figure={ins.figure} rows={c.rows} name={`whowins-${ins.id}`} />
                </div>
              </div>
              <BackToTop />
            </section>
          )
        })}
        <section id="implications" className="scroll-mt-24 py-12">
          <p className="eyebrow mb-3">Implications</p>
          <h2 className="text-3xl font-semibold tracking-tight">Practices for agent builders and benchmark designers</h2>
          <ol className="mt-6 grid gap-4 md:grid-cols-2">
            {IMPLICATIONS.map((text, i) => (
              <li key={i} className="card flex gap-4 p-5">
                <span className="font-serif text-lg font-semibold italic text-accent">({['i', 'ii', 'iii', 'iv', 'v', 'vi'][i]})</span>
                <Rich text={text} className="leading-relaxed text-soft" />
              </li>
            ))}
          </ol>
          <p className="mt-8 text-sm text-soft">
            Every number above is also in the <Link to="/results" className="link">results dashboard</Link>, with its interval.
          </p>
          <BackToTop />
        </section>
      </div>
    </>
  )
}
