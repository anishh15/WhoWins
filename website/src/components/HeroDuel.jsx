import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { RotateCcw } from 'lucide-react'
import { fill, site } from '../lib/data'
import Rich from './Rich'
import SeatChip from './SeatChip'
import Transcript from './Transcript'

const { trial, verdict, winner } = site.box1
const COUNT = trial.messages.length
const LAST = COUNT + 2 // messages, then the reply, then the settled verdict

/** Box 1 played out once: the seats' lines arrive one by one, the reply shows which seat won, and it stays. */
export default function HeroDuel() {
  const reduced = useReducedMotion()
  const [step, setStep] = useState(reduced ? LAST : 0)

  // One message per tick until the verdict; with reduced motion the settled trial shows at once.
  useEffect(() => {
    if (reduced) {
      setStep(LAST)
      return undefined
    }
    if (step >= LAST) return undefined
    const timer = setTimeout(() => setStep((s) => s + 1), 650)
    return () => clearTimeout(timer)
  }, [reduced, step])

  const settled = step >= LAST
  const shown = Math.min(step, COUNT)
  return (
    <figure className="card relative overflow-hidden" aria-label="Box 1 of the paper: a five-way trial in a format task">
      <figcaption className="flex items-center justify-between gap-3 border-b border-blush/70 bg-tint/60 px-4 py-2.5">
        <span className="font-serif text-[0.95rem] font-semibold text-accent">Box 1: A five-way trial (format task)</span>
        <button
          type="button"
          onClick={() => setStep(reduced ? LAST : 0)}
          className="grid h-7 w-7 place-items-center rounded-full text-accent transition hover:bg-surface/70"
          aria-label="Play the trial again"
          title="Play again"
        >
          <RotateCcw size={14} />
        </button>
      </figcaption>
      <div className="px-4 py-4">
        <Transcript trial={trial} shown={shown} winner={settled ? winner : undefined} animate={!reduced} />
        <motion.div
          initial={false}
          animate={{ opacity: step > COUNT ? 1 : 0, y: step > COUNT ? 0 : 8 }}
          transition={{ duration: 0.4 }}
          aria-hidden={step <= COUNT}
          className="mt-4 flex items-start gap-3 rounded-xl border border-line bg-raised px-3 py-2.5"
        >
          <span className="mt-0.5 shrink-0 rounded-full bg-accent px-2 py-0.5 font-sans text-[0.68rem] font-bold uppercase tracking-wide text-surface">reply</span>
          <Rich as="p" text={verdict} className="text-[0.8rem] leading-snug text-soft" />
        </motion.div>
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-line px-4 py-2 text-xs text-muted">
        <span className="flex items-center gap-1">
          {['S1', 'S2', 'S3', 'S4', 'S5'].map((s) => <SeatChip key={s} seat={s} />)}
        </span>
        <span aria-live="polite">{settled ? <>Winner: <SeatChip seat={winner} /></> : fill('{{design:seats:Word}} seats, one key')}</span>
      </div>
    </figure>
  )
}
