// The site's study data, read from the JSON that the paper repository's site_data.py writes (nothing in it
// is typed by hand), and the paper's family and seat colours.
import macros from '../data/macros.json'
import site from '../data/site.json'
import table from '../data/table.json'

export { site, table }

export const FAMILIES = [
  { key: 'qwen3', title: 'Qwen 3', mark: 'var(--fam-qwen3)', edge: 'var(--fam-qwen3)', text: 'var(--fam-text-qwen3)', tint: 'var(--fam-tint-qwen3)', shape: 'circle' },
  { key: 'qwen3.5', title: 'Qwen 3.5', mark: 'var(--fam-qwen35)', edge: 'var(--fam-qwen35)', text: 'var(--fam-text-qwen35)', tint: 'var(--fam-tint-qwen35)', shape: 'square' },
  { key: 'gpt-oss', title: 'gpt-oss', mark: 'var(--fam-gptoss)', edge: 'var(--fam-gptoss-edge)', text: 'var(--fam-text-gptoss)', tint: 'var(--fam-tint-gptoss)', shape: 'triangle' },
]
export const familyOf = Object.fromEntries(FAMILIES.map((f) => [f.key, f]))

export const SEATS = {
  S1: { name: 'Operator', fill: '#ECCECA', line: '#8D4F4A' },
  S2: { name: 'Repository config', fill: '#F7E5E2', line: '#BD8A81' },
  S3: { name: 'User', fill: '#CAD7E9', line: '#415A79' },
  S4: { name: 'Tool result', fill: '#F2E3C3', line: '#AA8E53' },
  S5: { name: 'Memory note', fill: '#E1EDF5', line: '#8AA2B1' },
}

/** Fill in the numbers.tex macros that a text names in double braces. */
export function fill(text) {
  return text.replace(/\{\{([A-Za-z]+)\}\}/g, (whole, name) => macros[name] ?? whole)
}

/** A model-mode's name as the paper writes it in prose. */
export const modeName = (m) => `${m.display}${m.family === 'gpt-oss' ? '' : `, thinking ${m.mode}`}`
