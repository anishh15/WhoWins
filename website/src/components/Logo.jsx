import logo from '../assets/logo.svg'

/** The WhoWins mark (five seat bars, the winning one longer) beside the name. */
export default function Logo({ className = '' }) {
  return (
    <span className={`inline-flex items-center gap-2.5 ${className}`}>
      <img src={logo} alt="" width="30" height="30" className="h-[30px] w-[30px]" />
      <span className="font-serif text-[1.35rem] font-semibold tracking-tight text-ink">
        Who<span className="text-accent">Wins</span>
      </span>
    </span>
  )
}
