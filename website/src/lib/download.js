import { modeName } from './data'
import { modeOf } from './measures'

/** Rows for a download: each measure for each model-mode, on all scenarios and on each half. */
export function measureRows(measures, keys, modes) {
  const rows = []
  for (const key of keys) {
    const m = measures[key]
    for (const mode of modes) {
      const v = m.values[mode.mm]
      if (!v) continue
      for (const [half, x] of [['all', v], ['discovery', v.D], ['held-out', v.H]]) {
        if (!x) continue
        rows.push({
          measure_id: key, measure: m.label, unit: m.unit, denominator: m.denominator,
          model_mode: mode.mm, model: modeName(modeOf[mode.mm]), half,
          estimate: x.t, interval: x.c ?? '', estimate_raw: x.e, low_raw: x.l ?? '', high_raw: x.h ?? '',
        })
      }
    }
  }
  return rows
}

const cell = (v) => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v))

/** Save rows as a CSV or JSON file in the browser. */
export function save(rows, name, format) {
  const body = format === 'json'
    ? JSON.stringify(rows, null, 2)
    : [Object.keys(rows[0] || {}).join(','), ...rows.map((r) => Object.values(r).map(cell).join(','))].join('\n')
  const url = URL.createObjectURL(new Blob([body], { type: format === 'json' ? 'application/json' : 'text/csv' }))
  const a = Object.assign(document.createElement('a'), { href: url, download: `${name}.${format}` })
  document.body.append(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
