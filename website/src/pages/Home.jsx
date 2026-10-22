import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { ArrowRight, BookOpen, Github, LayoutGrid, Search, Terminal } from 'lucide-react'
import HeroDuel from '../components/HeroDuel'
import SeatChip from '../components/SeatChip'
import { REPO } from '../components/links'
import { HEADLINES } from '../content/findings'
import { HERO, KPIS, STEPS, STUDY } from '../content/home'
import { SEAT_INFO } from '../content/benchmark'
import { familyOf, fill, site } from '../lib/data'
import { useTitle } from '../lib/hooks'

const [QUESTION, REST] = site.title.split(/(?<=\?) /)

function Hero() {
  return (
    <section className="relative overflow-hidden">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_85%_-10%,rgb(var(--tint)/0.9),transparent_70%),radial-gradient(40rem_24rem_at_-10%_10%,rgb(var(--wash)),transparent_70%)]" />
      <div className="page relative grid items-center gap-10 py-12 sm:py-16 lg:grid-cols-[1.05fr_1fr] lg:gap-14 lg:py-20">
        <div>
          <p className="eyebrow">{HERO.eyebrow}</p>
          <h1 className="mt-4 text-[2.6rem] font-semibold leading-[1.02] tracking-tight sm:text-6xl">{QUESTION}</h1>
          <p className="mt-3 font-serif text-xl italic text-soft sm:text-2xl">{REST}</p>
          <p className="mt-6 max-w-xl text-[1.05rem] leading-relaxed text-soft">{HERO.lead}</p>
          <div className="mt-8 flex flex-wrap gap-2.5">
            <Link to="/results" className="btn-primary">
              Explore results <ArrowRight size={16} aria-hidden="true" />
            </Link>
            <Link to="/benchmark?at=scenarios" className="btn-quiet"><Search size={15} aria-hidden="true" /> Browse scenarios</Link>
            <Link to="/docs" className="btn-quiet"><Terminal size={15} aria-hidden="true" /> Get started</Link>
            <a href={REPO} className="btn-quiet"><Github size={15} aria-hidden="true" /> GitHub</a>
            <span className="btn cursor-default border border-dashed border-rule text-muted" title="The paper will be linked here once it is public">
              <BookOpen size={15} aria-hidden="true" /> Paper: coming soon
            </span>
          </div>
        </div>
        <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.1 }}>
          <HeroDuel />
        </motion.div>
      </div>
    </section>
  )
}

