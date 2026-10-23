/**
 * API layer. The ONLY place that talks to the network.
 * Backend is the source of truth: nothing here (or anywhere in the UI) recomputes waiting time, deadlines,
 * congestion, ACAPS decisions or metrics.
 */
import type { ScenarioInfo, SimulationRequest, SimulationResponse } from './types'

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api/v1'

export class ApiError extends Error {
  constructor(public kind: 'network' | 'validation' | 'server', message: string, public status?: number, public fields?: { path: string; msg: string }[]) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(BASE + path, { ...init, signal, headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...init?.headers } })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError('network', 'The ACAPS backend could not be reached.')
  }
  if (res.ok) return (await res.json()) as T
  if (res.status === 422) {
    const body = await res.json().catch(() => null)
    const fields = Array.isArray(body?.detail)
      ? body.detail.map((d: { loc: (string | number)[]; msg: string }) => ({ path: d.loc.filter(x => x !== 'body').join('.'), msg: d.msg }))
      : [{ path: '', msg: String(body?.detail ?? 'Invalid configuration') }]
    throw new ApiError('validation', 'The backend rejected this configuration.', 422, fields)
  }
  // gateway errors mean nothing answered on the other side (e.g. dev proxy with no backend running)
  if ([502, 503, 504].includes(res.status)) throw new ApiError('network', 'The ACAPS backend could not be reached.', res.status)
  throw new ApiError('server', `The backend returned an error (HTTP ${res.status}).`, res.status)
}

// Note: the backend also serves POST /experiments (see docs/API.md); this frontend's UI no
// longer has a view that calls it, so no wrapper is kept here. The backend endpoint itself is
// untouched — see design brief §7: "Do not remove backend experiment endpoints ... simply
// because the user interface no longer exposes them."
export const api = {
  scenarios: (signal?: AbortSignal) => request<ScenarioInfo[]>('/scenarios', undefined, signal),
  simulate: (body: SimulationRequest, signal?: AbortSignal) => request<SimulationResponse>('/simulate', { method: 'POST', body: JSON.stringify(body) }, signal),
}
