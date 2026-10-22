import { useEffect, useState } from 'react'
import { Link, NavLink, useLocation } from 'react-router-dom'
import { Github, Menu, X } from 'lucide-react'
import Logo from './Logo'
import ThemeToggle from './ThemeToggle'
import { NAV, REPO } from './links'

const item = ({ isActive }) =>
  `rounded-full px-3 py-1.5 text-sm font-medium transition ${
    isActive ? 'bg-tint/70 text-accent' : 'text-soft hover:bg-wash hover:text-ink'
  }`

export default function Navbar() {
  const [open, setOpen] = useState(false)
  const { pathname } = useLocation()
  useEffect(() => setOpen(false), [pathname])

  return (
    <header className="sticky top-0 z-40 border-b border-line/80 bg-bg/95">
      <nav className="page flex h-16 items-center justify-between gap-4" aria-label="Main">
        <Link to="/" className="rounded-lg" aria-label="WhoWins home">
          <Logo />
        </Link>
        <div className="hidden items-center gap-1 lg:flex">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={item}>
              {n.label}
            </NavLink>
          ))}
        </div>
        <div className="flex items-center gap-1">
          <a href={REPO} className="hidden h-9 items-center gap-2 rounded-full px-3 text-sm font-medium text-soft transition hover:bg-wash hover:text-ink sm:inline-flex" aria-label="WhoWins on GitHub">
            <Github size={17} aria-hidden="true" />
            <span>GitHub</span>
          </a>
          <ThemeToggle />
          <button
            type="button"
            className="grid h-9 w-9 place-items-center rounded-full text-soft hover:bg-wash lg:hidden"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-controls="mobile-menu"
            aria-label={open ? 'Close menu' : 'Open menu'}
          >
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </nav>
      {open && (
        <div id="mobile-menu" className="border-t border-line bg-bg lg:hidden">
          <div className="page flex flex-col gap-1 py-3">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} className={item}>
                {n.label}
              </NavLink>
            ))}
            <a href={REPO} className="rounded-full px-3 py-1.5 text-sm font-medium text-soft hover:bg-wash">
              GitHub
            </a>
          </div>
        </div>
      )}
    </header>
  )
}
