import type { SchedulerId, SchedulerMetrics, TrafficClass } from '../api/types'
import { SCHEDULERS } from '../api/types'

export interface MetricDef { key: string; label: string; unit: string; digits: number; pct?: boolean; better: 'lower' | 'higher'; note?: string; core?: boolean }
export const METRICS: MetricDef[] = [
  { key: 'avgWaitingTimeMs', label: 'Average waiting time', unit: 'ms', digits: 2, better: 'lower', core: true },
  { key: 'avgTotalDelayMs', label: 'Average total delay', unit: 'ms', digits: 2, better: 'lower', core: true },
  { key: 'deadlineMissRate', label: 'Deadline miss rate', unit: '% of generated', digits: 2, pct: true, better: 'lower', core: true },
  { key: 'throughputPps', label: 'Throughput', unit: 'packets/s', digits: 1, better: 'higher', core: true },
  { key: 'packetLossRate', label: 'Packet loss', unit: '% of generated', digits: 2, pct: true, better: 'lower', core: true },
  { key: 'starvationCount', label: 'Starvation', unit: 'packets', digits: 0, better: 'lower', core: true, note: "Packets that waited an excessive fraction of their budget (see the scenario's starvation.excessiveWaitFraction, shown below) and were overtaken at least once. FIFO never overtakes, so its count is zero by definition; compare excessive waits instead." },
  { key: 'excessiveWaitCount', label: 'Excessive waits', unit: 'packets', digits: 0, better: 'lower', note: "Packets that waited more than the scenario's configured fraction of their own delay budget (starvation.excessiveWaitFraction, shown below)." },
  { key: 'p95TotalDelayMs', label: 'P95 Total Delay', unit: 'ms', digits: 2, better: 'lower', core: true },
  { key: 'maxWaitingTimeMs', label: 'Maximum waiting time', unit: 'ms', digits: 2, better: 'lower' },
  { key: 'deadlineMisses', label: 'Deadline misses', unit: 'packets', digits: 0, better: 'lower' },
  { key: 'dropped', label: 'Packets dropped', unit: 'packets', digits: 0, better: 'lower' },
  { key: 'onTimeRate', label: 'On-time rate', unit: '% of generated', digits: 2, pct: true, better: 'higher' },
  { key: 'deadlineMissRateAccepted', label: 'Deadline miss rate (accepted)', unit: '% of accepted', digits: 2, pct: true, better: 'lower', note: 'Same deadline misses as above, but divided by accepted packets (generated minus overflow drops) instead of all generated packets.' },
  { key: 'avgServiceTimeMs', label: 'Average service time', unit: 'ms', digits: 3, better: 'lower', note: 'Transmission time only (packet size / link bandwidth), excluding queueing.' },
  { key: 'throughputBps', label: 'Throughput (bits)', unit: 'bit/s', digits: 0, better: 'higher' },
  { key: 'utilization', label: 'Link utilization', unit: '% of run', digits: 1, pct: true, better: 'higher', note: 'Share of the observation window the link spent transmitting.' },
]
export const metricDef = (k: string) => METRICS.find(m => m.key === k)!

export function rawMetric(m: SchedulerMetrics, key: string, cls?: TrafficClass | 'overall'): number | null {
  const blk = !cls || cls === 'overall' ? m.overall : m.perClass[cls]
  return blk?.[key] ?? null
}
/** Display scaling only: fractions are shown as percentages. */
export const toDisplay = (def: MetricDef, v: number | null) => (v == null ? null : def.pct ? v * 100 : v)
export function fmtMetric(def: MetricDef, v: number | null, withUnit = true): string {
  if (v == null) return '—'
  const d = toDisplay(def, v)!
  const s = d.toLocaleString('en-US', { minimumFractionDigits: def.digits, maximumFractionDigits: def.digits })
  return withUnit ? `${s} ${def.pct ? '%' : def.unit}` : s
}
/** Which schedulers hold the best value; empty if every scheduler is tied (nothing to celebrate). */
export function bestSchedulers(vals: Partial<Record<SchedulerId, number | null>>, better: 'lower' | 'higher'): SchedulerId[] {
  const e = SCHEDULERS.map(s => [s, vals[s]] as const).filter(([, v]) => v != null) as [SchedulerId, number][]
  if (e.length < 2) return []
  const best = better === 'lower' ? Math.min(...e.map(x => x[1])) : Math.max(...e.map(x => x[1]))
  const hit = e.filter(x => Math.abs(x[1] - best) < 1e-12).map(x => x[0])
  return hit.length === e.length ? [] : hit
}
