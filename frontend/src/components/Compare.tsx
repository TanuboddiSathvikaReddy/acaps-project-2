import { useMemo, useState } from 'react'
import type { RunView } from '../adapters/run'
import { SCHEDULERS, type SchedulerId } from '../api/types'
import { SCHED_LABEL } from '../lib/format'
import { bestSchedulers, fmtMetric, metricDef, rawMetric, toDisplay } from '../lib/metrics'
import { GroupedBars, SchedLegend } from '../visuals/charts'
import { Segmented } from './ui'

/** The same six metrics as Results (design brief §6): one primary comparison table, plus one
 * chart. The metric picker is the one control kept — without it there's no way to chart six
 * differently-scaled metrics (packets vs. ms vs. % vs. packets/s) in a single readable chart.
 * Everything else the old Compare page had — scheduler-focus filters, an overall/per-class scope
 * toggle, and a chart/table mode switch — was removed as unnecessary. */
const COMPARE_METRICS = ['deadlineMisses', 'packetLossRate', 'avgWaitingTimeMs', 'p95TotalDelayMs', 'throughputPps', 'starvationCount']

/** Scheduler comparison: one table (Metric × FIFO/Static Priority/ACAPS), one chart. Values come
 * straight from the backend's own metrics — no frontend scheduling logic, no fabricated numbers. */
export function CompareExplorer({ view }: { view: RunView }) {
  const [metric, setMetric] = useState(COMPARE_METRICS[0])
  const def = metricDef(metric)
  const group = useMemo(() => ({ key: 'overall', label: 'Overall', values: Object.fromEntries(SCHEDULERS.map(s => [s, toDisplay(def, rawMetric(view.schedulers[s].raw.metrics, metric, 'overall'))])) }), [view, metric, def])
  return (
    <div className="stack" style={{ gap: 24 }}>
      <div className="glass pad-lg">
        <div className="row spread" style={{ marginBottom: 14 }}><h2 style={{ fontSize: '1.05rem', margin: 0 }}>Scheduler comparison</h2><SchedLegend /></div>
        <div className="tbl-wrap" tabIndex={0}><table className="tbl">
          <caption className="sr-only">Core metrics by scheduler</caption>
          <thead><tr><th>Metric</th>{SCHEDULERS.map(s => <th key={s} className="r">{SCHED_LABEL[s]}</th>)}</tr></thead>
          <tbody>{COMPARE_METRICS.map(key => {
            const d = metricDef(key)
            const vals = Object.fromEntries(SCHEDULERS.map(s => [s, rawMetric(view.schedulers[s].raw.metrics, key)]))
            const best = bestSchedulers(vals, d.better)
            return <tr key={key}><td title={d.note}>{d.label}</td>{SCHEDULERS.map(s => <td key={s} className={`r ${best.includes(s) ? 'best' : ''}`}>{fmtMetric(d, vals[s] ?? null)}</td>)}</tr>
          })}</tbody>
        </table></div>
        <p className="small muted" style={{ marginTop: 12 }}>Green marks the best value in this run. Measured on this run only, not a general claim about the schedulers.</p>
      </div>
      <div className="glass pad-lg">
        <div className="row spread" style={{ marginBottom: 14, flexWrap: 'wrap', gap: 12 }}>
          <div><div className="title" style={{ fontSize: '1.2rem' }}>{def.label}</div><div className="small muted">{def.better === 'lower' ? 'Lower is better' : 'Higher is better'} · unit: {def.pct ? '% of generated packets' : def.unit}</div></div>
          <Segmented label="Metric to chart" value={metric} onChange={setMetric} options={COMPARE_METRICS.map(k => ({ value: k, label: metricDef(k).label }))} />
        </div>
        <GroupedBars groups={[group]} unit={def.pct ? '%' : def.unit} digits={def.digits} />
        <p className="small muted" style={{ marginTop: 14 }}>Exact values appear on hover. Bars start at zero.</p>
      </div>
    </div>
  )
}
