# API contract (schema version 1.0)

Base path `/api/v1`. JSON in, JSON out, camelCase. Interactive docs at `/docs` when the server runs
(`uvicorn acaps.api.app:app`). CORS is open (a separate frontend will call it) and responses are gzip-compressed.

The data model is UI-neutral: plain records, timelines and decision logs. Packet-level times are integer
**microseconds** (`...Us`); aggregate metrics are **milliseconds** (`...Ms`).

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/scenarios` | List presets with their fully resolved configuration |
| POST | `/simulate` | One seed; FIFO, Static Priority and ACAPS replay **one shared workload** |
| POST | `/experiments` | `runs` consecutive seeds, aggregated (mean / std / min / max / n) with paired deltas |

## Request

Every field is optional. Resolution order: base configuration -> `scenario` preset -> fields in the request.

```json
{
  "scenario": "networkOverload",
  "incomingRate": 800,
  "linkBandwidthMbps": 4,
  "queueCapacity": 100,
  "packetSize": 1200,
  "simulationDuration": 10,
  "randomSeed": 42,
  "trafficMix": {"emergency": 0.2, "video": 0.3, "gps": 0.2, "normal": 0.3},
  "classes": {
    "video": {"criticalityRank": 1, "delayBudgetMs": 150,
              "sizeModel": {"type": "uniform", "minBytes": 800, "maxBytes": 1400}}
  },
  "arrivalModel": "poisson",
  "bursts": [{"startTime": 4, "duration": 1, "rateMultiplier": 3,
              "trafficMixOverride": {"emergency": 0.6, "video": 0.15, "gps": 0.1, "normal": 0.15}}],
  "expiredPacketPolicy": "TRANSMIT_LATE",
  "congestionThresholds": {"medium": 0.3, "high": 0.7},
  "aging": {"quantumFraction": 0.25, "maxPromotionLevels": 2},
  "starvation": {"excessiveWaitFraction": 0.8},
  "observedRateWindowMs": 500,
  "sizeNeutralModel": null,
  "options": {"includeEventLog": false, "includeDecisions": true, "includeDecisionCandidates": false,
              "includeQueueTimeline": true, "includeSizeNeutralControl": false, "maxTimelinePoints": 2000},
  "runs": 30
}
```

Notes:

* `linkBandwidthMbps` is the link capacity. **`serviceRate` was removed** and is rejected with a 422 that names
  the replacement. Transmission time is derived from packet size and bandwidth.
* `packetSize` is only the *default* size (a fixed size for classes without a `sizeModel`). The presets give each
  class its own `sizeModel`, which takes precedence; the resolved sizes are echoed in `config.classes`.
* `sizeModel` is one of `{"type":"fixed","bytes":n}`, `{"type":"uniform","minBytes":a,"maxBytes":b}`,
  `{"type":"discrete","values":[{"bytes":n,"probability":p}, ...]}` (probabilities sum to 1).
* `classes` merge per class and per field; `sizeModel` and `trafficMix` are replaced wholesale.
* `runs` (1-200, default 30) is only accepted by `/experiments`.
* Unknown fields, invalid mixes, non-positive capacities etc. return **422** with a JSON error list.
* `options.includeSizeNeutralControl` adds the size-neutral control (see `EXPERIMENTS.md`).

Scenarios: `custom`, `normalTraffic`, `heavyTraffic`, `emergencyBurst`, `videoHeavy`, `networkOverload`,
`mixedTraffic`, `sizeNeutralControl`, `emergencyBurstSizeNeutral`, `networkOverloadSizeNeutral`.

## `POST /simulate` response

```
{
  "schemaVersion": "1.0",
  "config": { ...resolved configuration..., "derived": {
      "linkBandwidthBps", "meanPacketSizeBytes", "offeredLoad", "equivalentPacketRatePps",
      "fifoWaitBoundUs", "burstOfferedLoad": [...], "byClass": {...}, "warnings": [...] } },
  "workload": { "fingerprint", "packetCount", "packets": [ {packetId, trafficClass, arrivalTimeUs, sizeBytes,
                 source, destination, criticalityRank, delayBudgetUs, deadlineUs} ] },
  "schedulers": {
    "FIFO" | "STATIC_PRIORITY" | "ACAPS": {
      "metrics": { "overall": {...}, "perClass": {"emergency": {...}, ...}, "queue": {...} },
      "packets": [ {packetId, outcome, dropReason, enqueueTimeUs, txStartUs, txEndUs, dropTimeUs,
                    waitingTimeUs, serviceTimeUs, totalDelayUs, deadlineMissed, overtakenCount} ],
      "queueTimeline": [ {timeUs, queueLength, occupancy, congestionLevel, serverBusy,
                          observedArrivalRatePps, observedArrivalRateBps,
                          observedDepartureRatePps, observedDepartureRateBps} ],
      "decisions": [ {timeUs, chosenPacketId, chosenClass, queueLength, occupancy, congestionLevel,
                      reasonCode, details, candidates?} ],
      "events": [ {timeUs, type, packetId, data} ]        // only if includeEventLog
    }
  },
  "comparison": { "baseline": "FIFO", "metricDirections", "metrics", "deltasVsFifo", "perClass" },
  "sizeNeutralControl": { "config", "workloadFingerprint", "packetCount", "schedulers": {...metrics...}, "comparison" }
}
```

* `outcome`: `ON_TIME`, `LATE`, `DROPPED`. `dropReason`: `QUEUE_OVERFLOW`, `DEADLINE_EXPIRED`.
* `reasonCode`: `ONLY_CANDIDATE`, `FIFO_HEAD`, `STATIC_PRIORITY_CLASS`, `AT_RISK_LEAST_SLACK`,
  `SAFE_BY_CRITICALITY`, `SAFE_AGING_CHANGED_CHOICE`, `INFEASIBLE_TRIAGE`.
* ACAPS `details`: `tier`, `agingChangedChoice`, `waitingTimeUs`, `remainingDeadlineUs`, `slackUs`,
  `criticalityRank`, `effectiveRank`, `liveWorkUs`, `atRiskCount`, `safeCount`, `infeasibleCount`.
* `candidates` (opt-in): every waiting packet at that decision, with waiting time, deadline, remaining deadline,
  criticality, estimated service time; ACAPS adds `tier`, `slackUs`, `promotions`, `effectiveRank`.
* `workload.fingerprint` is identical for the three schedulers by construction and is re-verified at the end of
  each run.
* `queueTimeline` is evenly downsampled to `options.maxTimelinePoints` (first and last points kept).
  Statistics are always computed from the full timeline.
* `sizeNeutralControl` exposes only aggregate metrics (no packet lists) to keep the response small.

**Response size.** A 10 s heavy scenario (~8000 packets) is ~13 MB of JSON uncompressed and ~1 MB gzipped.
Switch off `includeDecisions` / `includeQueueTimeline` or shorten `simulationDuration` if you do not need them.

## `POST /experiments` response

```
{
  "schemaVersion": "1.0", "config": {...}, "baseSeed": 42, "runCount": 30,
  "runs": [ {"seed", "workloadFingerprint", "packetCount", "schedulers": {"FIFO": metrics, ...}} ],
  "aggregate": { "FIFO": {overall/perClass/queue with {mean,std,min,max,n} leaves}, "STATIC_PRIORITY": ..., "ACAPS": ... },
  "pairedDeltasVsFifo": { "STATIC_PRIORITY": {...}, "ACAPS": {...} },
  "sizeNeutralControl": { "scenario", "derived", "runs", "aggregate", "pairedDeltasVsFifo" }   // if requested
}
```

Runtime grows with `runs x duration x rate`; a 10 s overload scenario takes ~2.5 s per seed.

## `GET /scenarios`

`[{"name", "label", "description", "config": <resolved config incl. derived>}]`
