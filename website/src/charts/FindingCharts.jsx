import DataTable from '../components/DataTable'
import { LEVEL, NULL_SHARE, modeName } from '../lib/data'
import { measureRows } from '../lib/download'
import { measures, modes, thinking } from '../lib/measures'
import Boundary from './Boundary'
import DotChart from './DotChart'
import Forecast from './Forecast'
import OrderScatter from './OrderScatter'
import Thinking from './Thinking'
import { Legend, niceDomain, niceTicks } from './core'

const all = () => true
const Note = ({ children }) => <span>{children}</span>

/** A table of measures per model-mode: columns are [label, measure key]. */
function ModeTable({ caption, cols }) {
  const rows = modes.filter((m) => cols.some(([, k]) => measures[k].values[m.mm]))
  return (
    <DataTable caption={caption} rowKey={(m) => m.mm} rows={rows} columns={[
      ['Model-mode', (m) => modeName(m)],
      ...cols.flatMap(([label, k]) => {
        const v = (m) => measures[k].values[m.mm]
        return measures[k].values[rows[0].mm]?.c
          ? [[label, (m) => v(m)?.t || 'n/a', 'right'], [`${label}, ${LEVEL} interval`, (m) => v(m)?.c || '', 'right']]
          : [[label, (m) => v(m)?.t || 'n/a', 'right']]
      }),
    ]} />
  )
}

function ThinkTable({ rows, caption }) {
  return (
    <DataTable caption={caption} rowKey={(r) => r.model} rows={rows} columns={[
      ['Model', (r) => r.display],
      ['Thinking off', (r) => r.offText, 'right'],
      ['Thinking on', (r) => r.onText, 'right'],
      ['Change', (r) => r.t, 'right'],
      [`${LEVEL} interval`, (r) => r.c, 'right'],
    ]} />
  )
}

const download = (...keys) => () => measureRows(measures, keys, modes)
const thinkRows = (key) => () => thinking[key].map((r) => ({
  measure_id: `thinking_${key}`, unit: 'diff', denominator: 'decided replies, paired within the scenario', model: r.display,
  thinking_off: r.offText, thinking_on: r.onText, change: r.t, interval: r.c, change_raw: r.e, low_raw: r.l, high_raw: r.h,
}))

const rowsOf = (key, tick) => modes.filter((m) => measures[key].values[m.mm]).map((m) => ({
  mode: m, v: measures[key].values[m.mm], tick: tick && measures[tick].values[m.mm],
}))

/** The chart, table and legend for each insight on the findings page. */
export const FINDING_CHARTS = {
  boundary: () => ({
    rows: download('first_merged', 'first_separate'),
    title: 'The first-listed line, inside one message and across two',
    chart: <Boundary shown={all} />,
    legend: <Legend extra={[<Note key="r">dashed: {NULL_SHARE}</Note>, <Note key="b">bars: {LEVEL} intervals</Note>]} />,
    table: <ModeTable caption="First-listed line wins" cols={[['One message', 'first_merged'], ['Separate messages', 'first_separate']]} />,
  }),
  order: () => ({
    rows: download('later_wins', 'op_first'),
    title: 'Later line wins against the operator line when first',
    chart: <OrderScatter shown={all} />,
    legend: <Legend extra={[<Note key="s">marker size grows with parameters</Note>, <Note key="d">dashed: one minus the horizontal value</Note>]} />,
    table: <ModeTable caption="Order against the operator line" cols={[['Later wins', 'later_wins'], ['Operator first', 'op_first']]} />,
  }),
  role: () => ({
    rows: download('real_label_tp', 'real_label_first'),
    title: 'Real system message minus labelled user text, operator first',
    chart: <DotChart rows={rowsOf('real_label_tp', 'real_label_first')} unit="diff" refAt={0} yLabel="real role minus label" label="Real role minus label for the operator line sent first, per model-mode" />,
    legend: <Legend extra={[<Note key="m">marks: tool and file-write tasks, with {LEVEL} intervals</Note>, <Note key="g">grey ticks: all task types</Note>]} />,
    table: <ModeTable caption="Real minus label" cols={[['Tool and file-write', 'real_label_tp'], ['All task types', 'real_label_first']]} />,
  }),
  forecast: () => ({
    rows: download('share_position', 'share_task', 'share_seats'),
    title: 'Share of the gap recovered when forecasting larger conflicts from pairs',
    chart: <Forecast shown={all} />,
    legend: <Legend extra={[<Note key="b">bar: position fit</Note>, <Note key="t">black tick: task-aware fit</Note>, <Note key="s">mark on a stem: seats fit</Note>]} />,
    table: <ModeTable caption="Share of the gap recovered" cols={[['Position fit', 'share_position'], ['Task-aware fit', 'share_task'], ['Seats fit', 'share_seats']]} />,
  }),
  seatGain: () => ({
    rows: download('seat_gain'),
    title: 'What one strength per seat adds to the position fit',
    chart: <DotChart rows={rowsOf('seat_gain')} unit="nats" refAt={0} yLabel="nats per reply" label="Seat gain in nats per reply, per model-mode" />,
    legend: <Legend extra={[<Note key="r">dashed: zero</Note>, <Note key="b">bars: {LEVEL} intervals</Note>]} />,
    table: <ModeTable caption="Seat gain" cols={[['Seat gain (nats per reply)', 'seat_gain']]} />,
  }),
  thinkTier: () => ({
    rows: thinkRows('tier'),
    title: 'Declared tier rule followed, thinking off to on',
    chart: <Thinking rows={thinking.tier} domain={[0.4, 1]} ticks={[0.4, 0.6, 0.8, 1]} yLabel="rule followed" label="Share of decided tier trials that follow the rule, thinking off and on, per Qwen size" />,
    legend: <Legend extra={[<Note key="g">grey: the {LEVEL} interval of the change includes zero</Note>]} />,
    table: <ThinkTable rows={thinking.tier} caption="Tier rule followed, thinking off and on" />,
  }),
  thinkOp: () => ({
    rows: thinkRows('operator'),
    title: 'Operator line wins (system message, first), thinking off to on',
    chart: <Thinking rows={thinking.operator} domain={[0, 0.5]} ticks={[0, 0.25, 0.5]} yLabel="operator line wins" label="Operator line wins when first in the real system message, thinking off and on, per Qwen size" />,
    legend: <Legend extra={[<Note key="g">grey: the {LEVEL} interval of the change includes zero</Note>]} />,
    table: <ThinkTable rows={thinking.operator} caption="Operator line wins, thinking off and on" />,
  }),
  flags: () => {
    const rows = rowsOf('flagged')
    const domain = niceDomain([0, Math.max(...rows.map((r) => r.v.h ?? r.v.e)) * 1.05], 4)
    return {
      rows: download('flagged'),
      title: 'Decided pair replies that flag or hedge the conflict',
      chart: <DotChart rows={rows} unit="rate" domain={domain} ticks={niceTicks(domain, 4)} yLabel="flagged or hedged" label="Share of decided pair replies that flag or hedge the conflict, per model-mode" />,
      legend: <Legend extra={[<Note key="k">by our keyword patterns</Note>, <Note key="b">bars: {LEVEL} intervals</Note>]} />,
      table: <ModeTable caption="Flagged or hedged" cols={[['Flagged or hedged', 'flagged']]} />,
    }
  },
}
