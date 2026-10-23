# Architecture

## 1. What is being simulated

One router output port: a finite buffer feeding one link. Packets arrive, wait if the link is busy, and a
**scheduler** decides which waiting packet uses the link next.

```
 traffic          BoundedQueue                       link
 generator ─────▶ (K waiting packets) ──▶ scheduler ──▶ (one packet at a time)
  (seeded)        tail-drop when full     picks one     transmission time = bits / bandwidth
```

In queueing terms this is a finite-buffer G/G/1/K system. It is deliberately the smallest network that shows
scheduling effects: congestion, waiting, deadlines and loss all emerge on this one link.

## 2. Separation of concerns

| Layer | Module | Responsibility | Knows about |
|---|---|---|---|
| Configuration | `config/` | Validate user conditions, resolve presets | nothing else |
| Core model | `core/` | Packet, queue, network, state, events, time units | configuration values |
| Traffic | `traffic/` | Turn conditions into an immutable workload | config, packets |
| Schedulers | `schedulers/` | Pure decision rules `select(state) -> Decision` | state only |
| Engine | `engine/simulation.py` | Run the clock, apply decisions, record timestamps | all of the above |
| Metrics | `metrics/engine.py` | Compute numbers from a finished run | run records |
| Experiments | `experiments/` | Replay one workload under all schedulers, aggregate | engine, metrics |
| API | `api/` | JSON in / JSON out | experiments |

A scheduler cannot see the future, the configuration, other schedulers, or previous decisions. That makes
the three schedulers interchangeable and the comparison fair.

## 3. Initial packet information vs. dynamic state

The brief requires strict separation, and the code enforces it with two different types.

**`Packet`** (frozen dataclass; known at creation; lives in the shared workload):
`packetId`, `trafficClass`, `arrivalTimeUs`, `sizeBytes`, `source`, `destination`, `criticalityRank`,
`delayBudgetUs`. (`deadlineUs = arrivalTimeUs + delayBudgetUs` is derived.)

**`PacketRecord`** (mutable; one per packet **per scheduler run**; filled in only by the engine):
`status`, `enqueueTimeUs`, `txStartUs`, `txEndUs`, `dropTimeUs`, `dropReason`, `deadlineMissed`,
`overtakenCount`. Derived properties: `waitingTimeUs = txStart - arrival`, `serviceTimeUs = txEnd - txStart`,
`totalDelayUs = txEnd - arrival`.

Because packets are immutable and records are per run, replaying a workload cannot leak state between
schedulers.

## 4. Packet lifecycle

```
CREATED ─▶ ARRIVED ─┬─▶ DROPPED (QUEUE_OVERFLOW)                       buffer full: tail-drop
                    └─▶ QUEUED ─▶ [scheduler picks] ─▶ TRANSMITTING ─▶ DELIVERED (ON_TIME | LATE)
                            └─▶ DROPPED (DEADLINE_EXPIRED)   only under policy DROP_EXPIRED
```

| Log event | Emitted when |
|---|---|
| `PACKET_CREATED`, `PACKET_ARRIVED` | arrival event |
| `PACKET_QUEUED` | buffer had room |
| `PACKET_DROPPED` | overflow, or expiry under `DROP_EXPIRED` |
| `SCHEDULER_DECISION` | scheduler chose a packet (reason code + details) |
| `PACKET_TRANSMISSION_STARTED` / `_COMPLETED` | link starts / finishes the packet |
| `DEADLINE_MISSED` | a waiting packet reaches its deadline, or an in-service packet is certain to finish late |

The event log is optional (`options.includeEventLog`); the decision log and queue timeline are separate,
always-available structures.

## 5. Network model

* **Link bandwidth** `linkBandwidthMbps` is an **independent input**. It never changes when packet sizes change.
* **Transmission time** = `ceil(packetSizeBits / linkBandwidthBps)` microseconds (minimum 1 us), integer arithmetic.
  Handy rule: `bits / Mbps = microseconds`. 1500 B on 10 Mbps = 12000 / 10 = 1200 us.
* **Incoming rate** is in packets/s (all classes combined). The *bit rate* it offers is derived:
  `offered load rho = incomingRate x meanPacketSizeBits / linkBandwidthBps`.
* `describe_network()` reports rho, the FIFO delay bound and per-class transmission-time ranges, as
  informational values (never fed to a scheduler).

## 6. Queue model

* Capacity `K` (`queueCapacity`) is measured in **packets** and counts **waiting** packets only; the packet on
  the link is not in the buffer.
* **Tail-drop**: an arrival that finds the buffer full is dropped. The drop policy belongs to the *network*, not
  the scheduler, so it is identical for all schedulers. Overflow is packet **loss**.
* `queueOccupancy = queueLength / K`; congestion level LOW / MEDIUM / HIGH comes from occupancy thresholds
  (`congestionThresholds`, defaults 0.30 and 0.70, simulation parameters).
* A packet-count buffer means loss can differ between schedulers when packet sizes vary (a scheduler that sends
  small packets first frees slots sooner). This is a known property of the model; a byte-capacity buffer is a
  documented future extension (`docs/LIMITATIONS.md`).

## 7. Discrete-event engine

The clock is an integer number of **microseconds** and jumps from event to event.

