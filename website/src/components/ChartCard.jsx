import { useState } from 'react'
import Segmented from './Segmented'
import Rich from './Rich'
import { site } from '../lib/data'
import { useFigure } from '../lib/figures'

const figureOf = (key) => site.figures.find((f) => f.key === key)

function PaperFigure({ fig, title }) {
  const src = useFigure(fig.file)
  return (
    <div>
      <img src={src} alt={`The paper's figure: ${title}`} className="mx-auto w-full max-w-lg rounded-lg bg-white p-2 dark:bg-transparent" loading="lazy" />
      <Rich as="p" text={fig.caption} className="mt-3 text-xs leading-relaxed text-muted" />
    </div>
  )
}

/**
 * A chart with two alternate views: its data as a table, and the paper's own figure.
 * figure is a figure key such as "2_message_boundary"; legend sits under the chart.
 */
export default function ChartCard({ title, chart, table, legend, figure }) {
  const [view, setView] = useState('chart')
  const fig = figure && figureOf(figure)
  const options = [{ value: 'chart', label: 'Chart' }, { value: 'table', label: 'Table' }, ...(fig ? [{ value: 'paper', label: 'Paper figure' }] : [])]
  return (
    <figure className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-raised/70 px-4 py-2.5">
        <figcaption className="text-sm font-semibold text-ink">{title}</figcaption>
        <Segmented label={`${title}: view`} options={options} value={view} onChange={setView} size="sm" />
      </div>
      <div className="p-4">
        {view === 'chart' && (
          <>
            {chart}
            {legend && <div className="mt-3">{legend}</div>}
          </>
        )}
        {view === 'table' && table}
        {view === 'paper' && <PaperFigure fig={fig} title={title} />}
      </div>
    </figure>
  )
}
