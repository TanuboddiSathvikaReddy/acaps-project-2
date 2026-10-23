/** Wire types for ACAPS API schema 1.0 (docs/API.md, docs/openapi.json). camelCase, times: packet-level µs, aggregates ms. */

export type TrafficClass = 'emergency' | 'video' | 'gps' | 'normal'
export const TRAFFIC_CLASSES: TrafficClass[] = ['emergency', 'video', 'gps', 'normal']
export type SchedulerId = 'FIFO' | 'STATIC_PRIORITY' | 'ACAPS'
export const SCHEDULERS: SchedulerId[] = ['FIFO', 'STATIC_PRIORITY', 'ACAPS']
export type Congestion = 'LOW' | 'MEDIUM' | 'HIGH'
export type Outcome = 'ON_TIME' | 'LATE' | 'DROPPED'
export type DropReason = 'QUEUE_OVERFLOW' | 'DEADLINE_EXPIRED'
export type Tier = 'AT_RISK' | 'SAFE' | 'INFEASIBLE'
export type ExpiredPacketPolicy = 'TRANSMIT_LATE' | 'DROP_EXPIRED'
export type ReasonCode =
  | 'ONLY_CANDIDATE' | 'FIFO_HEAD' | 'STATIC_PRIORITY_CLASS' | 'AT_RISK_LEAST_SLACK'
  | 'SAFE_BY_CRITICALITY' | 'SAFE_AGING_CHANGED_CHOICE' | 'INFEASIBLE_TRIAGE'
export type EventType =
  | 'PACKET_CREATED' | 'PACKET_ARRIVED' | 'PACKET_QUEUED' | 'SCHEDULER_DECISION'
  | 'PACKET_TRANSMISSION_STARTED' | 'PACKET_TRANSMISSION_COMPLETED' | 'PACKET_DROPPED' | 'DEADLINE_MISSED'

export type SizeModel =
  | { type: 'fixed'; bytes: number }
  | { type: 'uniform'; minBytes: number; maxBytes: number }
  | { type: 'discrete'; values: { bytes: number; probability: number }[] }

export interface ClassConfig { criticalityRank: number; delayBudgetMs: number; sizeModel: SizeModel }
export interface Burst { startTime: number; duration: number; rateMultiplier: number; trafficMixOverride?: Record<TrafficClass, number> }

export interface Derived {
  linkBandwidthBps: number; meanPacketSizeBytes: number; offeredLoad: number; equivalentPacketRatePps: number
  fifoWaitBoundUs?: number; burstOfferedLoad: number[]; byClass: Record<string, Record<string, number>>; warnings: string[]
}
export interface ResolvedConfig {
  scenario: string | null
  incomingRate: number; linkBandwidthMbps: number; queueCapacity: number; packetSize: number
  simulationDuration: number; randomSeed: number
  trafficMix: Record<TrafficClass, number>
  classes: Record<TrafficClass, ClassConfig>
  arrivalModel: string; bursts: Burst[]; expiredPacketPolicy: ExpiredPacketPolicy
  congestionThresholds: { medium: number; high: number }
  aging: { quantumFraction: number; maxPromotionLevels: number }
  starvation: { excessiveWaitFraction: number }
  observedRateWindowMs: number
  derived?: Derived
}

/** What the UI may send. Every field optional; the backend resolves base -> scenario -> request. */
export interface SimulationRequest {
  scenario?: string | null
  incomingRate?: number; linkBandwidthMbps?: number; queueCapacity?: number; packetSize?: number
  simulationDuration?: number; randomSeed?: number
  trafficMix?: Record<TrafficClass, number>
  classes?: Partial<Record<TrafficClass, Partial<ClassConfig>>>
  bursts?: Burst[]
  expiredPacketPolicy?: ExpiredPacketPolicy
  aging?: { quantumFraction: number; maxPromotionLevels: number }
  options?: {
    includeEventLog?: boolean; includeDecisions?: boolean; includeDecisionCandidates?: boolean
    includeQueueTimeline?: boolean; includeSizeNeutralControl?: boolean; maxTimelinePoints?: number
  }
}
export interface ExperimentRequest extends SimulationRequest { runs?: number }

