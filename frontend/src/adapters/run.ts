/**
 * Data adapters: turn wire responses into indexed, UI-friendly views.
 * Pure re-indexing only. No metric, deadline, waiting-time or scheduling computation happens here.
 */
import type {
  Decision, PacketRecord, QueuePoint, SchedulerId, SchedulerRun, SimEvent, SimulationResponse, Stat, StatTree, WirePacket,
} from '../api/types'
import { SCHEDULERS } from '../api/types'

export interface SchedulerView {
  id: SchedulerId
  raw: SchedulerRun
  rec: Map<number, PacketRecord>
  decisions: Decision[]
  decisionByPacket: Map<number, Decision>
  timeline: QueuePoint[]
  events: SimEvent[]
  /** packets sorted by (arrival, id) with leave-queue time, for playback scans */
  hasEvents: boolean
}
export interface RunView {
  raw: SimulationResponse
  demo: boolean
  demoNote?: string
  pkt: Map<number, WirePacket>
  packets: WirePacket[]
  durationUs: number
  endUs: number
  schedulers: Record<SchedulerId, SchedulerView>
}

export function adaptSimulation(raw: SimulationResponse, demo = false, demoNote?: string): RunView {
  const packets = raw.workload.packets
  const pkt = new Map(packets.map(p => [p.packetId, p]))
  let endUs = raw.config.simulationDuration * 1e6
  const schedulers = {} as Record<SchedulerId, SchedulerView>
  for (const id of SCHEDULERS) {
    const s = raw.schedulers[id]
    const rec = new Map(s.packets.map(r => [r.packetId, r]))
    const decisions = s.decisions ?? []
    const decisionByPacket = new Map(decisions.map(d => [d.chosenPacketId, d]))
    for (const r of s.packets) { if (r.txEndUs && r.txEndUs > endUs) endUs = r.txEndUs }
    schedulers[id] = { id, raw: s, rec, decisions, decisionByPacket, timeline: s.queueTimeline ?? [], events: s.events ?? [], hasEvents: !!s.events }
  }
  return { raw, demo, demoNote, pkt, packets, durationUs: raw.config.simulationDuration * 1e6, endUs, schedulers }
}


/** Walk a StatTree by path like "overall.deadlineMissRate" or "perClass.video.avgWaitingTimeMs". */
export function statAt(tree: StatTree | undefined, path: string): Stat | null {
  let cur: Stat | StatTree | undefined = tree
  for (const k of path.split('.')) {
    if (!cur || typeof cur !== 'object') return null
    cur = (cur as StatTree)[k]
  }
  return cur && 'mean' in (cur as Stat) ? (cur as Stat) : null
}

/** Final recorded state of one packet in one scheduler run (from backend timestamps and flags). */
export type FinalStatus = 'DELIVERED' | 'DEADLINE_MISSED' | 'DROPPED' | 'PENDING'
export function finalStatus(r: PacketRecord | undefined): FinalStatus {
  if (!r) return 'PENDING'
  if (r.outcome === 'DROPPED') return 'DROPPED'
  if (r.outcome === 'LATE') return 'DEADLINE_MISSED'
  if (r.outcome === 'ON_TIME') return 'DELIVERED'
  return 'PENDING'
}
