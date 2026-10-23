import { useEffect, useRef } from 'react'
import { useApp } from '../state/store'
import { Check } from './Icons'
import { NetworkScene } from '../visuals/NetworkScene'

// Three steps, matching the three real phases in state/store.tsx `run()`. There is no fourth
// "loading results" step: the response is parsed and stored as part of the 'running' phase
// completing, so a separate step for it would never actually show as distinct from 'running'.
const STEPS = [
  { id: 'validating', t: 'Validating configuration', d: 'Checking the settings before anything is sent.' },
  { id: 'preparing', t: 'Preparing simulation', d: 'Building the request for the ACAPS backend.' },
  { id: 'running', t: 'Running one shared workload', d: 'FIFO, Static Priority and ACAPS replay the same packets. This is the real request — its duration depends on the scenario.' },
]
export function RunOverlay() {
  const { s } = useApp()
  const step = useRef(0.6)
  const card = useRef<HTMLDivElement>(null)
  const returnFocus = useRef<HTMLElement | null>(null)
  const phase = s.run.phase
  const idx = phase === 'validating' ? 0 : phase === 'preparing' ? 1 : 2
  useEffect(() => { step.current = 0.5 + idx * 0.9 }, [idx])
  useEffect(() => {
    // Move focus into the dialog while it's up (it has no controls, so the card itself is the
    // target), and give it back to whatever triggered the run — normally the Run Simulation
    // button — once the overlay is gone.
    returnFocus.current = document.activeElement as HTMLElement | null
    card.current?.focus()
    return () => { returnFocus.current?.focus?.() }
  }, [])
  const label = STEPS[idx].t
  return (
    <div className="run-overlay" role="dialog" aria-modal="true" aria-label="Simulation in progress">
      <div ref={card} tabIndex={-1} className="run-card glass">
        <div><div className="eyebrow"><span className="dot" />Simulation</div><h2 className="title" style={{ marginTop: 10 }}>{label}</h2></div>
        <div className="run-stage"><NetworkScene stepRef={step} label="Illustration while the simulation runs" className="" /></div>
        <ol className="run-steps" aria-live="polite">
          {STEPS.map((st, i) => (
            <li key={st.id} className={i < idx ? 'done' : i === idx ? 'on' : ''}>
              <span className="ind"><Check /></span>
              <span><b style={{ display: 'block', fontWeight: 600 }}>{st.t}</b><span className="small muted">{st.d}</span></span>
              <span className="small muted num">{i < idx ? 'done' : i === idx ? '…' : ''}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  )
}
