// Every measure per model-mode, written by site_data.py from results.json; kept apart from data.js so
// pages without charts do not load it.
import file from '../data/measures.json'

export const { modes, measures, thinking, matchups } = file
export const modeOf = Object.fromEntries(modes.map((m) => [m.mm, m]))
