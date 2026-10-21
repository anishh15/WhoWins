import { motion } from 'framer-motion'
import { SEATS } from '../lib/data'
import SeatChip from './SeatChip'

const seatOfLine = (line) => line.find((p) => p.seat)?.seat

function Part({ part }) {
  if (part.k === 'opt') {
    const seat = part.seat && SEATS[part.seat]
    return (
      <>
        {part.chip && <><SeatChip seat={part.seat} /> </>}
        <span className="hl rounded-[3px] px-0.5 text-ink" style={{ '--hl': seat ? seat.fill : 'rgb(var(--tint))' }} title={`option ${part.o}`}>
          {part.s}
        </span>
      </>
    )
  }
  if (part.k === 'label') {
    return (
      <>
        <SeatChip seat={part.seat} /> <span className="text-soft">{part.s}</span>
      </>
    )
  }
  return <span className={part.k === 'task' ? 'font-semibold text-ink' : 'text-soft'}>{part.s}</span>
}

/**
 * A trial as a chat transcript in the style of the paper's Box 1. shown limits how many messages are
 * visible (the rest keep their space, for the home page animation); winner highlights one seat's lines.
 */
export default function Transcript({ trial, shown = Infinity, winner, animate = false }) {
  const Row = animate ? motion.div : 'div'
  return (
    <div className="space-y-2 font-mono text-[0.78rem] leading-relaxed sm:text-[0.8rem]">
      {trial.messages.map((msg, i) => {
        const visible = i < shown
        const motionProps = animate ? { initial: false, animate: { opacity: visible ? 1 : 0, y: visible ? 0 : 6 }, transition: { duration: 0.35 } } : {}
        return (
          <Row key={i} aria-hidden={!visible} className={`grid grid-cols-[4.6rem_1fr] gap-2 sm:grid-cols-[5.4rem_1fr] ${visible || animate ? '' : 'invisible'}`} {...motionProps}>
            <span className="pt-px font-sans text-[0.72rem] font-bold uppercase tracking-wide text-accent">{msg.role}</span>
            <div className="min-w-0 break-words">
              {msg.call ? (
                <span className="text-soft"><em className="font-sans not-italic text-muted">calls</em> {msg.call}</span>
              ) : (
                msg.lines.map((line, j) => {
                  const seat = seatOfLine(line)
                  const state = !winner || !seat ? '' : seat === winner ? 'win' : 'lose'
                  return (
                    <div
                      key={j}
                      className={`min-h-[1em] rounded-md transition-all duration-500 ${state === 'lose' ? 'opacity-75 grayscale' : ''} ${state === 'win' ? '-mx-1.5 bg-tint/80 px-1.5 ring-1 ring-rose/60' : ''}`}
                    >
                      {line.map((p, k) => <Part key={k} part={p} />)}
                    </div>
                  )
                })
              )}
            </div>
          </Row>
        )
      })}
    </div>
  )
}
