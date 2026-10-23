import { CompareExplorer } from '../components/Compare'
import { EmptyState } from '../components/States'
import { useApp } from '../state/store'

/** Top-level "Compare" page (design brief §1, §12) — reads the current completed run directly
 * from the store; it does not request or compute anything of its own. */
export default function ComparePage({ go }: { go: (r: string) => void }) {
  const { s } = useApp()
  const view = s.run.phase === 'complete' ? s.run.view : null
  if (!view) {
    return (
      <div className="container">
        <div className="page-head">
          <div className="eyebrow"><span className="dot" />Compare</div>
          <h1>Nothing to compare yet.</h1>
        </div>
        <EmptyState title="Run a simulation first" note="FIFO, Static Priority and ACAPS are compared on a real completed run — there is nothing to show until one exists." action={<button className="btn primary" onClick={() => go('simulation')}>Go to Simulation</button>} />
      </div>
    )
  }
  return (
    <div className="container" style={{ paddingBottom: 90 }}>
      <div className="page-head">
        <div className="eyebrow"><span className="dot" />Compare · {view.raw.config.scenario ?? 'custom'}</div>
        <h1>Compare schedulers.</h1>
      </div>
      <CompareExplorer view={view} />
    </div>
  )
}
