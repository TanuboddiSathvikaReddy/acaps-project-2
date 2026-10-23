import type { CSSProperties } from 'react'
import type { TrafficClass } from '../api/types'
import { TRAFFIC_CLASSES } from '../api/types'
import { useApp } from '../state/store'
import { CLASS_LABEL, describeScenario, fmtNum } from '../lib/format'
import { setMixShare } from '../lib/mix'
import type { ConfigForm } from '../state/config'
import { ClassGlyph } from './Icons'
import { Banner, Expand, Segmented, Slider } from './ui'
import { ErrorState, LoadingState } from './States'

/* ============================== presets ============================== */
const CONTROLS = ['sizeNeutralControl', 'emergencyBurstSizeNeutral', 'networkOverloadSizeNeutral']
const MAIN = ['normalTraffic', 'heavyTraffic', 'videoHeavy', 'emergencyBurst', 'mixedTraffic', 'networkOverload']

/** One compact preset selector (design brief §4A: "simplify the existing preset-card wall into
 * one clean preset selector") instead of a grid of large cards. The selected preset's own
 * description and load badge appear as a single line underneath — no card, no repetition. */
export function PresetRow() {
  const { s, pickScenario } = useApp()
  const { status, list } = s.scenarios
  if (status === 'loading' || status === 'idle') return <div className="ctl-help">Loading scenario presets…</div>
  if (status === 'error') return <Banner tone="warn">Scenario presets could not be loaded. You can still configure a custom run below.</Banner>
  const by = (n: string) => list.find(x => x.name === n)
  const main = MAIN.map(by).filter((x): x is NonNullable<typeof x> => !!x)
  const controls = CONTROLS.map(by).filter((x): x is NonNullable<typeof x> => !!x)
  const active = main.find(sc => sc.name === s.form.scenario) ?? controls.find(sc => sc.name === s.form.scenario)
  const d = active?.config.derived
  return (
    <div>
      <Segmented label="Scenario preset" value={s.form.scenario} onChange={v => pickScenario(v)} options={main.map(sc => ({ value: sc.name, label: sc.label }))} />
      {active && (
        <div className="row spread" style={{ marginTop: 10, gap: 10, flexWrap: 'wrap' }}>
          <span className="small muted">{describeScenario(active.description)}</span>
          {d && <span className={`badge ${d.offeredLoad >= 1 ? 'bad' : d.offeredLoad >= 0.8 ? 'warn' : 'ok'}`}>{d.offeredLoad >= 1 ? 'Overloaded' : d.offeredLoad >= 0.8 ? 'Near capacity' : 'Under capacity'} · {fmtNum(active.config.incomingRate)} pkt/s · {active.config.linkBandwidthMbps} Mbps</span>}
        </div>
      )}
      {controls.length > 0 && (
        <Expand title={<span>Size-neutral variants <span className="muted small">· same load, one packet size per class</span></span>}>
          <p className="small muted" style={{ marginBottom: 10, maxWidth: '70ch' }}>These rerun a scenario with identical arrivals, classes, deadlines and bandwidth, but one shared packet size — isolating scheduling effects from packet-size effects.</p>
          <Segmented label="Size-neutral variant" value={controls.some(sc => sc.name === s.form.scenario) ? s.form.scenario : controls[0].name} onChange={v => pickScenario(v)} options={controls.map(sc => ({ value: sc.name, label: sc.label }))} />
        </Expand>
      )}
    </div>
  )
}

/* ============================== a single control ============================== */
export function Control({ name, unit, help, value, min, max, step, onChange, error, edited, field, digits }: {
  name: string; unit: string; help: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; error?: string; edited?: boolean; field: string; digits?: number
}) {
  const id = `ctl-${field}`
  return (
    <div className="ctl">
      <div className="ctl-top">
        <label className="ctl-name" htmlFor={id}>{name}{edited && <span className="badge neutral" style={{ marginLeft: 10 }} title="Differs from the selected scenario">edited</span>}</label>
        <div className="ctl-val">
          <input id={id} className="num" type="number" inputMode="decimal" value={Number.isFinite(value) ? +value.toFixed(digits ?? 2) : ''} min={0} step={step} aria-invalid={!!error} aria-describedby={`${id}-h`} onChange={e => onChange(e.target.value === '' ? NaN : Number(e.target.value))} />
          <span className="ctl-unit">{unit}</span>
        </div>
      </div>
      <Slider id={`${id}-s`} value={value} min={min} max={max} step={step} onChange={onChange} label={`${name} slider`} />
      <div id={`${id}-h`} className={error ? 'ctl-err' : 'ctl-help'} role={error ? 'alert' : undefined}>{error ?? help}</div>
    </div>
  )
}

