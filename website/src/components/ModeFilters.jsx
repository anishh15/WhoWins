import Segmented from './Segmented'
import { FAMILIES } from '../lib/data'
import { useQuery } from '../lib/url'

const FAMILY_OPTIONS = [{ value: 'all', label: 'All families' }, ...FAMILIES.map((f) => ({ value: f.key, label: f.title }))]
const THINK_OPTIONS = [
  { value: 'all', label: 'Both modes' },
  { value: 'off', label: 'Thinking off' },
  { value: 'on', label: 'Thinking on' },
]

/** The family and thinking filters, kept in the link (?family=, ?think=). */
export function useModeFilters() {
  const [{ family, think }, set] = useQuery({
    family: [FAMILY_OPTIONS.map((o) => o.value), 'all'],
    think: [THINK_OPTIONS.map((o) => o.value), 'all'],
  })
  const shown = (m) => (family === 'all' || m.family === family) && (think === 'all' || m.mode === think)
  return { family, think, set, shown }
}

export default function ModeFilters({ filters }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Segmented label="Model family" options={FAMILY_OPTIONS} value={filters.family} onChange={(family) => filters.set({ family })} size="sm" />
      <Segmented label="Thinking mode" options={THINK_OPTIONS} value={filters.think} onChange={(think) => filters.set({ think })} size="sm" />
    </div>
  )
}
