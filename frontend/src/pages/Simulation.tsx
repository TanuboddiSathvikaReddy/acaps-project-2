import { useEffect } from 'react'
import { ConfigColumn, ScenariosGate } from '../components/Setup'
import { RunOverlay } from '../components/RunOverlay'
import { Arrow, Reset } from '../components/Icons'
import { DemoBadge, Reveal, Banner } from '../components/ui'
import { Playback } from '../components/Playback'
import { ErrorState } from '../components/States'
import { useApp } from '../state/store'
import { fmtNum } from '../lib/format'

export default function Simulation({ go }: { go: (r: string) => void }) {
  const { s, run, reset } = useApp()
  const view = s.run.view
  const phase = s.run.phase
  const complete = phase === 'complete' && view
  // The completed-run layout replaces the setup form in place (no real page navigation), so the
  // browser does not reset scroll position on its own. Without this, a scroll position retained
  // from a long setup form can land the new page's fixed-position HUD controls directly under the
  // nav bar. A real navigation would reset this for free; this view transition needs it explicitly.
  useEffect(() => { if (complete) window.scrollTo({ top: 0, behavior: 'auto' }) }, [view]) // eslint-disable-line react-hooks/exhaustive-deps
  const busy = phase === 'validating' || phase === 'preparing' || phase === 'running'

  if (complete) {
    return (
      <div className="container" style={{ paddingBottom: 90 }}>
        <div className="page-head">
          <div className="row spread"><div className="eyebrow"><span className="dot" />Simulation · {view.raw.config.scenario ?? 'custom'}</div>{view.demo && <DemoBadge note={view.demoNote} />}</div>
          <h1>Watch the packets.</h1>
          {view.demo && <Banner tone="warn"><b>Demo data.</b> {view.demoNote}</Banner>}
        </div>
        <div className="ws-bar"><div className="glass ws-bar-inner">
          <div className="row" style={{ gap: 10 }}>
            <button className="btn quiet sm" onClick={() => go('results')}>Results <Arrow /></button>
            <button className="btn quiet sm" onClick={() => go('compare')}>Compare <Arrow /></button>
          </div>
          <div className="row" style={{ gap: 6 }}>
            <span className="small muted num" style={{ padding: '0 8px' }}>{fmtNum(view.raw.workload.packetCount)} packets</span>
            <button className="btn ghost sm" onClick={reset}><Reset /> New simulation</button>
          </div>
        </div></div>
        <div className="page" style={{ marginTop: 16 }}>
          <Playback view={view} />
        </div>
      </div>
    )
  }

  return (
    <div className="container" style={{ maxWidth: 760 }}>
      <div className="page-head">
        <div className="row spread"><div className="eyebrow"><span className="dot" />Simulation</div>{s.scenarios.origin === 'demo' && <span className="badge warn">Backend offline · demo data</span>}</div>
        <h1>Configure a network scenario to begin.</h1>
        <p className="lead">Choose a preset or set the network yourself, then run it. The backend generates one workload and replays it under FIFO, Static Priority and ACAPS.</p>
      </div>
      {phase === 'error' && s.run.error && (
        <Reveal><div className="glass" style={{ marginBottom: 20 }}>
          <ErrorState title={s.run.error.kind === 'validation' ? 'This configuration can’t run yet' : s.run.error.kind === 'network' ? 'The ACAPS backend isn’t reachable' : 'The simulation failed'} note={s.run.error.message} fields={s.run.error.fields}
            action={<button className="btn primary" onClick={() => void run()}>{s.run.error.kind === 'validation' ? 'Try again' : 'Retry'}</button>} />
        </div></Reveal>
      )}
      <ScenariosGate>
        <ConfigColumn />
      </ScenariosGate>
      {busy && <RunOverlay />}
    </div>
  )
}
