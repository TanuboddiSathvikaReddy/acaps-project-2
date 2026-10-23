import { lazy, Suspense, useEffect, useRef } from 'react'
import { Nav } from './components/Nav'
import { TipHost } from './components/ui'
import { useHashRoute, useRevealRoot, useScrollVar } from './hooks'
import { LoadingState } from './components/States'
import { Landing } from './pages/Landing'

const Simulation = lazy(() => import('./pages/Simulation'))
const ResultsPage = lazy(() => import('./pages/ResultsPage'))
const ComparePage = lazy(() => import('./pages/ComparePage'))

export function App() {
  const [route, go] = useHashRoute()
  useScrollVar()
  const prev = useRef(route)
  useEffect(() => { if (prev.current !== route) { window.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior }); prev.current = route } }, [route])
  useRevealRoot(route)
  // 'home' (an empty hash, or the brand mark) shows the Landing page again; Simulation/Results/
  // Compare are reached via the nav, unchanged otherwise.
  const page = route === 'simulation' ? <Simulation go={go} /> : route === 'results' ? <ResultsPage go={go} /> : route === 'compare' ? <ComparePage go={go} /> : <Landing go={go} />
  return (
    <>
      <div className="atmo" aria-hidden><div className="grid" /><div className="orb" /></div>
      <a className="sr-only" href="#main">Skip to content</a>
      <Nav route={route} go={go} />
      <main id="main" key={route} className="page">
        <Suspense fallback={<LoadingState title="Loading" note="Preparing this view." />}>{page}</Suspense>
      </main>
      <TipHost />
    </>
  )
}
