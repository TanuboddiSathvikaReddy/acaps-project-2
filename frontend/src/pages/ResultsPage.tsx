import { Results } from '../components/Results'
import { EmptyState } from '../components/States'
import { useApp } from '../state/store'

/** Top-level "Results" page (design brief §1, §11) — reads the current completed run directly
 * from the store; it does not request or compute anything of its own. */
export default function ResultsPage({ go }: { go: (r: string) => void }) {
  const { s } = useApp()
  const view = s.run.phase === 'complete' ? s.run.view : null
  if (!view) {
    return (
      <div className="container">
        <div className="page-head">
          <div className="eyebrow"><span className="dot" />Results</div>
          <h1>No results yet.</h1>
        </div>
        <EmptyState title="Run a simulation first" note="Results are measured from a real simulation run — there is nothing to show until one completes." action={<button className="btn primary" onClick={() => go('simulation')}>Go to Simulation</button>} />
      </div>
    )
  }
  return (
    <div className="container" style={{ paddingBottom: 90 }}>
      <div className="page-head">
        <div className="eyebrow"><span className="dot" />Results · {view.raw.config.scenario ?? 'custom'}</div>
        <h1>Measured results.</h1>
      </div>
      <Results view={view} onOpen={tab => go(tab === 'compare' ? 'compare' : 'simulation')} />
    </div>
  )
}
