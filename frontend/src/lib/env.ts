/**
 * Demo mode is an explicit, build-time opt-in for development (VITE_DEMO_MODE=true).
 * Default is false. Real mode (the default) never falls back to fixtures on its own —
 * see api/source.ts. This flag is the ONLY thing that switches data source, and it never
 * changes at runtime based on request success or failure.
 */
export const DEMO_MODE = (import.meta.env.VITE_DEMO_MODE ?? '') === 'true'
