/**
 * Playback model: indexes the recorded timestamps of ONE scheduler run so the UI can replay it.
 * It only answers "what had already been recorded at clock time t". It never decides anything, never
 * recomputes waiting time / deadlines / congestion / metrics, and never invents events.
 */
import type { RunView, SchedulerView } from '../adapters/run'
import type { Decision, QueuePoint, SchedulerId } from '../api/types'

export interface Snap {
  t: number
  waiting: number[]            // packet ids currently in the queue, arrival order
  tx: number | null            // packet currently on the link
  recentArr: number[]; recentDep: number[]; recentDrop: number[]
  delivered: number; late: number; dropped: number
  point: QueuePoint | null; decision: Decision | null
}

const upper = <T>(a: T[], key: (x: T) => number, t: number) => { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (key(a[m]) <= t) lo = m + 1; else hi = m } return lo }

export class PlaybackModel {
  readonly view: RunView; readonly sv: SchedulerView; readonly id: SchedulerId
  private q: { id: number; enter: number; leave: number }[] = []
  private tx: { id: number; start: number; end: number; late: boolean }[] = []
  private drops: { id: number; time: number }[] = []
  private endsOnTime: number[] = []; private endsLate: number[] = []
  private lo = 0
  readonly endUs: number
  private readonly capacity: number

  constructor(view: RunView, id: SchedulerId) {
    this.view = view; this.id = id; this.sv = view.schedulers[id]; this.endUs = view.endUs
    this.capacity = view.raw.config.queueCapacity
    for (const r of this.sv.raw.packets) {
      if (r.enqueueTimeUs != null) this.q.push({ id: r.packetId, enter: r.enqueueTimeUs, leave: r.txStartUs ?? r.dropTimeUs ?? Infinity })
      if (r.txStartUs != null && r.txEndUs != null) this.tx.push({ id: r.packetId, start: r.txStartUs, end: r.txEndUs, late: r.outcome === 'LATE' })
      if (r.dropTimeUs != null) this.drops.push({ id: r.packetId, time: r.dropTimeUs })
    }
    this.q.sort((a, b) => a.enter - b.enter || a.id - b.id)
    this.tx.sort((a, b) => a.start - b.start)
    this.drops.sort((a, b) => a.time - b.time)
    for (const x of this.tx) (x.late ? this.endsLate : this.endsOnTime).push(x.end)
    this.endsOnTime.sort((a, b) => a - b); this.endsLate.sort((a, b) => a - b)
  }

  /** winUs: how far back (sim µs) "recent" arrivals / departures / drops reach; used for visual trails only. */
  snapshot(t: number, winUs: number, maxRecent = 70): Snap {
    const q = this.q
    while (this.lo > 0 && q[this.lo - 1].leave > t) this.lo--        // scrubbed backwards
    while (this.lo < q.length && q[this.lo].leave <= t && q[this.lo].enter <= t) this.lo++
    const waiting: number[] = []
    for (let i = this.lo; i < q.length && q[i].enter <= t; i++) if (q[i].leave > t) waiting.push(q[i].id)

    const pk = this.view.packets
    const a1 = upper(pk, p => p.arrivalTimeUs, t), a0 = upper(pk, p => p.arrivalTimeUs, t - winUs)
    const step = Math.max(1, Math.ceil((a1 - a0) / maxRecent))
    const recentArr: number[] = []; for (let i = a1 - 1; i >= a0; i -= step) recentArr.push(pk[i].packetId)

    const ti = upper(this.tx, x => x.start, t) - 1
    let cur: number | null = null
    if (ti >= 0 && this.tx[ti].end > t) cur = this.tx[ti].id
    const recentDep: number[] = []
    for (let i = ti; i >= 0 && recentDep.length < maxRecent; i--) { if (this.tx[i].end > t) continue; if (this.tx[i].end < t - winUs) break; recentDep.push(this.tx[i].id) }

    const d1 = upper(this.drops, x => x.time, t), recentDrop: number[] = []
    for (let i = d1 - 1; i >= 0 && recentDrop.length < 24; i--) { if (this.drops[i].time < t - winUs) break; recentDrop.push(this.drops[i].id) }

    // Canonical queue state: `waiting` above is exact (reconstructed from each packet's own
    // enqueue/leave timestamps, the same data the backend used). The backend's queueTimeline is
    // a separate, potentially DOWNSAMPLED stream (server-side maxTimelinePoints), so on a long or
    // busy run its nearest point can disagree with the exact count at this instant — that was the
    // source of the queue-count mismatch between the header and the canvas. Congestion level and
    // the observed arrival/departure rates are genuinely measured, sliding-window quantities that
    // only the backend computes, so those two fields still come from the nearest timeline point;
    // only queueLength/occupancy are corrected here, and every caller reads them from this one
    // `point` object, so the header, the canvas and this correction can never disagree again.
    const tl = this.sv.timeline
    const pi = upper(tl, p => p.timeUs, t) - 1
    const nearest = pi >= 0 ? tl[pi] : null
    const point: QueuePoint | null = nearest
      ? { ...nearest, queueLength: waiting.length, occupancy: waiting.length / this.capacity }
      : (this.capacity > 0 ? { timeUs: t, queueLength: waiting.length, occupancy: waiting.length / this.capacity, congestionLevel: 'LOW', serverBusy: cur != null, observedArrivalRatePps: 0, observedArrivalRateBps: 0, observedDepartureRatePps: 0, observedDepartureRateBps: 0 } : null)
    const dec = this.sv.decisions
    const di = upper(dec, d => d.timeUs, t) - 1
    return {
      t, waiting, tx: cur, recentArr, recentDep, recentDrop,
      delivered: upper(this.endsOnTime, x => x, t), late: upper(this.endsLate, x => x, t), dropped: d1,
      point, decision: di >= 0 ? dec[di] : null,
    }
  }

  /** Time (µs) of the previous / next scheduler decision, for step buttons. */
  nextDecisionAfter(t: number): number | null { const d = this.sv.decisions; const i = upper(d, x => x.timeUs, t); return i < d.length ? d[i].timeUs : null }
  prevDecisionBefore(t: number): number | null { const d = this.sv.decisions; const i = upper(d, x => x.timeUs, t - 1) - 1; return i >= 0 ? d[i].timeUs : null }
}

/** The most recent recorded decision for ONE named scheduler at clock time t, independent of
 * whichever scheduler the packet-flow visualization currently has selected. Used to keep the
 * ACAPS Decision Basis panel always showing ACAPS's own decision (design brief §4D: "Do not make
 * FIFO or Static Priority appear to use ACAPS's decision factors") even while the visualization is
 * displaying FIFO or Static Priority. Real recorded data only — no recomputation. */
export function decisionAt(view: RunView, id: SchedulerId, t: number): Decision | null {
  const dec = view.schedulers[id].decisions
  const i = upper(dec, d => d.timeUs, t) - 1
  return i >= 0 ? dec[i] : null
}

/** Mutable playback clock. One instance per mounted playback view. */
export class Clock {
  t = 0; playing = true; speed = 0.1 // simulated seconds per real second
  constructor(public end: number) {}
  advance(dtReal: number) {
    if (!this.playing) return
    this.t = Math.min(this.end, this.t + dtReal * this.speed * 1e6)
    if (this.t >= this.end) this.playing = false
  }
  seek(t: number) { this.t = Math.max(0, Math.min(this.end, t)) }
}
