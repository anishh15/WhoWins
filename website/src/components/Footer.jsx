import { Link } from 'react-router-dom'
import Logo from './Logo'
import { NAV, PYPI, REPO } from './links'
import { AFFILIATIONS, AUTHORS } from '../content/people'

export default function Footer() {
  return (
    <footer className="mt-24 border-t border-line bg-raised/60">
      <div className="page grid gap-10 py-12 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="space-y-3">
          <Logo />
          <p className="max-w-sm text-sm leading-relaxed text-muted">
            Position, Role or Label? A Controlled Study of Instruction Conflicts in LLM Agents.
          </p>
          <p className="text-sm text-soft">
            {AUTHORS.map((a, i) => (
              <span key={a.name}>
                {a.name}
                <sup className="ml-px text-[0.65em] text-muted">{a.affiliation + 1}</sup>
                {i < AUTHORS.length - 1 ? ', ' : ''}
              </span>
            ))}
          </p>
          <p className="text-xs text-muted">
            {AFFILIATIONS.map((a, i) => (
              <span key={a} className="mr-3">
                <sup>{i + 1}</sup> {a}
              </span>
            ))}
          </p>
        </div>
        <div>
          <h2 className="eyebrow mb-3 font-sans">Explore</h2>
          <ul className="space-y-2 text-sm">
            {NAV.map((n) => (
              <li key={n.to}>
                <Link to={n.to} className="text-soft hover:text-accent">
                  {n.label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="eyebrow mb-3 font-sans">Project</h2>
          <ul className="space-y-2 text-sm text-soft">
            <li><a href={REPO} className="hover:text-accent">Code and scenarios on GitHub</a></li>
            <li><a href={PYPI} className="hover:text-accent">pip install whowins</a></li>
            <li><a href={`${REPO}/issues`} className="hover:text-accent">Report an issue</a></li>
            <li><span className="text-muted">Paper: coming soon</span></li>
            <li><a href={`${REPO}/blob/main/LICENSE`} className="hover:text-accent">Apache License 2.0</a></li>
          </ul>
        </div>
      </div>
      <div className="border-t border-line">
        <p className="page py-5 text-xs text-muted">
          Every study number on this site is generated from the paper's data by a script; none is typed by hand.
        </p>
      </div>
    </footer>
  )
}
