import { useMemo } from 'react'
import type { RunView } from '../adapters/run'
import { SCHEDULERS, TRAFFIC_CLASSES, type SchedulerId } from '../api/types'
import { CLASS_LABEL, SCHED_LABEL, fmtNum } from '../lib/format'
import { bestSchedulers, fmtMetric, metricDef, rawMetric, toDisplay } from '../lib/metrics'
import { GroupedBars, QueueTimeline, SchedLegend } from '../visuals/charts'
import { ClassGlyph } from './Icons'
import { Reveal, DemoBadge, Banner } from './ui'

/** A plain-language sentence built ONLY from the measured numbers, scoped to this run. */
export function measuredSentence(view: RunView): string {
  const m = (s: SchedulerId) => view.schedulers[s].raw.metrics.overall
  const n = (s: SchedulerId) => (m(s).deadlineMisses ?? 0) as number
  const parts = SCHEDULERS.map(s => `${SCHED_LABEL[s]} ${fmtNum(n(s))}`)
  const all = SCHEDULERS.map(n)
  if (all.every(x => x === 0)) return 'No scheduler missed a deadline in this run. The workload did not stress the deadlines enough to separate them.'
  return `Deadline misses in this run: ${parts.join(', ')} packets. This describes this workload only, not schedulers in general.`
}

/** Results page's own fixed six-metric set (design brief: "Deadline Misses, Packet Loss, Average
 * Waiting Time, P95 Total Delay, Throughput, Starvation"). Kept separate from lib/metrics.ts's
 * seven `core: true` Compare tabs — Compare and Results are allowed their own minimal sets. */
const RESULTS_METRICS = ['deadlineMisses', 'packetLossRate', 'avgWaitingTimeMs', 'p95TotalDelayMs', 'throughputPps', 'starvationCount']

export function Results({ view, onOpen }: { view: RunView; onOpen: (tab: 'compare' | 'playback') => void }) {
  const cfg = view.raw.config
  const classBars = useMemo(() => TRAFFIC_CLASSES.map(c => ({ key: c, label: <span className="cls"><ClassGlyph cls={c} />{CLASS_LABEL[c]}</span>, values: Object.fromEntries(SCHEDULERS.map(s => [s, toDisplay(metricDef('deadlineMissRate'), rawMetric(view.schedulers[s].raw.metrics, 'deadlineMissRate', c))])) })), [view])
  const series = SCHEDULERS.map(s => ({ id: s, points: view.schedulers[s].timeline }))
  return (
    <div className="stack" style={{ gap: 32 }}>
      {/* --- header --- */}
      <Reveal className="glass pad-lg">
        <div className="row spread"><div className="eyebrow"><span className="dot" />Simulation complete</div>{view.demo && <DemoBadge note={view.demoNote} />}</div>
        {view.demo && <Banner tone="warn"><b>Demo data.</b> {view.demoNote}</Banner>}
        <h1 style={{ margin: '6px 0 2px', fontSize: 'var(--fs-title)' }}>{measuredHeadline(view)}</h1>
        <p className="muted small" style={{ maxWidth: '62ch', margin: 0 }}>{measuredSentence(view)} Same workload, fingerprint <code>{view.raw.workload.fingerprint.slice(0, 10)}</code>.</p>
      </Reveal>

      {/* --- one comparison: core metrics table --- */}
      <Reveal className="glass pad-lg">
        <div className="row spread" style={{ marginBottom: 14 }}><h2 style={{ fontSize: '1.05rem', margin: 0 }}>Scheduler comparison</h2><SchedLegend /></div>
        <div className="tbl-wrap" tabIndex={0}><table className="tbl">
          <caption className="sr-only">Core metrics by scheduler</caption>
          <thead><tr><th>Metric</th>{SCHEDULERS.map(s => <th key={s} className="r">{SCHED_LABEL[s]}</th>)}</tr></thead>
          <tbody>{RESULTS_METRICS.map(key => {
            const def = metricDef(key)
            const vals = Object.fromEntries(SCHEDULERS.map(s => [s, rawMetric(view.schedulers[s].raw.metrics, key)]))
            const best = bestSchedulers(vals, def.better)
            return <tr key={key}><td title={def.note}>{def.label}</td>{SCHEDULERS.map(s => <td key={s} className={`r ${best.includes(s) ? 'best' : ''}`}>{fmtMetric(def, vals[s] ?? null)}</td>)}</tr>
          })}</tbody>
        </table></div>
        <p className="small muted" style={{ marginTop: 12 }}>Green marks the best value in this run. This describes this run only, not schedulers in general.</p>
      </Reveal>

      {/* --- two charts --- */}
      <div className="grid-2">
        <Reveal className="glass pad-lg"><div className="eyebrow" style={{ marginBottom: 12 }}>Waiting packets over time</div>
          <QueueTimeline series={series} capacity={cfg.queueCapacity} thresholds={cfg.congestionThresholds} endUs={view.endUs} /></Reveal>
        <Reveal d={1} className="glass pad-lg"><div className="eyebrow" style={{ marginBottom: 12 }}>Deadline miss rate by traffic class</div>
          <GroupedBars groups={classBars} unit="%" digits={2} /></Reveal>
      </div>

      <div className="row" style={{ justifyContent: 'center', gap: 10 }}>
        <button className="btn ghost sm" onClick={() => onOpen('compare')}>Explore every metric</button>
        <button className="btn primary sm" onClick={() => onOpen('playback')}>Watch the run again</button>
      </div>
    </div>
  )
}

/** Headline built from all three schedulers' own numbers — never singles out one scheduler as
 * having "won"; it states what happened in this run and leaves the comparison to the KPIs below. */
function measuredHeadline(view: RunView) {
  const n = (s: SchedulerId) => (view.schedulers[s].raw.metrics.overall.deadlineMisses as number) ?? 0
  const vals = SCHEDULERS.map(n)
  if (vals.every(x => x === 0)) return 'No deadlines were missed in this run.'
  if (new Set(vals).size === 1) return `Every scheduler missed ${fmtNum(vals[0])} deadlines in this run.`
  return 'Deadline misses varied across schedulers in this run.'
}
