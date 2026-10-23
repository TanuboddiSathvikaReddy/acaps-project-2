import { useEffect, useMemo, useRef, useState } from 'react'
import type { RunView } from '../adapters/run'
import { SCHEDULERS, type SchedulerId } from '../api/types'
import { useReducedMotion } from '../hooks'
import { CLASS_LABEL, SCHED_LABEL, cssVarSched, fmtClock } from '../lib/format'
import { useApp } from '../state/store'
import { Clock, decisionAt, PlaybackModel, type Snap } from '../visuals/playback'
import { FlowCanvas } from '../visuals/FlowCanvas'
import { ClassGlyph, Pause, Play, Skip } from './Icons'
import { DecisionCard } from './DecisionCard'
import { SchedulerOrder } from './SchedulerOrder'
import { Segmented, Slider } from './ui'

const SPEEDS = [{ v: '0.03', l: '0.03×' }, { v: '0.1', l: '0.1×' }, { v: '0.25', l: '0.25×' }, { v: '1', l: '1×' }]

/**
 * The simulation's primary visual (design brief §4B): packet-flow visualization, full width and
 * spacious. The separate Network State dashboard and queue-over-time chart that used to sit beside
 * it were removed — the canvas itself already draws queue length, congestion, link state and
 * delivered/dropped counts (see visuals/FlowCanvas.tsx), so the dashboard only repeated them in a
 * second form, and queue-over-time belongs with the rest of the outcome analysis on Results.
 * Scheduler Selection Order and the ACAPS Decision Basis panel follow directly below, matching the
 * brief's four-area structure: Traffic Configuration → Packet-Flow Visualization → Scheduler
 * Selection Order → ACAPS Decision Factors.
 */
export function Playback({ view }: { view: RunView }) {
  const { s, setScheduler, selectPacket } = useApp()
  const reduced = useReducedMotion()
  const sched = s.scheduler
  const model = useMemo(() => new PlaybackModel(view, sched), [view, sched])
  const clock = useMemo(() => { const c = new Clock(view.endUs); c.playing = !reduced; return c }, [view, reduced])
  const snapRef = useRef<Snap | null>(null)
  const [speed, setSpeed] = useState('0.1')
  const [playing, setPlaying] = useState(!reduced)
  useEffect(() => { clock.speed = Number(speed) }, [speed, clock])
  // carry the clock position across scheduler switches so "same workload, different decision" is comparable
  const carry = useRef(0)
  useEffect(() => { clock.seek(carry.current) }, [model, clock])
  useEffect(() => { const id = setInterval(() => { carry.current = clock.t; if (clock.playing !== playing && clock.t >= clock.end) setPlaying(false) }, 250); return () => clearInterval(id) }, [clock, playing])
  const t = clock.t
  const cfg = view.raw.config
  const toggle = () => { if (clock.t >= clock.end) clock.seek(0); clock.playing = !clock.playing; setPlaying(clock.playing) }
  const step = (dir: 1 | -1) => { clock.playing = false; setPlaying(false); const n = dir > 0 ? model.nextDecisionAfter(clock.t) : model.prevDecisionBefore(clock.t); if (n != null) clock.seek(n) }

  return (
    <div className="stack">
      <div style={{ position: 'relative' }}>
        <FlowCanvas model={model} clock={clock} snapRef={snapRef} selectedId={s.packetId} onSelect={selectPacket} queueCapacity={cfg.queueCapacity}
          label={`Packet flow for ${SCHED_LABEL[sched]}: traffic enters a queue, the scheduler selects packets, and they are transmitted or dropped. Use the transport controls to play, pause and step.`} />
        <div className="flow-hud">
          <Segmented label="Scheduler" value={sched} onChange={setScheduler} options={SCHEDULERS.map((x: SchedulerId) => ({ value: x, label: SCHED_LABEL[x], swatch: cssVarSched(x) }))} />
          <div className="glass tight row" style={{ padding: '8px 14px', gap: 14 }} aria-label="Legend">
            {(['emergency', 'video', 'gps', 'normal'] as const).map(c => <span key={c} className="cls small"><ClassGlyph cls={c} />{CLASS_LABEL[c]}</span>)}
          </div>
        </div>
      </div>
      <div className="glass transport" role="group" aria-label="Playback controls">
        <button className="icon-btn" onClick={() => step(-1)} aria-label="Previous decision" style={{ transform: 'scaleX(-1)' }}><Skip /></button>
        <button className="btn primary sm" onClick={toggle} aria-label={playing ? 'Pause' : 'Play'} style={{ minWidth: 92 }}>{playing ? <><Pause /> Pause</> : <><Play /> {clock.t >= clock.end ? 'Replay' : 'Play'}</>}</button>
        <button className="icon-btn" onClick={() => step(1)} aria-label="Next decision"><Skip /></button>
        <div className="scrub"><Slider value={t} min={0} max={view.endUs} step={1000} label="Simulation time" onChange={v => { clock.seek(v) }} /></div>
        <span className="clock" aria-label="Simulation time">{fmtClock(t)}</span>
        <Segmented label="Playback speed" role="group" value={speed} onChange={setSpeed} options={SPEEDS.map(x => ({ value: x.v, label: x.l }))} />
      </div>
      <p className="small muted" style={{ margin: '2px 4px 0' }}>Playback speed is simulated seconds per real second. Rings show the share of each packet’s delay budget left. Queue contents and counters always come from the recorded run.</p>

      <div style={{ marginTop: 14 }}><SchedulerOrder view={view} /></div>
      <div style={{ marginTop: 14 }}><DecisionCard d={decisionAt(view, 'ACAPS', t)} view={view} /></div>
    </div>
  )
}
