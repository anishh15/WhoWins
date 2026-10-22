import { Cpu } from 'lucide-react'
import CodeBlock from '../components/CodeBlock'
import PageHeader from '../components/PageHeader'
import Rich from '../components/Rich'
import { REPO } from '../components/links'
import { STEPS, TREE } from '../content/docs'
import { fill } from '../lib/data'
import { useTitle } from '../lib/hooks'

export default function Docs() {
  useTitle('Get started')
  return (
    <>
      <PageHeader eyebrow="Get started" title="Install, check and score"
        lead="Everything here runs from a clone of the repository. Only sending trials to a model needs a GPU machine; checking the data, building trials and scoring replies do not." />
      <div className="page mt-10 grid gap-10 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <nav aria-label="Steps" className="hidden lg:block">
          <ol className="sticky top-24 space-y-2 border-l border-line text-sm">
            {STEPS.map((s, i) => (
              <li key={s.id}>
                <a href={`#/docs?at=${s.id}`} className="-ml-px block border-l-2 border-transparent py-0.5 pl-3 text-soft hover:border-rose hover:text-accent">
                  <span className="mr-1.5 text-muted">{i + 1}.</span>{s.title}
                </a>
              </li>
            ))}
            <li><a href="#/docs?at=layout" className="-ml-px block border-l-2 border-transparent py-0.5 pl-3 text-soft hover:border-rose hover:text-accent">Repository layout</a></li>
          </ol>
        </nav>
        <div className="min-w-0 space-y-12">
          {STEPS.map((s, i) => (
            <section key={s.id} id={s.id} className="scroll-mt-24">
              <div className="flex items-center gap-3">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-tint font-serif text-sm font-bold text-accent">{i + 1}</span>
                <h2 className="text-2xl font-semibold tracking-tight">{s.title}</h2>
                {s.gpu && <span className="chip gap-1"><Cpu size={12} aria-hidden="true" /> needs a GPU</span>}
              </div>
              <Rich as="p" text={s.text} className="mt-3 max-w-3xl leading-relaxed text-soft" />
              <div className="mt-4"><CodeBlock code={s.code} lang={s.lang || 'bash'} /></div>
              {s.note && <Rich as="p" text={s.note} className="mt-3 max-w-3xl text-sm leading-relaxed text-muted" />}
            </section>
          ))}
          <section id="layout" className="scroll-mt-24">
            <h2 className="text-2xl font-semibold tracking-tight">Repository layout</h2>
            <div className="mt-4"><CodeBlock code={fill(TREE)} lang="text" title="WhoWins" /></div>
            <p className="mt-4 text-sm text-soft">
              Every command and flag is in <a className="link" href={`${REPO}/blob/main/runbook.md`}>runbook.md</a>, and{' '}
              <a className="link" href={`${REPO}/tree/main/docs/codebase`}>docs/codebase</a> explains the code file by file.
            </p>
          </section>
        </div>
      </div>
    </>
  )
}
