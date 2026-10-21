import Segmented from './Segmented'
import { FAMILIES } from '../lib/data'

const FAMILY_OPTIONS = [{ value: 'all', label: 'All families' }, ...FAMILIES.map((f) => ({ value: f.key, label: f.title }))]
const THINK_OPTIONS = [
  { value: 'all', label: 'Both modes' },
  { value: 'off', label: 'Thinking off' },
  { value: 'on', label: 'Thinking on' },
]

/** The family and thinking filters; filterOf(state) gives the predicate for a model-mode. */
export default function ModeFilters({ value, onChange }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Segmented label="Model family" options={FAMILY_OPTIONS} value={value.family} onChange={(family) => onChange({ ...value, family })} size="sm" />
      <Segmented label="Thinking mode" options={THINK_OPTIONS} value={value.think} onChange={(think) => onChange({ ...value, think })} size="sm" />
    </div>
  )
}

export const filterOf = ({ family, think }) => (m) => (family === 'all' || m.family === family) && (think === 'all' || m.mode === think)