/* ============================== traffic mix ============================== */
const INK_ON: Record<TrafficClass, string> = { emergency: '#0a1120', video: '#04121c', gps: '#12082e', normal: '#0a1120' }

/** The four sliders below are the only way to edit the mix (design brief §4A: "remove the
 * duplicate mechanism that edits the same mix through a second draggable control"). This bar is a
 * read-only, non-interactive echo of their current values — a quick proportional glance, not a
 * second control — so there's exactly one way to change the mix and one place that shows it. */
export function TrafficMix() {
  const { s, setForm, scenarioCfg } = useApp()
  const mix = s.form.mix
  const cfg = scenarioCfg()?.config
  return (
    <div>
      <div className="row spread">
        <div className="eyebrow">Traffic mix</div>
        <span className="badge ok mix-total"><b className="num">100%</b> total, always</span>
      </div>
      <div className="mix-bar" aria-hidden>
        {TRAFFIC_CLASSES.map(c => (
          <div key={c} className="mix-seg" style={{ flexGrow: Math.max(mix[c], 0.0001), flexBasis: 0, background: c === 'gps' ? 'var(--mix-fill-gps)' : `var(--c-${c})`, color: INK_ON[c], position: 'relative' } as CSSProperties}>
            {mix[c] >= 9 && <span><ClassGlyph cls={c} size={12} /> {mix[c]}%</span>}
          </div>
        ))}
      </div>
      <div className="mix-cards">
        {TRAFFIC_CLASSES.map(c => {
          const cc = cfg?.classes?.[c]
          return (
            <div key={c} className="mix-card">
              <div className="top"><span className="cls small"><ClassGlyph cls={c} />{CLASS_LABEL[c]}</span><span className="pct num">{mix[c]}<small className="muted" style={{ fontSize: '.5em' }}>%</small></span></div>
              <Slider value={mix[c]} min={0} max={100} step={1} onChange={v => setForm({ mix: setMixShare(mix, c, v) })} label={`${CLASS_LABEL[c]} share`} />
              <span className="meta">{cc ? `rank ${cc.criticalityRank} · ${cc.delayBudgetMs} ms delay budget` : 'share of generated packets'}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ============================== packet size ============================== */
/** ONE simple control, per the product decision to hide the backend's size-model complexity
 * (fixed/uniform/discrete, min/max, probabilities, per-class editors) from ordinary users. See
 * buildRequest in state/config.ts for exactly how this single number reaches the backend. */
export function PacketSizeControl() {
  const { s, setForm, scenarioCfg } = useApp()
  const f = s.form
  const base = scenarioCfg()?.config
  const num = (v: string) => (v === '' ? NaN : Number(v))
  const touched = base != null && f.packetSize !== base.packetSize
  return (
    <div className="ctl">
      <div className="ctl-top"><label className="ctl-name" htmlFor="ctl-size">Packet Size{touched && <span className="badge neutral" style={{ marginLeft: 10 }}>edited</span>}</label>
        <div className="ctl-val"><input id="ctl-size" className="num" type="number" min={1} value={Number.isFinite(f.packetSize) ? f.packetSize : ''} onChange={e => setForm({ packetSize: num(e.target.value) })} aria-invalid={!!s.issues.find(i => i.field === 'packetSize')} /><span className="muted">bytes</span></div>
      </div>
      <div className={s.issues.find(i => i.field === 'packetSize') ? 'ctl-err' : 'ctl-help'}>
        {s.issues.find(i => i.field === 'packetSize')?.message ?? (touched
          ? 'Every traffic class now uses this fixed size.'
          : "Left at the scenario's own size — some scenarios vary size by traffic class.")}
      </div>
    </div>
  )
}

/* ============================== full configuration column ============================== */
/** One compact panel: Scenario → Network → Traffic mix → Packet size → Run. No manual burst
 * editor and no expired-packet-policy control (design brief §4A) — scenario-defined bursts and
 * the backend's own expired-packet policy still apply exactly as the chosen scenario defines them
 * (see formFromScenario/buildRequest in state/config.ts); there just isn't a user-facing control
 * for them, since neither is necessary for the normal simulation workflow. */
export function ConfigColumn({ onRun }: { onRun?: () => void } = {}) {
  const { s, setForm, scenarioCfg, run } = useApp()
  const f = s.form, base = scenarioCfg()?.config
  const err = (field: string) => s.issues.find(i => i.field === field)?.message
  const ed = (k: keyof ConfigForm, baseVal: number | undefined) => baseVal != null && f[k] !== baseVal
  return (
    <div className="glass pad-lg cfg-panel">
      <div className="cfg-sec">
        <div className="row spread" style={{ marginBottom: 6 }}><div className="eyebrow">Scenario</div><span className="small muted">Pick a preset, then adjust anything below.</span></div>
        <PresetRow />
      </div>
      <div className="cfg-div" />
      <div className="cfg-sec">
        <div className="eyebrow" style={{ marginBottom: 6 }}>Network</div>
        <Control field="incomingRate" name="Incoming Packet Rate" unit="packets/s" help="Average packets arriving each second, all traffic classes combined." value={f.incomingRate} min={50} max={2000} step={10} onChange={v => setForm({ incomingRate: v })} error={err('incomingRate')} edited={ed('incomingRate', base?.incomingRate)} digits={0} />
        <Control field="linkBandwidthMbps" name="Network Bandwidth" unit="Mbps" help="Capacity of the output link. It sets how long each packet takes to transmit." value={f.linkBandwidthMbps} min={1} max={100} step={0.5} onChange={v => setForm({ linkBandwidthMbps: v })} error={err('linkBandwidthMbps')} edited={ed('linkBandwidthMbps', base?.linkBandwidthMbps)} />
        <Control field="queueCapacity" name="Queue Capacity" unit="packets" help="How many packets can wait. When the queue is full, new arrivals are dropped." value={f.queueCapacity} min={5} max={500} step={5} onChange={v => setForm({ queueCapacity: v })} error={err('queueCapacity')} edited={ed('queueCapacity', base?.queueCapacity)} digits={0} />
        <Control field="simulationDuration" name="Simulation Duration" unit="s" help="How long traffic is generated for. The queue then drains until every packet is delivered or dropped." value={f.simulationDuration} min={1} max={30} step={1} onChange={v => setForm({ simulationDuration: v })} error={err('simulationDuration')} edited={ed('simulationDuration', base?.simulationDuration)} digits={1} />
      </div>
      <div className="cfg-div" />
      <div className="cfg-sec">
        <TrafficMix />
        {err('mix') && <div className="ctl-err" role="alert" style={{ marginTop: 8 }}>{err('mix')}</div>}
      </div>
      <div className="cfg-div" />
      <div className="cfg-sec">
        <PacketSizeControl />
      </div>
      <div className="cfg-div" />
      <div className="cfg-sec">
        <button className="btn primary lg" style={{ width: '100%' }} onClick={() => { void run(); onRun?.() }} disabled={s.scenarios.status !== 'ready'}>Run Simulation</button>
      </div>
    </div>
  )
}

export function ScenariosGate({ children }: { children: React.ReactNode }) {
  const { s, retryScenarios } = useApp()
  if (s.scenarios.status === 'error') return <ErrorState title="Scenarios unavailable" note={s.scenarios.error ? `The scenario list could not be loaded: ${s.scenarios.error}` : 'The scenario list could not be loaded. Check that the ACAPS backend is running.'} action={<button className="btn primary" onClick={retryScenarios}>Retry</button>} />
  if (s.scenarios.status !== 'ready') return <LoadingState title="Loading scenarios" note="Reading presets from the backend." />
  return <>{children}</>
}
