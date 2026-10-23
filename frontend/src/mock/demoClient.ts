/**
 * DEMO DATA. Isolated on purpose.
 * Only used when VITE_DEMO_MODE=true (see lib/env.ts) — an explicit, developer-set build flag,
 * never a silent fallback when the live backend is unreachable (see api/source.ts). Fixtures in
 * /public/mock were produced offline by tools/make_demo_fixtures.py (a throwaway approximation,
 * NOT the backend). Everything served from here is flagged `demo: true` and the UI shows a
 * persistent "Demo data" badge. It is never presented as a real result.
 */
import type { ScenarioInfo, SimulationRequest, SimulationResponse } from '../api/types'

const DEMO_SCENARIOS = ['normalTraffic', 'heavyTraffic', 'emergencyBurst', 'videoHeavy', 'networkOverload', 'mixedTraffic']
const cache = new Map<string, unknown>()
async function load<T>(file: string): Promise<T> {
  if (cache.has(file)) return cache.get(file) as T
  const res = await fetch(`/mock/${file}`)
  if (!res.ok) throw new Error(`demo fixture ${file} missing`)
  const j = (await res.json()) as T
  cache.set(file, j)
  return j
}

export const demoClient = {
  scenarios: () => load<ScenarioInfo[]>('scenarios.json'),
  async simulate(req: SimulationRequest): Promise<{ data: SimulationResponse; note: string }> {
    const name = req.scenario && DEMO_SCENARIOS.includes(req.scenario) ? req.scenario : 'networkOverload'
    const data = await load<SimulationResponse>(`simulate-${name}.json`)
    return {
      data,
      note: `Pre-generated demo fixture for “${name}” (${data.config.simulationDuration} s). Demo mode is on (VITE_DEMO_MODE=true); your exact parameters were not applied.`,
    }
  },
}
