import Contents, { BackToTop } from '../components/Contents'
import PageHeader from '../components/PageHeader'
import Rich from '../components/Rich'
import ScrollBox from '../components/ScrollBox'
import ScenarioBrowser from '../components/ScenarioBrowser'
import SeatChip from '../components/SeatChip'
import TrialViewer from '../components/TrialViewer'
import { EXPERIMENT_INFO, OUTCOMES, SEAT_INFO, TASK_TYPES } from '../content/benchmark'
import { fill, site } from '../lib/data'
import { useTitle } from '../lib/hooks'

const TRIAL_SCENARIOS = new Set(site.trialScenarios)

function Heading({ id, eyebrow, title, lead }) {
  return (
    <div className="max-w-3xl">
      <p className="eyebrow">{eyebrow}</p>
      <h2 id={id} className="mt-2 text-3xl font-semibold tracking-tight">{title}</h2>
      {lead && <Rich as="p" text={lead} className="mt-2 leading-relaxed text-soft" />}
    </div>
  )
}

function TaskTypes() {
  return (
    <section className="page mt-12" aria-labelledby="types">
      <Heading id="types" eyebrow="Scenarios" title="Task types"
        lead="A scenario is a task and up to {{design:options.1:word}} options that set one property to different values, so a reply’s scored choice matches at most one option." />
      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {site.taskTypes.map((t) => (
          <div key={t.key} className="card flex flex-col p-5">
            <p className="text-3xl font-semibold tracking-tight text-ink">{t.scenarios}</p>
            <p className="mt-1 font-serif text-lg font-semibold text-accent">{TASK_TYPES[t.key].title}</p>
            <p className="mt-2 text-sm text-ink">Scores {TASK_TYPES[t.key].scores}.</p>
            <p className="mt-1 flex-1 text-sm leading-relaxed text-soft">{TASK_TYPES[t.key].detail}</p>
            <code className="mt-3 font-mono text-xs text-muted">data/scenarios/{t.folder}/</code>
          </div>
        ))}
      </div>
    </section>
  )
}

