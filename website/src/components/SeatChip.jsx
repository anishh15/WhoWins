import { SEATS } from '../lib/data'

/** A seat chip in the paper's colours: S1 to S5. */
export default function SeatChip({ seat, size = 'sm', title = true }) {
  const s = SEATS[seat]
  const dims = size === 'lg' ? 'h-7 min-w-[2.5rem] px-2 text-sm' : 'h-5 min-w-[1.9rem] px-1.5 text-[0.72rem]'
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-[5px] border font-serif font-bold leading-none text-[#262626] align-[0.1em] ${dims}`}
      style={{ background: s.fill, borderColor: s.line }}
      title={title ? `${seat}: ${s.name.toLowerCase()}` : undefined}
    >
      {seat}
    </span>
  )
}
