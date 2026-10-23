# ACAPS frontend

Vite + React 19 + TypeScript. No chart or animation libraries.

## Run
    npm install
    npm run dev          # http://localhost:5173, proxies /api to VITE_BACKEND_URL (default http://localhost:8000)
    npm run build        # tsc + vite build -> dist/
Start the backend first (uvicorn on :8000). To point at another host, set VITE_API_BASE or VITE_BACKEND_URL.

## Layering
api (client, source) -> adapters (re-index only) -> state (store) -> components -> visuals (canvas/SVG).
No packet generation, waiting time, deadline, congestion, ACAPS or metric logic lives here.

## Demo data
public/mock/*.json are fixtures used ONLY when the build is explicitly started with `VITE_DEMO_MODE=true` (see src/lib/env.ts and src/api/source.ts) — never as a silent fallback when the live backend is unreachable or returns an error. In real mode (the default), any backend failure is shown to the user as a genuine connection error with a retry option; it is never masked by demo data. Every demo-mode screen shows a persistent "Demo data" badge and demo requests ignore your parameters. Fixtures are produced by tools/make_demo_fixtures.py, an approximation for UI development, not the backend and not real results. A production build (`npm run build`) strips public/mock entirely unless VITE_DEMO_MODE=true (see tools/strip-demo-fixtures.mjs).

## API gaps
- openapi `comparison` block shape is not fully specified; comparisons are derived from per-scheduler `metrics`.
- Per-packet tier for queued packets is only available with includeDecisionCandidates.
- The landing-page scene is a labelled illustration, not a simulation.
