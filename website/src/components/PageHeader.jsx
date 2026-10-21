import Rich from './Rich'

/** The top of an inner page: eyebrow, serif title and a plain lead. */
export default function PageHeader({ eyebrow, title, lead, children }) {
  return (
    <header className="relative overflow-hidden border-b border-line bg-gradient-to-b from-wash/70 to-bg">
      <div className="page py-12 sm:py-16">
        <p className="eyebrow">{eyebrow}</p>
        <h1 className="mt-3 max-w-3xl text-[2.1rem] font-semibold leading-[1.1] tracking-tight sm:text-5xl">{title}</h1>
        {lead && <Rich as="p" text={lead} className="mt-4 max-w-2xl text-[1.05rem] leading-relaxed text-soft" />}
        {children}
      </div>
    </header>
  )
}
