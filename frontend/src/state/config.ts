import type { Burst, ExpiredPacketPolicy, ResolvedConfig, SimulationRequest, TrafficClass } from '../api/types'
import { TRAFFIC_CLASSES } from '../api/types'
import { mixFromFractions, mixToFractions } from '../lib/mix'

export interface ConfigForm {
  scenario: string
  incomingRate: number
  linkBandwidthMbps: number
  queueCapacity: number
  simulationDuration: number
  randomSeed: number
  mix: Record<TrafficClass, number> // integer percent, always sums to 100
  // A single visible number. The backend's per-class size-model complexity (fixed/uniform/discrete,
  // min/max, probabilities) is real and stays fully in force in every scenario until this is
  // deliberately changed — see the comment on `packetSize` in buildRequest below.
  packetSize: number
  bursts: Burst[]
  expiredPacketPolicy: ExpiredPacketPolicy
  // Aging (quantum fraction, max promotion levels) is intentionally NOT a form field: the backend
  // keeps its own values and the frontend never overrides them. See docs/ALGORITHMS.md.
}

// TRANSMIT_LATE mirrors the backend's own default (docs/ASSUMPTIONS.md), so an unmodified form
// matches what the backend would assume anyway. Overwritten by whichever scenario the user picks
// (formFromScenario), including on first load — see AppProvider's mount effect in state/store.tsx.
export const DEFAULT_FORM: ConfigForm = {
  scenario: 'networkOverload', incomingRate: 800, linkBandwidthMbps: 4, queueCapacity: 100, simulationDuration: 10, randomSeed: 42,
  mix: { emergency: 20, video: 30, gps: 20, normal: 30 }, packetSize: 1200,
  bursts: [], expiredPacketPolicy: 'TRANSMIT_LATE',
}

/** Populate the form from a backend-resolved scenario. Nothing is invented: values come from GET /scenarios. */
export function formFromScenario(name: string, c: ResolvedConfig, prev: ConfigForm): ConfigForm {
  return {
    ...prev, scenario: name, incomingRate: c.incomingRate, linkBandwidthMbps: c.linkBandwidthMbps, queueCapacity: c.queueCapacity,
    simulationDuration: c.simulationDuration, randomSeed: c.randomSeed, mix: mixFromFractions(c.trafficMix), packetSize: c.packetSize,
    bursts: c.bursts ?? [], expiredPacketPolicy: c.expiredPacketPolicy as ExpiredPacketPolicy,
  }
}

export interface FieldIssue { field: string; message: string }
/** Cheap client-side guard for obviously invalid input (the backend remains the authority and re-validates). */
export function validateForm(f: ConfigForm): FieldIssue[] {
  const out: FieldIssue[] = []
  const pos = (v: number, field: string, label: string) => { if (!(v > 0) || !Number.isFinite(v)) out.push({ field, message: `${label} must be greater than zero.` }) }
  pos(f.incomingRate, 'incomingRate', 'Incoming rate'); pos(f.linkBandwidthMbps, 'linkBandwidthMbps', 'Bandwidth')
  pos(f.queueCapacity, 'queueCapacity', 'Queue capacity'); pos(f.simulationDuration, 'simulationDuration', 'Duration')
  if (!Number.isInteger(f.queueCapacity)) out.push({ field: 'queueCapacity', message: 'Queue capacity must be a whole number of packets.' })
  if (!Number.isInteger(f.randomSeed)) out.push({ field: 'randomSeed', message: 'Must be a whole number.' })
  if (TRAFFIC_CLASSES.reduce((s, c) => s + f.mix[c], 0) !== 100) out.push({ field: 'mix', message: 'Traffic mix must total 100%.' })
  if (!(f.packetSize > 0)) out.push({ field: 'packetSize', message: 'Packet size must be greater than zero.' })
  return out
}

/** Build the request as a diff against the scenario, so preset semantics stay the backend's. */
export function buildRequest(f: ConfigForm, base: ResolvedConfig | undefined): SimulationRequest {
  const req: SimulationRequest = { scenario: f.scenario === 'custom' ? null : f.scenario }
  const diff = <K extends keyof ResolvedConfig>(k: K, v: ResolvedConfig[K], set: () => void) => { if (!base || JSON.stringify(base[k]) !== JSON.stringify(v)) set() }
  diff('incomingRate', f.incomingRate, () => (req.incomingRate = f.incomingRate))
  diff('linkBandwidthMbps', f.linkBandwidthMbps, () => (req.linkBandwidthMbps = f.linkBandwidthMbps))
  diff('queueCapacity', f.queueCapacity, () => (req.queueCapacity = f.queueCapacity))
  diff('simulationDuration', f.simulationDuration, () => (req.simulationDuration = f.simulationDuration))
  diff('randomSeed', f.randomSeed, () => (req.randomSeed = f.randomSeed))
  const mix = mixToFractions(f.mix)
  diff('trafficMix', mix, () => (req.trafficMix = mix))
  diff('bursts', f.bursts, () => (req.bursts = f.bursts))
  diff('expiredPacketPolicy', f.expiredPacketPolicy, () => (req.expiredPacketPolicy = f.expiredPacketPolicy))
  // Aging is never overridden from the frontend: no control exists for it, so the backend's own
  // resolved values (per scenario) are always used, exactly as if the field were never sent.
  //
  // Packet Size is presented as ONE control, but the backend models size per traffic class
  // (fixed/uniform/discrete). Leaving it untouched keeps the scenario's own per-class sizes
  // exactly as designed (e.g. small GPS packets, large video packets) — nothing is overridden.
  // Only when the user actually changes the number do we apply it uniformly to every class, using
  // the same `sizeModel: {type: fixed}` mechanism the backend already exposes (docs/API.md); this
  // is a presentation simplification of an existing mechanism, not a new one.
  diff('packetSize', f.packetSize, () => (req.packetSize = f.packetSize))
  if (base && f.packetSize !== base.packetSize) {
    req.classes = Object.fromEntries(TRAFFIC_CLASSES.map(c => [c, { sizeModel: { type: 'fixed' as const, bytes: f.packetSize } }])) as SimulationRequest['classes']
  }
  // Event logs and decision candidates are never requested — they are expensive (event logs
  // alone were ~21 MB of a ~33 MB response) and the simplified UI has no detail view that needs
  // per-event or per-candidate data; the decision card uses only the always-included `decisions`.
  req.options = { includeEventLog: false, includeDecisions: true, includeQueueTimeline: true, includeDecisionCandidates: false, maxTimelinePoints: 2000 }
  return req
}