export interface ScenarioInfo { name: string; label: string; description: string; config: ResolvedConfig }

export interface ComparisonBlock {
  baseline: SchedulerId
  metricDirections: { overall: Record<string, 'lower' | 'higher'>; perClass: Record<string, 'lower' | 'higher'> }
  metrics: Record<string, Record<SchedulerId, number | null>>
  deltasVsFifo: Record<string, Partial<Record<SchedulerId, number | null>>>
  perClass: Record<string, { metrics: Record<string, Record<SchedulerId, number | null>>; deltasVsFifo: Record<string, Partial<Record<SchedulerId, number | null>>> }>
}

export interface WirePacket {
  packetId: number; trafficClass: TrafficClass; arrivalTimeUs: number; sizeBytes: number
  source: string; destination: string; criticalityRank: number; delayBudgetUs: number; deadlineUs: number
}
export interface PacketRecord {
  packetId: number; outcome: Outcome | null; dropReason: DropReason | null
  enqueueTimeUs: number | null; txStartUs: number | null; txEndUs: number | null; dropTimeUs: number | null
  waitingTimeUs: number | null; serviceTimeUs: number | null; totalDelayUs: number | null
  deadlineMissed: boolean; overtakenCount: number
}
export interface QueuePoint {
  timeUs: number; queueLength: number; occupancy: number; congestionLevel: Congestion; serverBusy: boolean
  observedArrivalRatePps: number; observedArrivalRateBps: number; observedDepartureRatePps: number; observedDepartureRateBps: number
}
export interface DecisionDetails {
  tier?: Tier; agingChangedChoice?: boolean; waitingTimeUs?: number; remainingDeadlineUs?: number; slackUs?: number
  criticalityRank?: number; effectiveRank?: number; liveWorkUs?: number; atRiskCount?: number; safeCount?: number; infeasibleCount?: number
}
export interface Decision {
  timeUs: number; chosenPacketId: number; chosenClass: TrafficClass; queueLength: number; occupancy: number
  congestionLevel: Congestion; reasonCode: ReasonCode; details: DecisionDetails; candidates?: Record<string, unknown>[]
}
export interface SimEvent { timeUs: number; type: EventType; packetId: number | null; data: Record<string, unknown> }

export type MetricBlock = Record<string, number | null> & { congestionTimeShare?: never }
export interface QueueMetrics {
  meanQueueLength: number; meanOccupancy: number; maxQueueLength: number; maxOccupancy: number
  congestionTimeShare: Record<Congestion, number>
}
export interface SchedulerMetrics { overall: Record<string, number | null>; perClass: Record<string, Record<string, number | null>>; queue: QueueMetrics }
export interface SchedulerRun {
  metrics: SchedulerMetrics; packets: PacketRecord[]; queueTimeline?: QueuePoint[]; decisions?: Decision[]; events?: SimEvent[]
}
export interface SimulationResponse {
  schemaVersion: string; config: ResolvedConfig
  workload: { fingerprint: string; packetCount: number; packets: WirePacket[] }
  schedulers: Record<SchedulerId, SchedulerRun>
  comparison?: ComparisonBlock; sizeNeutralControl?: unknown
}

export interface Stat { mean: number | null; std: number | null; min: number | null; max: number | null; n: number }
export type StatTree = { [k: string]: Stat | StatTree }
export interface ExperimentResponse {
  schemaVersion: string; config: ResolvedConfig; baseSeed: number; runCount: number
  runs: { seed: number; workloadFingerprint: string; packetCount: number; schedulers: Record<SchedulerId, SchedulerMetrics> }[]
  aggregate: Record<SchedulerId, StatTree>
  pairedDeltasVsFifo: Partial<Record<SchedulerId, StatTree>>
  sizeNeutralControl?: {
    scenario: string
    runs: { seed: number; workloadFingerprint: string; packetCount: number; schedulers: Record<SchedulerId, SchedulerMetrics> }[]
    aggregate: Record<SchedulerId, StatTree>
    pairedDeltasVsFifo: Partial<Record<SchedulerId, StatTree>>
  }
}

export interface ApiValidationError { detail: { loc: (string | number)[]; msg: string; type: string }[] }
