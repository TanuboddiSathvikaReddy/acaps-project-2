# ACAPS: Adaptive Context-Aware Packet Scheduling

Phase 1 of a Computer Networks project: a **backend-only discrete-event simulation** that compares three
packet schedulers on one congested link, fairly and reproducibly.

| Scheduler | Rule |
|---|---|
| **FIFO** | Serve packets in arrival order. The baseline. |
| **Static Priority** | Serve the most critical *class* first; FIFO within a class. Never changes. |
| **ACAPS** | Serve by *deadline feasibility first*, then criticality, with bounded aging. No weights. |

There is **no** machine learning, real packet capture, multi-hop network, or frontend in Phase 1.
A separate frontend can later call the JSON API.

## Design principle

> **Deadline feasibility takes priority over class criticality when a packet is genuinely at risk.
> Criticality is used within the appropriate urgency tier rather than being converted into an
> arbitrary numerical weight.**

ACAPS contains **no** weighted score such as `0.35*criticality + 0.25*deadline + ...`. The decision is a
lexicographic hierarchy over quantities the simulator *measures* (see `docs/ALGORITHMS.md`).

## How the original context factors are represented

The original idea combined five "context factors". In this implementation none of them is a number typed in by
the user or drawn at random, and none is multiplied by a weight:

| Original context factor | Representation in the simulation |
|---|---|
| **Criticality** | The packet's **traffic class** and its fixed **criticality rank** (0 = most critical). Used *inside* an urgency tier as a lexicographic key, and improved (never beyond a bounded limit) by aging. |
| **Deadline** | The class's **application delay budget** and the packet's **remaining deadline** = `arrival + budget - now`. Combined with the packet's transmission time into **slack**, which decides the tier (AT_RISK / SAFE / INFEASIBLE). |
| **Age** | The packet's **actual queue waiting time** = `now - arrival`, measured from the clock. Drives aging: one class promotion per `quantumFraction x own delay budget` waited, capped by `maxPromotionLevels`. |
| **Latency** | **Derived**, never assigned: `waiting time + transmission (service) time`, with transmission time = `packetSizeBits / linkBandwidthBps`. Reported per packet, per class and overall. |
| **Congestion** | **Derived** from the **actual queue occupancy / backlog** (`queueLength / queueCapacity` -> LOW / MEDIUM / HIGH) and from **observed traffic** (sliding-window measured arrival and departure rates). Congestion affects ACAPS only through the backlog, which is what turns packets AT_RISK. |

## What the user configures vs. what the simulator derives

The user describes **network conditions**: incoming rate (packets/s), **link bandwidth (Mbps)**, queue capacity
(packets), packet sizes (per class: fixed / uniform / discrete), traffic mix, delay budgets, duration, seed.
The simulator **derives the state**: waiting time, transmission time, latency, queue occupancy, congestion,
deadline misses, losses. Bandwidth is independent of packet size; only transmission time depends on size.

## Quick start

```bash
pip install -e ".[dev]"            # or: pip install pydantic fastapi uvicorn pytest httpx
pytest                             # 148 tests
uvicorn acaps.api.app:app --reload # API on http://127.0.0.1:8000  (docs at /docs)
python scripts/run_sample.py --runs 20   # regenerate docs/SAMPLE_RESULTS.md
```

Use from Python:

```python
from acaps.config.presets import resolve_config
from acaps.experiments.runner import run_simulation

result = run_simulation(resolve_config({"scenario": "networkOverload"}))
for name, run in result.runs.items():
    print(name.value, run.metrics["overall"]["deadlineMissRate"])
```

Call the API:

```bash
curl -X POST localhost:8000/api/v1/simulate -H 'content-type: application/json' \
     -d '{"scenario": "networkOverload", "linkBandwidthMbps": 4, "randomSeed": 7}'
```

## Repository layout

```
src/acaps/
  config/       models.py (validated configuration), presets.py (scenarios + request merging)
  core/         timeunits, packet (initial info vs dynamic record), events, queue, network, state
  traffic/      generator.py (seeded workload), workload.py (immutable + fingerprint)
  schedulers/   base, fifo, static_priority, acaps
  engine/       simulation.py (discrete-event loop)
  metrics/      engine.py (formulas + invariants)
  experiments/  runner.py (replay + comparison + repeated runs), aggregate.py
  api/          app.py, schemas.py, serializers.py (thin FastAPI wrapper)
tests/          148 tests, including an M/D/1 queueing-theory validation and the event-ordering lock
scripts/        run_sample.py
docs/           see below
```

## Documentation

| File | Contents |
|---|---|
| `docs/ARCHITECTURE.md` | Components, packet lifecycle, network/queue model, event ordering |
| `docs/ALGORITHMS.md` | FIFO, Static Priority, ACAPS, aging, tie-breaking, worked example |
| `docs/ASSUMPTIONS.md` | Every assumption, marked as **simulation parameter** vs **real-world fact** |
| `docs/METRICS.md` | Every metric, its formula and denominator |
| `docs/EXPERIMENTS.md` | Methodology, scenarios, same-workload replay, paired comparison, size-neutral controls, results (tested configurations only), how to reproduce |
| `docs/SAMPLE_RESULTS.md` | Generated results of the 9 scenarios over 20 seeds (incl. size-neutral pairs) |
| `docs/API.md` | JSON contract |
| `docs/LIMITATIONS.md` | What Phase 1 deliberately does not do |
