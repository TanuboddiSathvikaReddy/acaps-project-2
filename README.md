# ACAPS — Adaptive Context-Aware Packet Scheduling

A Computer Networks course project: a discrete-event simulation of one congested router output
port, replaying one immutable, reproducible workload under three schedulers —

| Scheduler | Rule |
|---|---|
| **FIFO** | Serve packets in arrival order. The baseline. |
| **Static Priority** | Serve the most critical traffic class first; FIFO within a class. |
| **ACAPS** | Serve by deadline feasibility first (lexicographic tiers: SAFE / AT_RISK / INFEASIBLE), then criticality, with bounded aging. No weighted score. |

— and measuring what actually happened: deadline misses, packet loss, waiting time, throughput
and starvation, for each.

## Repository layout

```
backend/    Python/FastAPI simulation engine, scheduler implementations and metrics (source of truth)
frontend/   Vite/React/TypeScript app: configure a run, watch it, see the results
```

The backend is the single source of truth for every number the frontend shows. The frontend never
recomputes waiting time, deadlines, congestion, ACAPS decisions or metrics — it only requests,
re-indexes and displays what the backend returns.

## Backend

```
cd backend
pip install -e ".[dev]"
uvicorn acaps.api.app:app --reload   # http://localhost:8000
pytest                                # run the test suite
```

See `backend/docs/API.md` for the request/response contract, `backend/docs/ALGORITHMS.md` for the
scheduling and ACAPS decision logic, and `backend/docs/METRICS.md` for metric definitions and units.

## Frontend

```
cd frontend
npm install
npm run dev     # http://localhost:5173, proxies /api to the backend on :8000
npm run build   # typecheck + production build -> frontend/dist
```

Start the backend first. The frontend talks to the live API by default; it never silently falls
back to demo data. To run against pre-generated fixtures instead of a live backend (for frontend
development only), set `VITE_DEMO_MODE=true` — every screen then shows a persistent "Demo data"
badge. See `frontend/docs/FRONTEND.md` for the full layering and demo-data notes.

## Tests

```
cd backend && pytest             # backend regression suite
cd frontend && npx tsc --noEmit  # frontend typecheck
cd frontend && npm run build     # production build
```
