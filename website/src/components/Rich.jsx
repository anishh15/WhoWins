import { Fragment } from 'react'
import { fill } from '../lib/data'
import SeatChip from './SeatChip'

// The site's small markup: ***bold italic***, **bold**, *italic*, `code`, [[S1]] seat chips; macros in double braces.
const TOKEN = /(\*\*\*[^*]+\*\*\*|\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|\[\[S[1-5]\]\])/g

function render(text) {
  return text.split(TOKEN).map((part, i) => {
    if (!part) return null
    if (part.startsWith('***')) return <strong key={i}><em>{part.slice(3, -3)}</em></strong>
    if (part.startsWith('**')) return <strong key={i} className="font-semibold text-ink">{render(part.slice(2, -2))}</strong>
    if (part.startsWith('*')) return <em key={i}>{render(part.slice(1, -1))}</em>
    if (part.startsWith('`')) return <code key={i} className="rounded bg-raised px-1 py-px font-mono text-[0.88em] text-ink">{part.slice(1, -1)}</code>
    if (part.startsWith('[[')) return <SeatChip key={i} seat={part.slice(2, -2)} />
    return <Fragment key={i}>{part}</Fragment>
  })
}

/** Text in the site's markup, with numbers.tex macros filled in. */
export default function Rich({ text, as: Tag = 'span', className }) {
  return <Tag className={className}>{render(fill(text))}</Tag>
}
