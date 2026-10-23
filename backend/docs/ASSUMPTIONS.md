# Assumptions

The brief requires a clear line between **real networking facts** and **simulation assumptions**. Every
assumption below is a **simulation parameter or modelling choice** that can be changed in the configuration or
the code. None is presented as a universal networking rule.

## 1. Real-world facts the model relies on

These are ordinary, well-established networking facts:

| Fact | Where used |
|---|---|
| Transmission (serialization) delay on a link is `bits / bandwidth`. | Service time of every packet |
| Queueing delay is the time a packet waits behind other packets; it depends on load, not on a configured number. | Waiting time is measured, never assigned |
| A finite buffer overflows when arrivals exceed departures for long enough; the excess is dropped. | Tail-drop, loss metric |
| A non-preemptive link finishes the packet it has started. | Engine |
| Poisson arrivals are a standard analytical model of aggregated independent traffic. | Traffic generator (option) |
| Offered load `rho = lambda x E[size] x 8 / C`; queues are unstable for `rho >= 1`. | `derived.offeredLoad` |
| Jitter as variation of delay between consecutive packets (IPDV, RFC 3393). | Jitter metric |

## 2. Simulation parameters (chosen for the experiment, not standards)

| Parameter | Default | Meaning / why it is only an assumption |
|---|---|---|
| `incomingRate` | scenario | Offered packets/s. |
| `linkBandwidthMbps` | 5 (4 for overload) | Link capacity. Independent of packet size. |
| `queueCapacity` | 100 packets | Buffer size in **packets**. Real routers use bytes or milliseconds of buffering. |
| Class delay budgets | 50 / 150 / 100 / 500 ms | Emergency / video / GPS / normal. Illustrative application requirements. |
| Criticality ranks | 0 / 1 / 2 / 3 | Emergency > video > GPS > normal. A design choice, not a standard. |
| Packet-size models | see presets | Uniform / discrete ranges per class; class-correlated sizes (emergency and GPS small, video large). |
| Traffic mix | 20 / 30 / 20 / 30 % | Share of packets per class. |
| `congestionThresholds` | 0.30 / 0.70 | Occupancy limits for LOW / MEDIUM / HIGH. |
| `aging.quantumFraction`, `maxPromotionLevels` | 0.25, 2 | One promotion per 25% of the packet's own budget waited; at most 2 levels. |
| `starvation.excessiveWaitFraction` | 0.8 | Waiting more than 80% of the budget counts as "excessive". |
| `observedRateWindowMs` | 500 | Window for measured arrival/departure rates. |
| `expiredPacketPolicy` | `TRANSMIT_LATE` | See below. |
| Burst parameters | scenario | Rate multipliers and class mixes in `emergencyBurst` / `mixedTraffic`. |

## 3. Modelling choices

1. **One link, one hop, one queue.** No routing, no propagation delay, no multi-hop effects. Latency in the
   results is *queueing + transmission* on this link.
2. **Single shared queue for all classes.** Schedulers pick from one buffer (no per-class queues).
3. **Deterministic service.** A packet's transmission time is exactly `ceil(bits / bandwidth)`. No random service.
4. **Non-preemptive, work-conserving link.** A transmission is never aborted; the link never idles when packets wait.
5. **Tail-drop, class-blind.** The drop decision is made by the network, identically for every scheduler.
6. **Packet-count buffer.** Capacity counts packets. Because packets have different sizes, the amount of data the
   buffer holds varies, and a scheduler that serves small packets first can free slots sooner; **loss can
   therefore differ between schedulers for a reason unrelated to "better scheduling"**. The size-neutral control
   scenario (section 5) is provided to separate this. A byte-capacity queue is future work.
7. **Time resolution 1 us.** Ties at the same microsecond are broken deterministically (`ARCHITECTURE.md` section 7).
8. **Expired packets.** Default `TRANSMIT_LATE`: an expired packet stays queued and is delivered late (counted as
   a deadline miss, not a loss). `DROP_EXPIRED` drops it at its deadline (counted as loss **and** miss).
9. **Deadline met** means `transmissionEnd <= arrival + delayBudget`. Delivery to the receiver is assumed to
   happen at transmission end (no propagation delay).
10. **Deadline miss and packet loss are distinct.** Overflow drops are loss but *not* deadline misses; late
    deliveries are misses but *not* loss; expiry drops are both. Rates state their denominator (`METRICS.md`).
11. **Traffic generation stops at the configured duration.** The simulation then drains the queue; every packet
    receives a final outcome.
12. **Bursts do not overlap** (validated). A burst may replace the traffic mix for its window.

## 4. What is measured vs what is configured

| Quantity | Status |
|---|---|
| waiting time, latency, remaining deadline, slack | **derived** from the clock |
| queue occupancy, congestion level | **derived** from the queue |
| observed arrival/departure rates | **measured** over a sliding window |
| deadline misses, losses, starvation | **counted** from events |
| latency / waiting / congestion "levels" | **never** entered by the user or drawn randomly |

## 5. The size-neutral control

Sizes differ by class in the presets (small emergency/GPS packets, large video/normal packets). Any
work-conserving scheduler that favours small-packet classes looks good on waiting time simply because
short jobs finish first (a shortest-job-first effect), even if it is not smarter about deadlines. To separate the
two effects, every scenario can be rerun as a **size-neutral control**: identical arrival times, classes, ranks,
deadlines, bandwidth, queue and bursts, but every class uses the *same* size model. Default: a fixed size equal to
the mean packet size of the **peak-load period** (for a scenario with one class mix everywhere this is simply the
mix-weighted mean size). Reason: packet loss happens when load is highest, so the control keeps the overload
window's offered load unchanged; in `emergencyBurst`, whose burst has a different class mix, this leaves the
burst load unchanged (rho 1.11) and makes the calmer base period lighter (0.60 -> 0.37). Ready-made size-neutral
scenarios exist for `heavyTraffic` (`sizeNeutralControl`), `emergencyBurst` (`emergencyBurstSizeNeutral`) and
`networkOverload` (`networkOverloadSizeNeutral`).

How to read it: a difference that survives in the control does not depend on packet-size differences; a difference
that disappears does depend on them. Note that with one fixed size, equal **loss** across work-conserving schedulers
is a mathematical identity (same service times give the same queue length over time, so the class-blind tail-drop
drops the same packets), so for loss the control is a consistency check, and it cannot tell class-correlated sizes
from size variability in general. See `EXPERIMENTS.md` section 8.3.

## 6. Reproducibility assumptions

* Randomness comes only from seeded `random.Random` streams (`random()` output for a given seed is stable across
  Python versions).
* Identical configuration + seed => identical workload (checked by a SHA-256 fingerprint) and identical results.
* Repeated experiments use consecutive seeds `baseSeed, baseSeed+1, ...`.
