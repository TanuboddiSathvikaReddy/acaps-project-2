import type { RunView } from '../adapters/run'
import type { Decision, Tier } from '../api/types'
import { CLASS_LABEL, fmtUs, packetAlias } from '../lib/format'
import { Check } from './Icons'
import { Expand, Term } from './ui'

export const tierTone = (t?: Tier) => (t === 'SAFE' ? 'ok' : t === 'AT_RISK' ? 'warn' : t === 'INFEASIBLE' ? 'bad' : 'neutral')
export function TierBadge({ tier }: { tier?: Tier }) {
  if (!tier) return null
  return <span className={`badge ${tierTone(tier)}`}>{tier === 'AT_RISK' && <Check />} {tier.replace('_', ' ')}</span>
}

/** The one compact decision summary line required by the design brief: a tier, an arrow, and a
 * short clause — never the verbose paragraph or internal promotion/rank numbers. */
function decisionSummary(d: Decision): string {
  const tier = d.details.tier
  if (d.reasonCode === 'ONLY_CANDIDATE') return 'Only packet waiting'
  if (tier === 'AT_RISK') return 'AT RISK → Least Slack'
  if (tier === 'INFEASIBLE') return 'INFEASIBLE → Triage'
  if (tier === 'SAFE') return d.reasonCode === 'SAFE_AGING_CHANGED_CHOICE' ? 'SAFE → Waiting moved this packet up' : 'SAFE → Effective Criticality, then Deadline'
  return d.reasonCode.replace(/_/g, ' ')
}

/**
 * ACAPS Decision Basis (design brief §4D) — the compact, always-visible "why this packet" panel.
 * Always shows ACAPS's own decision, never whichever scheduler the packet-flow visualization
 * currently has selected (the brief is explicit that FIFO and Static Priority must not appear to
 * use ACAPS's decision factors) — callers pass the ACAPS decision at the current playback time
 * (see decisionAt in visuals/playback.ts), independent of the visualization's own scheduler toggle.
 * Shows only Criticality, Waiting Time, Time Left, Service Time, Slack and Queue Occupancy, with
 * real backend values and a one-line decision summary, plus a small expandable for the formulas.
 * No packet inspector, no lifecycle, no candidate table, no decision-path essay, no internal
 * promotion counts or effective-rank values — those were deliberately left out.
 */
export function DecisionCard({ d, view }: { d: Decision | null; view: RunView }) {
  if (!d) return <div className="decision glass"><div className="eyebrow">ACAPS Decision Basis</div><p className="muted small">No decision yet. The first one is recorded when the link picks its first packet.</p></div>
  const pkt = view.pkt.get(d.chosenPacketId)
  const rec = view.schedulers.ACAPS.rec.get(d.chosenPacketId)
  const waitingUs = pkt ? d.timeUs - pkt.arrivalTimeUs : null
  const timeLeftUs = pkt ? pkt.deadlineUs - d.timeUs : null
  const serviceUs = rec?.serviceTimeUs ?? null
  const slackUs = timeLeftUs != null && serviceUs != null ? timeLeftUs - serviceUs : null
  return (
    <div className="decision glass">
      <div className="row spread"><span className="eyebrow">ACAPS Decision Basis</span><span className="mono small muted">t = {(d.timeUs / 1000).toFixed(0)} ms</span></div>
      <div className="who">
        <span className="pid num">{packetAlias(d.chosenClass, d.chosenPacketId)}</span><span className="muted">selected</span>
        <span className="cls small">{CLASS_LABEL[d.chosenClass]}</span>
      </div>
      <TierBadge tier={d.details.tier} />
      <div className="dgrid">
        <div><div className="k"><Term k="criticality">Criticality</Term></div><div className="v">{pkt ? pkt.criticalityRank : 'Not available'}</div></div>
        <div><div className="k"><Term k="waiting">Waiting Time</Term></div><div className="v">{waitingUs != null ? fmtUs(waitingUs) : 'Not available'}</div></div>
        <div><div className="k"><Term k="remaining">Time Left</Term></div><div className="v">{timeLeftUs != null ? fmtUs(timeLeftUs) : 'Not available'}</div></div>
        <div><div className="k"><Term k="service">Service Time</Term></div><div className="v">{serviceUs != null ? fmtUs(serviceUs) : 'Not available'}</div></div>
        <div><div className="k"><Term k="slack">Slack</Term></div><div className="v">{slackUs != null ? fmtUs(slackUs) : 'Not available'}</div></div>
        <div><div className="k"><Term k="queueOccupancy">Queue Occupancy</Term></div><div className="v">{Math.round(d.occupancy * 100)}%</div></div>
      </div>
      <p className="why" style={{ fontWeight: 600 }}>{decisionSummary(d)}</p>
      <Expand title="How is this calculated?">
        <div className="small muted num" style={{ display: 'grid', gap: 6 }}>
          <div><b>Waiting Time</b> = Current Time − Arrival Time</div>
          <div><b>Time Left</b> = Deadline − Current Time</div>
          <div><b>Service Time (ms)</b> = (Packet Size (B) × 8) ÷ (Bandwidth (Mbps) × 1000)</div>
          <div><b>Slack</b> = Time Left − Service Time</div>
          <div><b>Queue Occupancy</b> = Queue Length ÷ Queue Capacity</div>
        </div>
      </Expand>
    </div>
  )
}