function Kpis() {
  return (
    <section aria-label="The study in numbers" className="page">
      <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line shadow-card sm:grid-cols-3 lg:grid-cols-6">
        {KPIS.map((k) => (
          <div key={k.label} className="bg-surface px-4 py-5 sm:px-5">
            <dt className="sr-only">{k.label}</dt>
            <dd className="text-[1.65rem] font-semibold leading-none tracking-tight text-ink sm:text-3xl">{fill(k.value)}</dd>
            <dd className="mt-2 text-sm font-medium text-soft">{k.label}</dd>
            <dd className="mt-0.5 text-xs text-muted">{fill(k.note)}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function Headlines() {
  return (
    <section className="page mt-20 sm:mt-24">
      <div className="max-w-2xl">
        <p className="eyebrow">Findings</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">{STUDY.title}</h2>
        <p className="mt-3 leading-relaxed text-soft">{STUDY.lead}</p>
      </div>
      <div className="mt-8 grid gap-5 lg:grid-cols-3">
        {HEADLINES.map((h, i) => (
          <article key={h.to} className="card flex flex-col p-6">
            <span className="font-serif text-lg font-semibold italic text-accent">{i + 1})</span>
            <p className="mt-2 flex-1 leading-relaxed text-ink">{h.text}</p>
            <div className="mt-6 border-t border-line pt-4">
              <p className="num text-2xl font-semibold tracking-tight text-accent">{fill(h.stat)}</p>
              <p className="mt-1 text-sm text-muted">{h.statLabel}</p>
            </div>
            <Link to={`/findings?at=${h.to}`} className="link mt-4 inline-flex items-center gap-1 text-sm">
              Read the finding <ArrowRight size={14} aria-hidden="true" />
            </Link>
          </article>
        ))}
      </div>
    </section>
  )
}

function HowItWorks() {
  const options = site.box1.trial.messages.flatMap((m) => (m.lines || []).flat()).filter((p) => p.k === 'opt')
  const visuals = [
    <ul key="a" className="space-y-1.5 font-mono text-[0.74rem]">
      {[...options].sort((a, b) => a.o.localeCompare(b.o)).map((p) => (
        <li key={p.o} className="truncate rounded-md border border-line bg-raised px-2 py-1 text-soft"><span className="text-muted">{p.o}</span> {p.s}</li>
      ))}
    </ul>,
    <div key="b" className="space-y-2.5">
      {Object.entries(SEAT_INFO).map(([seat, s]) => (
        <p key={seat} className="flex items-center gap-2 text-sm text-soft"><SeatChip seat={seat} /> {s.source}</p>
      ))}
      <p className="pt-1 text-xs leading-relaxed text-muted">{site.experiments.map((e) => e.name).join(' · ')}</p>
    </div>,
    <div key="c" className="flex flex-wrap gap-1.5">
      {['chose', 'unresolved', 'off-menu', 'multiple', 'no action'].map((o) => (
        <span key={o} className={`chip ${o === 'chose' ? 'border-rose/60 bg-tint/70 text-accent' : ''}`}>{o}</span>
      ))}
      <p className="mt-2 w-full text-xs text-muted">No LLM judge. The same reply always gets the same label.</p>
    </div>,
  ]
  return (
    <section className="page mt-20 sm:mt-24">
      <div className="max-w-2xl">
        <p className="eyebrow">The benchmark</p>
        <h2 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">How it works</h2>
      </div>
      <ol className="mt-8 grid gap-5 lg:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.title} className="card flex min-w-0 flex-col p-6">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-tint font-serif text-sm font-bold text-accent">{i + 1}</span>
            <h3 className="mt-4 text-xl font-semibold">{s.title}</h3>
            <p className="mt-2 text-sm leading-relaxed text-soft">{fill(s.text)}</p>
            <div className="mt-5 flex-1">{visuals[i]}</div>
          </li>
        ))}
      </ol>
      <div className="mt-5 grid gap-5 sm:grid-cols-3">
        {site.families.map((f) => (
          <div key={f.key} className="rounded-2xl border border-line bg-raised/70 px-5 py-4">
            <p className="font-serif text-lg font-semibold" style={{ color: familyOf[f.key].text }}>{f.title}</p>
            <p className="mt-1 text-sm text-soft">{f.models.length} models, {f.sizes}, {f.key === 'gpt-oss' ? 'always reasoning' : 'thinking off and on'}</p>
          </div>
        ))}
      </div>
    </section>
  )
}

function Explore() {
  const links = [
    { to: '/results', icon: LayoutGrid, title: 'Results dashboard', text: 'Every measure of the main table for every model-mode, with intervals.' },
    { to: '/seats', icon: ArrowRight, title: 'Seat matchups', text: 'Which seat beats which, for one model-mode at a time.' },
    { to: '/benchmark?at=trials', icon: Search, title: 'Trial viewer', text: 'Real trials of every experiment, as the model receives them.' },
  ]
  return (
    <section className="page mt-20 sm:mt-24">
      <div className="grid gap-4 md:grid-cols-3">
        {links.map(({ to, icon: Icon, title, text }) => (
          <Link key={to} to={to} className="group card flex items-start gap-4 p-5 transition-transform duration-200 hover:-translate-y-0.5">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-tint text-accent"><Icon size={18} aria-hidden="true" /></span>
            <span>
              <span className="block font-semibold text-ink group-hover:text-accent">{title}</span>
              <span className="mt-1 block text-sm text-soft">{text}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  )
}

export default function Home() {
  useTitle()
  return (
    <>
      <Hero />
      <Kpis />
      <Headlines />
      <HowItWorks />
      <Explore />
    </>
  )
}
