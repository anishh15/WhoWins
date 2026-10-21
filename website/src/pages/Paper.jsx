import { BookOpen } from 'lucide-react'
import CodeBlock from '../components/CodeBlock'
import PageHeader from '../components/PageHeader'
import Rich from '../components/Rich'
import { AFFILIATIONS, AUTHORS, BIBTEX } from '../content/people'
import { site } from '../lib/data'
import { useFigure } from '../lib/figures'
import { useTitle } from '../lib/hooks'

function Figure({ fig, number }) {
  const src = useFigure(fig.file)
  return (
    <figure className={`card overflow-hidden ${number === 1 ? 'md:col-span-2' : ''}`}>
      <a href={src} className="block bg-white p-3 dark:bg-transparent">
        <img src={src} alt={`Figure ${number} of the paper`} loading="lazy" className="mx-auto w-full" />
      </a>
      <figcaption className="border-t border-line px-4 py-3 text-sm leading-relaxed text-soft">
        <span className="font-semibold text-ink">Figure {number}. </span>
        <Rich text={fig.caption} />
      </figcaption>
    </figure>
  )
}

export default function Paper() {
  useTitle('Paper')
  return (
    <>
      <PageHeader eyebrow="Paper" title={site.title}>
        <div className="mt-6 space-y-2">
          <p className="text-[1.05rem] text-ink">
            {AUTHORS.map((a, i) => (
              <span key={a.name}>
                {a.url ? <a href={a.url} className="font-medium hover:text-accent">{a.name}</a> : <span className="font-medium">{a.name}</span>}
                <sup className="ml-px text-muted">{a.affiliation + 1}</sup>
                {i < AUTHORS.length - 1 ? ', ' : ''}
              </span>
            ))}
          </p>
          <p className="text-sm text-muted">{AFFILIATIONS.map((a, i) => <span key={a} className="mr-4"><sup>{i + 1}</sup> {a}</span>)}</p>
        </div>
        <p className="mt-6 inline-flex items-center gap-2 rounded-full border border-dashed border-rule bg-surface px-4 py-2 text-sm text-soft">
          <BookOpen size={15} className="text-accent" aria-hidden="true" /> The paper is coming soon. Until then, please cite the repository.
        </p>
      </PageHeader>
      <div className="page mt-12 grid gap-12 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <section aria-labelledby="abstract">
          <h2 id="abstract" className="text-2xl font-semibold tracking-tight">Abstract</h2>
          <Rich as="p" text={site.abstract} className="mt-4 font-serif text-[1.12rem] leading-[1.7] text-ink" />
        </section>
        <section aria-labelledby="cite">
          <h2 id="cite" className="text-2xl font-semibold tracking-tight">Citation</h2>
          <p className="mt-2 text-sm text-soft">The paper is not public yet. Until it is, please cite:</p>
          <div className="mt-4"><CodeBlock code={BIBTEX} lang="bibtex" wrap /></div>
          <h3 className="mt-8 font-sans text-sm font-semibold text-ink">Contact</h3>
          <ul className="mt-2 space-y-1 text-sm">
            {AUTHORS.map((a) => <li key={a.email}><a className="link" href={`mailto:${a.email}`}>{a.email}</a></li>)}
          </ul>
        </section>
      </div>
      <section className="page mt-16" aria-labelledby="figures">
        <h2 id="figures" className="text-2xl font-semibold tracking-tight">Figures</h2>
        <p className="mt-1 text-sm text-soft">The paper’s eight figures, with their captions.</p>
        <div className="mt-6 grid gap-6 md:grid-cols-2">
          {site.figures.map((f, i) => <Figure key={f.key} fig={f} number={i + 1} />)}
        </div>
      </section>
    </>
  )
}
