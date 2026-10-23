# Metrics

Computed by `metrics/engine.py` from a finished run (after the drain phase). Every rate states its denominator.

## Notation

| Symbol | Meaning |
|---|---|
| `G` | generated packets (all arrivals) |
| `A` | accepted: entered the queue = `D + L_e` |
| `D` | delivered (transmission completed) |
| `O` | delivered **on time**: `txEnd <= deadline` |
| `L_o` | dropped by **queue overflow** |
| `L_e` | dropped by **deadline expiry** (only under `DROP_EXPIRED`) |
| `W` | observation window `[0, max(duration, last departure)]` |

Invariants **checked on every run** (a violation raises `MetricsInvariantError`, it is never silently reported):
`G = D + L_o + L_e`, `A = D + L_e`, and every per-class count sums to the overall count. Empty denominators
give `null` (never 0 and never NaN).

## Loss vs deadline miss

| Outcome | Counted as loss? | Counted as deadline miss? |
|---|---|---|
| Delivered on time | no | no |
| Delivered late (`txEnd > deadline`) | no | **yes** |
| Dropped: queue overflow | **yes** | no |
| Dropped: deadline expired (`DROP_EXPIRED`) | **yes** | **yes** |

## Metric list

| Key | Formula | Denominator / unit |
|---|---|---|
| `generated`, `accepted`, `delivered`, `deliveredOnTime`, `deliveredLate`, `droppedOverflow`, `droppedExpired`, `dropped` | counts | packets |
| `packetLossRate` | `(L_o + L_e) / G` | per generated packet |
| `deadlineMisses` | `(D - O) + L_e` | packets |
| `deadlineMissRate` | `deadlineMisses / G` | per generated packet |
| `deadlineMissRateAccepted` | `deadlineMisses / A` | per accepted packet |
| `onTimeRate` | `O / G` | per generated packet |
| `avgWaitingTimeMs` | mean of `txStart - arrival` over delivered | ms |
| `avgServiceTimeMs` | mean of `txEnd - txStart` over delivered | ms |
| `avgTotalDelayMs` | mean of `txEnd - arrival` over delivered (= waiting + service) | ms |
| `maxWaitingTimeMs` | max waiting over delivered | ms |
| `p95TotalDelayMs` | 95th percentile of total delay, nearest-rank, over delivered | ms |
| `throughputPps` | `D / W` | packets/s |
| `throughputBps` | `deliveredBits / W` | bit/s |
| `deliveredBits` | sum of delivered packet sizes x 8 | bits |
| `utilization` (overall only) | `busyTime / W` | fraction |
| `meanPacketSizeBytes` | mean size of generated packets | bytes |
| `jitterMs` | see below | ms |
| `excessiveWaitCount` / `Rate` | see below | packets |
| `starvationCount` / `Rate` | see below | packets |
| `observationWindowMs` (overall only) | `W` | ms |

Per-class blocks have the same keys, computed on that class's packets (with the same `W`).

Metrics for overflow-dropped packets: they never waited, so they are excluded from delay averages.
Expired-then-dropped packets are also excluded from delay averages (they were never delivered) but are included in
loss/miss counts and in excessive-wait counts (they waited until their deadline).

## Jitter

Delay variation between **consecutive delivered packets of the same class**, in departure order (IPDV-style):

```
d_i = total delay of the i-th delivered packet of a class
jitter = mean over consecutive pairs of | d_i - d_(i-1) |
```

The overall figure **pools the per-class pairs**. Pairing packets of different classes would mainly measure the
(expected, large) difference between classes instead of delay variation inside a flow.

## Excessive wait and starvation

Measured over **accepted** packets (`A`):

* **Excessive wait**: `waitingTime > excessiveWaitFraction x own delayBudget` (default 0.8).
  For a dropped-expired packet, waiting runs from arrival to the drop instant.
* **Starvation**: excessive wait **and** overtaken at least once, i.e. at some decision a packet that arrived
  *later* was chosen ahead of it (`overtakenCount >= 1`).

A packet that waits long only because the queue is long (nobody jumped ahead) is *congestion*, not starvation.
FIFO never overtakes anyone, so its starvation count is **zero by definition**. Compare FIFO on excessive wait
and loss instead. Rates use `A` as denominator (`excessiveWaitRateAccepted`, `starvationRateAccepted`).

## Queue behaviour (`queue` block)

Time-weighted over `[0, W]`; each timeline point holds until the next.

| Key | Meaning |
|---|---|
| `meanQueueLength` | `integral(queueLength dt) / W` (waiting packets only) |
| `meanOccupancy` | `meanQueueLength / K` |
| `maxQueueLength`, `maxOccupancy` | peak settled length and `/ K` |
| `congestionTimeShare` | fraction of `W` spent in LOW / MEDIUM / HIGH (sums to 1) |

The queue timeline (`queueTimeline`) is sampled whenever the queue length or link state changes and also carries
the measured arrival/departure rates in packets/s and bit/s.

## Comparison block

For the common comparison (`comparison` in the API) each metric is shown per scheduler with the difference
versus **FIFO** (`scheduler - FIFO`) and a `metricDirections` map saying whether lower or higher is better.

## Aggregation over repeated runs

`aggregate` reports, per metric leaf: `mean`, `std` (**sample** standard deviation, `n-1`; `null` for one run),
`min`, `max`, and `n` (number of non-null values). `pairedDeltasVsFifo` reports the same statistics of the
**per-seed** difference `scheduler - FIFO`. Paired differences are the right comparison: for a given seed all
schedulers replayed exactly the same workload.