| Event | What happens |
|---|---|
| `ARRIVAL` | Record arrival. If the buffer is full: tail-drop. Else enqueue and schedule a `DEADLINE_EXPIRY` at the packet's deadline. |
| `DEPARTURE` | Packet finishes: set `txEnd`, decide on-time vs late (`txEnd <= deadline` is on time), free the link. |
| `DEADLINE_EXPIRY` | Waiting packet: mark missed (and drop it under `DROP_EXPIRED`). In service: mark missed if it will finish late. Already delivered: nothing. |

**Dispatch rule.** After *every* event, if the link is idle and packets wait, the engine builds a
`SchedulingState`, asks the scheduler, removes the chosen packet and starts transmitting. The server is
**work-conserving** (never idles while packets wait) and **non-preemptive** (a transmission is never aborted).

### 7.1 Event-ordering convention (frozen for Phase 1)

Two rules define what a scheduler sees. They are identical for FIFO, Static Priority and ACAPS.

1. **Order of events that occur at the same microsecond**: `DEADLINE_EXPIRY`, then `DEPARTURE`, then `ARRIVAL`;
   remaining ties are broken by packet id. Events are processed **one at a time**.
2. **A scheduling decision is taken after every single event** (not once per timestamp): if the link is idle and the
   queue is non-empty, the scheduler is asked immediately. A decision therefore sees exactly the events that have
   already been processed, and no later event of the same microsecond.

Consequences (all deliberate, all scheduler-independent):

| Situation at one instant `t` | What happens |
|---|---|
| Departure and an arrival, packets are waiting | Departure frees the link; the decision is taken **among the packets already waiting** (the arrival has not been processed yet); then the arrival is processed and finds the buffer slot that the decision just freed. |
| Departure and an arrival, queue empty | The link is idle when the arrival is processed, so the arrival starts transmission immediately (waiting time 0). This is why arrivals spaced exactly one service time apart never queue. |
| Two packets arrive at the same microsecond, link idle | Processed in packet-id order: the lower id is the only candidate at its decision and is transmitted; the other waits. The scheduler does not choose between them. |
| A waiting packet's deadline equals `t`, and a departure occurs at `t` | The expiry is processed first. Under `DROP_EXPIRED` the packet is removed before the departure-triggered decision, so an expired packet is never scheduled. Under `TRANSMIT_LATE` it is marked missed. |
| An in-service packet's transmission ends exactly at its deadline `t` | The expiry event is processed first and sees `txEnd == deadline` (not greater), so it records no miss; the departure then confirms the packet as on time. |

Rationale: this mirrors a work-conserving transmitter that starts the next packet as soon as it can, and it makes the
buffer accounting natural (a departure-triggered dispatch frees a slot before the next arrival is admitted).

How often does it matter? Only at exact microsecond coincidences. In one sample workload (`heavyTraffic`, seed 42,
8064 packets) 3 arrival instants are shared by two packets and 6 arrivals coincide with a FIFO departure instant, so
the convention affects a handful of decisions per run. It is documented rather than tuned; it is covered by
`tests/test_engine.py` (`test_simultaneous_arrivals...`, `test_arrival_equal_to_service...`).

**End of run.** Arrivals exist only in `[0, duration)`. The engine keeps running until every accepted packet is
delivered or dropped (the *drain phase*), so every packet has a final outcome and the accounting identity
`generated = delivered + droppedOverflow + droppedExpired` holds exactly. The observation window for
throughput/utilization is `[0, max(duration, lastDeparture)]`.

## 8. What the scheduler is allowed to see: `SchedulingState`

Everything is measured from the clock and queue at the decision instant:

* `now`, the waiting packets (in arrival order), queue capacity/length/occupancy, congestion level;
* per packet: waiting time (`now - arrival`), remaining deadline (`deadline - now`), transmission time on this
  link, slack (`remaining - transmission`), deadline status;
* observed arrival/departure rates over a sliding window (`observedRateWindowMs`, default 500 ms).

Nothing in the state is configured as a "congestion level" or "latency": those are computed.

## 9. Randomness and reproducibility

Randomness is used for three things only: arrival gaps (Poisson), class choice (from the mix), packet size
(from the class size model). It is **never** used for waiting time, latency, congestion, or urgency.

* Three independent, seeded streams (`arrivals`, `classes`, `sizes`), derived from `sha256(seed:name)`.
  Changing a size model does not move arrival times or the class sequence.
* Exactly one draw per packet from the class stream and from the size stream, whatever the class.
* Class order is canonicalized (alphabetical) so JSON key order cannot change a workload.
* The workload carries a SHA-256 **fingerprint** over every packet field. Each run recomputes it at the end;
  the runner asserts all three schedulers report the same fingerprint.
* The same seed and configuration always produce bit-identical results (tested).

## 10. Extension points

* New scheduler: implement `Scheduler.select(state) -> Decision`, register it in `make_scheduler`.
* New size model: add a class with `sample(u)` / `mean_bytes` / `min_possible` / `max_possible` to the union in
  `config/models.py`.
* New metric: add it to `MetricsEngine._summarize`; aggregation and comparison pick it up automatically.
* New scenario: add a `Preset` (it is only configuration; there is one simulation engine).
