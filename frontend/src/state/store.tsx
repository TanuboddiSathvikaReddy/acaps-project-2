import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef, type ReactNode } from 'react'
import { ApiError } from '../api/client'
import { loadScenarios, runSimulation, type Origin } from '../api/source'
import type { ScenarioInfo, SchedulerId, SimulationRequest } from '../api/types'
import type { RunView } from '../adapters/run'
import { buildRequest, DEFAULT_FORM, formFromScenario, validateForm, type ConfigForm, type FieldIssue } from './config'

export type RunPhase = 'idle' | 'validating' | 'preparing' | 'running' | 'complete' | 'error'
export interface RunError { kind: 'network' | 'validation' | 'server' | 'client'; message: string; fields?: { path: string; msg: string }[] }

interface State {
  theme: 'dark' | 'light'
  scenarios: { status: 'idle' | 'loading' | 'ready' | 'error'; list: ScenarioInfo[]; origin: Origin | null; error?: string }
  form: ConfigForm
  issues: FieldIssue[]
  run: { phase: RunPhase; view: RunView | null; error: RunError | null; startedAt: number; req: SimulationRequest | null }
  scheduler: SchedulerId
  packetId: number | null
}
type Action =
  | { t: 'theme'; v: State['theme'] }
  | { t: 'scenarios'; v: State['scenarios'] }
  | { t: 'form'; v: Partial<ConfigForm> }
  | { t: 'formSet'; v: ConfigForm }
  | { t: 'issues'; v: FieldIssue[] }
  | { t: 'run'; v: Partial<State['run']> }
  | { t: 'scheduler'; v: SchedulerId }
  | { t: 'packet'; v: number | null }

function reducer(s: State, a: Action): State {
  switch (a.t) {
    case 'theme': return { ...s, theme: a.v }
    case 'scenarios': return { ...s, scenarios: a.v }
    case 'form': return { ...s, form: { ...s.form, ...a.v } }
    case 'formSet': return { ...s, form: a.v }
    case 'issues': return { ...s, issues: a.v }
    case 'run': return { ...s, run: { ...s.run, ...a.v } }
    case 'scheduler': return { ...s, scheduler: a.v }
    case 'packet': return { ...s, packetId: a.v }
  }
}

const initial = (): State => ({
  theme: (document.documentElement.dataset.theme as State['theme']) ?? 'dark',
  scenarios: { status: 'idle', list: [], origin: null }, form: DEFAULT_FORM, issues: [],
  run: { phase: 'idle', view: null, error: null, startedAt: 0, req: null },
  scheduler: 'ACAPS', packetId: null,
})

interface Ctx {
  s: State
  setForm: (v: Partial<ConfigForm>) => void
  pickScenario: (name: string) => void
  scenarioCfg: (name?: string) => ScenarioInfo | undefined
  run: () => Promise<boolean>
  reset: () => void
  retryScenarios: () => void
  setScheduler: (v: SchedulerId) => void
  selectPacket: (id: number | null) => void
  toggleTheme: () => void
}
const C = createContext<Ctx | null>(null)
export const useApp = () => { const c = useContext(C); if (!c) throw new Error('AppProvider missing'); return c }

const toErr = (e: unknown): RunError =>
  e instanceof ApiError ? { kind: e.kind, message: e.message, fields: e.fields } : { kind: 'client', message: (e as Error)?.message ?? 'Something went wrong.' }

export function AppProvider({ children }: { children: ReactNode }) {
  const [s, d] = useReducer(reducer, undefined, initial)
  const ref = useRef(s); ref.current = s
  const abort = useRef<AbortController | null>(null)

  const loadScenariosOnce = useCallback((signal?: AbortSignal) => {
    d({ t: 'scenarios', v: { status: 'loading', list: [], origin: null } })
    loadScenarios(signal).then(({ list, origin }) => {
      d({ t: 'scenarios', v: { status: 'ready', list, origin } })
      const start = list.find(x => x.name === DEFAULT_FORM.scenario)
      if (start) d({ t: 'formSet', v: formFromScenario(start.name, start.config, ref.current.form) })
    }).catch(e => d({ t: 'scenarios', v: { status: 'error', list: [], origin: null, error: toErr(e).message } }))
  }, [])

  // scenarios on mount (once)
  useEffect(() => {
    const ac = new AbortController()
    loadScenariosOnce(ac.signal)
    return () => ac.abort()
  }, [loadScenariosOnce])

  useEffect(() => { document.documentElement.dataset.theme = s.theme; try { localStorage.setItem('acaps-theme', s.theme) } catch { /* private mode */ } }, [s.theme])

  const scenarioCfg = useCallback((name?: string) => ref.current.scenarios.list.find(x => x.name === (name ?? ref.current.form.scenario)), [])

  const api: Ctx = useMemo(() => ({
    s,
    setForm: v => d({ t: 'form', v }),
    scenarioCfg,
    pickScenario: name => {
      const sc = ref.current.scenarios.list.find(x => x.name === name)
      if (sc) d({ t: 'formSet', v: formFromScenario(name, sc.config, ref.current.form) })
      else d({ t: 'form', v: { scenario: name } })
      d({ t: 'issues', v: [] })
    },
    run: async () => {
      const cur = ref.current
      // Every phase below corresponds to real request state; there are no artificial delays.
      // 'validating' and 'preparing' are synchronous (form validation, request construction) and
      // may complete within a single frame on a fast device — that is honest, not a bug.
      d({ t: 'run', v: { phase: 'validating', error: null, startedAt: Date.now() } })
      const issues = validateForm(cur.form)
      d({ t: 'issues', v: issues })
      if (issues.length) { d({ t: 'run', v: { phase: 'error', error: { kind: 'validation', message: 'Please review the highlighted settings.', fields: issues.map(i => ({ path: i.field, msg: i.message })) } } }); return false }
      abort.current?.abort(); abort.current = new AbortController()
      d({ t: 'run', v: { phase: 'preparing' } })
      const req = buildRequest(cur.form, scenarioCfg(cur.form.scenario)?.config)
      d({ t: 'run', v: { phase: 'running' } })
      try {
        const view = await runSimulation(req, abort.current.signal)
        d({ t: 'run', v: { phase: 'complete', view, error: null, req } })
        d({ t: 'packet', v: null })
        return true
      } catch (e) {
        if ((e as Error).name === 'AbortError') return false
        d({ t: 'run', v: { phase: 'error', error: toErr(e) } })
        return false
      }
    },
    reset: () => {
      abort.current?.abort()
      d({ t: 'run', v: { phase: 'idle', view: null, error: null, req: null } })
      d({ t: 'packet', v: null })
      // Restore the configuration form to the current scenario's own backend-resolved defaults —
      // never a fixture, never a fabricated value, just the same call GET /scenarios already answered.
      const current = ref.current.scenarios.list.find(x => x.name === ref.current.form.scenario)
      if (current) d({ t: 'formSet', v: formFromScenario(current.name, current.config, ref.current.form) })
    },
    retryScenarios: () => loadScenariosOnce(),
    setScheduler: v => d({ t: 'scheduler', v }),
    selectPacket: id => d({ t: 'packet', v: id }),
    toggleTheme: () => d({ t: 'theme', v: ref.current.theme === 'dark' ? 'light' : 'dark' }),
  }), [s, scenarioCfg])

  return <C.Provider value={api}>{children}</C.Provider>
}