function Seats() {
  return (
    <section className="page mt-16" aria-labelledby="seats">
      <Heading id="seats" eyebrow="Seats" title="Seats"
        lead="Each instruction arrives from one of {{design:seats:word}} sources, called seats. The task itself arrives as a user message that starts with `Task:`." />
      <div className="mt-6"><ScrollBox label="The seats" className="rounded-2xl border border-line bg-surface shadow-card">
        <table className="w-full min-w-[40rem] text-left text-sm">
          <thead className="bg-tint/50 text-xs font-semibold uppercase tracking-wide text-accent">
            <tr>
              <th scope="col" className="px-4 py-2.5">Seat</th>
              <th scope="col" className="px-4 py-2.5">Source</th>
              <th scope="col" className="px-4 py-2.5">Arrives in</th>
              <th scope="col" className="px-4 py-2.5">Label line the model sees</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {site.seats.map(({ seat, label }) => (
              <tr key={seat}>
                <td className="px-4 py-3"><SeatChip seat={seat} size="lg" /></td>
                <td className="px-4 py-3 font-medium text-ink">{SEAT_INFO[seat].source}</td>
                <td className="px-4 py-3 text-soft"><Rich text={SEAT_INFO[seat].where} /></td>
                <td className="px-4 py-3">{label ? <code className="font-mono text-xs text-ink">{label}</code> : <span className="text-muted">(none)</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollBox></div>
    </section>
  )
}

function Experiments() {
  return (
    <section className="page mt-16" aria-labelledby="experiments">
      <Heading id="experiments" eyebrow="Design" title="Experiments"
        lead="Each experiment varies one aspect of how the text is delivered and keeps the text fixed." />
      <div className="mt-6"><ScrollBox label="The experiments" className="rounded-2xl border border-line bg-surface shadow-card">
        <table className="w-full min-w-[52rem] text-left text-sm">
          <thead className="bg-tint/50 text-xs font-semibold uppercase tracking-wide text-accent">
            <tr>
              <th scope="col" className="px-4 py-2.5">Experiment</th>
              <th scope="col" className="px-4 py-2.5">What moves</th>
              <th scope="col" className="px-4 py-2.5">Held fixed</th>
              <th scope="col" className="px-4 py-2.5 text-right">Trials</th>
              <th scope="col" className="px-4 py-2.5 text-right">Replies</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {site.experiments.map((e) => (
              <tr key={e.key}>
                <th scope="row" className="px-4 py-3 text-left font-serif text-base font-semibold text-ink">{e.name}</th>
                <td className="px-4 py-3 text-soft">{fill(EXPERIMENT_INFO[e.key].moves)}</td>
                <td className="px-4 py-3 text-soft">{fill(EXPERIMENT_INFO[e.key].fixed)}</td>
                <td className="num px-4 py-3 text-right text-ink">{e.trials}{e.trialsQwen35 && <span className="block text-xs text-muted">({e.trialsQwen35})</span>}</td>
                <td className="num px-4 py-3 text-right text-ink">{e.replies}{e.repliesQwen35 && <span className="block text-xs text-muted">({e.repliesQwen35})</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollBox></div>
      <Rich as="p" className="mt-3 text-xs leading-relaxed text-muted" text="Per model-mode; each trial is sent {{design:draws_per_trial:times}} (Tiers: {{design:tier_draws_per_trial:times}}). In parentheses: Qwen 3.5, whose chat template rejects a late system message. The operator line is [[S1]] or [[S2]]." />
      <div className="mt-8 rounded-2xl border border-line bg-raised/70 p-5">
        <h3 className="font-sans text-sm font-semibold text-ink">What a reply can be</h3>
        <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          {OUTCOMES.map(([name, text]) => (
            <div key={name}>
              <dt><span className={`chip ${name === 'chose' ? 'border-rose/60 bg-tint/70 text-accent' : ''}`}>{name}</span></dt>
              <dd className="mt-1.5 text-sm leading-snug text-soft">{text}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  )
}

function Models() {
  return (
    <section className="page mt-16" aria-labelledby="models">
      <Heading id="models" eyebrow="Models" title="The models"
        lead="Qwen models run with thinking off and on, at one sampling setting per mode for every size. gpt-oss always reasons, at high effort." />
      <div className="mt-6 grid gap-5 lg:grid-cols-3">
        {site.families.map((f) => (
          <div key={f.key} className="card overflow-hidden">
            <p className="border-b border-line bg-raised/70 px-4 py-2.5 font-serif text-lg font-semibold text-ink">{f.title}</p>
            <ul className="divide-y divide-line">
              {f.models.map((m) => (
                <li key={m.name} className="flex items-baseline justify-between gap-3 px-4 py-2.5 text-sm">
                  <a href={`https://huggingface.co/${m.hf}`} className="font-medium text-ink hover:text-accent">{m.name}</a>
                  <span className="text-right text-xs text-muted">{m.parameters}{m.architecture !== 'dense' && <span className="block">{m.architecture}</span>}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  )
}

export default function Benchmark() {
  useTitle('Benchmark')
  return (
    <>
      <PageHeader eyebrow="Benchmark" title="The benchmark"
        lead="The scenarios, seats and experiments, with a browser for every scenario and real trials." />
      <div className="page mt-8">
        <Contents route="benchmark" items={[['types', 'Task types'], ['seats', 'Seats'], ['experiments', 'Experiments'], ['scenarios', 'Scenarios'], ['trials', 'Trials'], ['models', 'Models']]} />
      </div>
      <TaskTypes />
      <Seats />
      <Experiments />
      <div className="page"><BackToTop /></div>
      <section id="scenarios" className="page mt-16 scroll-mt-20" aria-labelledby="browser">
        <Heading id="browser" eyebrow="Browse" title="Scenario browser"
          lead="Every scenario in the data, as written. Search, filter, and open one to see its options and checkers." />
        <div className="mt-6"><ScenarioBrowser trialScenarios={TRIAL_SCENARIOS} /></div>
        <BackToTop />
      </section>
      <section id="trials" className="page mt-16 scroll-mt-20" aria-labelledby="viewer">
        <Heading id="viewer" eyebrow="Trials" title="Trial viewer"
          lead="Real trials from every experiment, rendered by the study’s own code." />
        <div className="mt-6"><TrialViewer /></div>
        <BackToTop />
      </section>
      <Models />
      <div className="page"><BackToTop /></div>
    </>
  )
}
