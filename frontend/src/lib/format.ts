import type { Congestion, TrafficClass, SchedulerId } from '../api/types'

export const usToMs = (us: number) => us / 1000
export function fmtMs(ms: number | null | undefined, digits = 1): string {
  if (ms == null || Number.isNaN(ms)) return '—'
  return ms.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}
export function fmtUs(us: number | null | undefined): string {
  if (us == null) return '—'
  if (Math.abs(us) >= 1000) return `${(us / 1000).toLocaleString('en-US', { maximumFractionDigits: 2 })} ms`
  return `${Math.round(us)} µs`
}
export function fmtClock(us: number): string {
  const s = Math.floor(us / 1e6), ms = Math.floor((us % 1e6) / 1000)
  return `${String(s).padStart(2, '0')}:${String(ms).padStart(3, '0')}`
}
export function fmtNum(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}
export function fmtPct(fraction: number | null | undefined, digits = 1): string {
  if (fraction == null || Number.isNaN(fraction)) return '—'
  return `${(fraction * 100).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })}%`
}
export function fmtBps(bps: number | null | undefined): string {
  if (bps == null) return '—'
  if (bps >= 1e6) return `${(bps / 1e6).toFixed(2)} Mbps`
  if (bps >= 1e3) return `${(bps / 1e3).toFixed(1)} kbps`
  return `${bps.toFixed(0)} bps`
}

// Frontend display names only — the backend's traffic-class keys (emergency/video/gps/normal)
// and their semantics are unchanged (see docs/ASSUMPTIONS.md). This is purely a presentation
// relabeling to make the traffic model read as recognizable application types.
export const CLASS_LABEL: Record<TrafficClass, string> = { emergency: 'Voice', video: 'Video', gps: 'Telemetry', normal: 'Data' }

// Realistic per-packet display alias (e.g. "VIDEO-377"), deterministic from the real backend
// packetId — never a separate frontend ID system. The same packet keeps the same alias
// everywhere: queue, transmission, inspector, events, decisions.
const CLASS_PREFIX: Record<TrafficClass, string> = { emergency: 'VOICE', video: 'VIDEO', gps: 'TELE', normal: 'DATA' }
export const packetAlias = (cls: TrafficClass, id: number): string => `${CLASS_PREFIX[cls]}-${id}`
export const SCHED_LABEL: Record<SchedulerId, string> = { FIFO: 'FIFO', STATIC_PRIORITY: 'Static Priority', ACAPS: 'ACAPS' }
export const CONGESTION_LABEL: Record<Congestion, string> = { LOW: 'Low', MEDIUM: 'Medium', HIGH: 'High' }

// Meaning + formula (where one applies) + unit + interpretation, for every factor shown in the
// Decision Basis. Shown via Term (hover/focus/tap, see components/ui.tsx).
export const TERM_EXPLAIN: Record<string, string> = {
  criticality: 'How important the packet is, based on its traffic class. Taken from the configured criticality rank — 0 is the most critical class.',
  waiting: 'How long the packet has been waiting in the queue. Waiting Time = Current Time − Arrival Time. Unit: ms.',
  remaining: 'How much time remains before the packet’s deadline. Time Left = Deadline − Current Time. Unit: ms. Positive means time remains; zero or negative means the deadline has been reached or passed.',
  service: 'How long this packet takes to transmit over the link. Service Time (ms) = (Packet Size (B) × 8) ÷ (Bandwidth (Mbps) × 1000). Unit: ms.',
  slack: 'How much room the packet has before its deadline becomes impossible to meet. Slack = Time Left − Service Time. Unit: ms. Positive: can still meet the deadline. Small: needs attention soon. Negative: already too late.',
  queueOccupancy: 'How much of the waiting queue is currently occupied. Queue Occupancy = Queue Length ÷ Queue Capacity. Unit: %. Example: 18/50 = 36%.',
  deadline: 'The latest time by which the packet should finish transmission. Deadline = Arrival Time + Delay Budget.',
  serviceTime: 'How long the packet actually spent being transmitted. Service Time = Transmission End − Transmission Start. Unit: ms.',
  totalDelay: 'Total time from when the packet arrived until its transmission finished. Total Delay = Transmission End − Arrival Time. Unit: ms.',
  congestion: 'Current queue pressure, derived from the actual queue occupancy against this scenario’s configured congestion thresholds — not a number the scheduler compares directly.',
  effectiveRank: 'Criticality rank after bounded aging promotions — how long the packet waited moved it up, within a fixed limit.',
  AT_RISK: 'Would miss its deadline if it were sent last among packets that can still be saved.',
  SAFE: 'Would still make its deadline even if it were sent last.',
  INFEASIBLE: 'Cannot meet its deadline even if sent right now.',
}
/** The backend's own scenario descriptions (GET /scenarios) are real text, shown verbatim — except
 * for the one piece of internal jargon in some of them, the Greek-letter "rho" offered-load
 * notation (e.g. "rho ~ 1.08"). Design brief: "no seed or rho jargon appears in the user-facing
 * interface." This swaps that notation for plain words around the SAME number the backend sent —
 * nothing is fabricated or recomputed, only reworded, the same kind of presentational relabeling
 * as CLASS_LABEL below. */
export function describeScenario(description: string): string {
  return description.replace(/\(rho\s*~\s*([\d.]+)\)/gi, (_, v) => `(offered load ~${v}×)`)
}
export const cssVarClass = (c: TrafficClass) => `var(--c-${c})`
export const cssVarSched = (s: SchedulerId) => (s === 'FIFO' ? 'var(--sched-fifo)' : s === 'ACAPS' ? 'var(--sched-acaps)' : 'var(--sched-static)')
