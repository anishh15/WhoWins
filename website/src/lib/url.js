import { useSearchParams } from 'react-router-dom'

/**
 * Query parameters of the hash route as state, so a view can be shared by its link. spec maps each
 * name to [allowed values, fallback]; anything not allowed reads as the fallback, which is left out
 * of the address. set({ name: value, ... }) changes several at once.
 */
export function useQuery(spec) {
  const [params, setParams] = useSearchParams()
  const values = {}
  for (const [name, [allowed, fallback]] of Object.entries(spec)) {
    const raw = params.get(name)
    values[name] = raw !== null && allowed.includes(raw) ? raw : fallback
  }
  const set = (changes) => setParams((current) => {
    const out = new URLSearchParams(current)
    for (const [name, value] of Object.entries(changes)) {
      if (value === spec[name][1]) out.delete(name)
      else out.set(name, value)
    }
    return out
  }, { replace: true })
  return [values, set]
}
