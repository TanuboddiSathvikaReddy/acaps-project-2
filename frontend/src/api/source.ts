/**
 * Data source. In real mode (the default) this ONLY talks to the live API: any failure
 * (network, validation, server) is thrown as an ApiError and shown to the user, never masked.
 * Demo mode (VITE_DEMO_MODE=true, see lib/env.ts) is a separate, explicit path for development:
 * it always uses the isolated fixtures in mock/demoClient.ts and is never entered as a fallback
 * from real mode. The two modes never mix within one session.
 */
import { api } from './client'
import type { ScenarioInfo, SimulationRequest } from './types'
import { adaptSimulation, type RunView } from '../adapters/run'
import { DEMO_MODE } from '../lib/env'

export type Origin = 'live' | 'demo'

export async function loadScenarios(signal?: AbortSignal): Promise<{ list: ScenarioInfo[]; origin: Origin }> {
  if (DEMO_MODE) {
    const { demoClient } = await import('../mock/demoClient')
    return { list: await demoClient.scenarios(), origin: 'demo' }
  }
  return { list: await api.scenarios(signal), origin: 'live' }
}

export async function runSimulation(req: SimulationRequest, signal?: AbortSignal): Promise<RunView> {
  if (DEMO_MODE) {
    const { demoClient } = await import('../mock/demoClient')
    const { data, note } = await demoClient.simulate(req)
    return adaptSimulation(data, true, note)
  }
  return adaptSimulation(await api.simulate(req, signal))
}
