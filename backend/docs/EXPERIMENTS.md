# Experiments

**Scope of every statement in this document.** All results below describe the *tested configurations*: the
scenarios listed in section 3, the workload families they generate, 20 runs per scenario (seeds 42 to 61), and the
default parameters listed in section 2. None of them is a claim about ACAPS, Static Priority or FIFO in general.
Different budgets, class mixes, buffer sizes, aging parameters or traffic models can change the outcome
(`LIMITATIONS.md`).

## 1. Questions

1. **Comparison.** On identical workloads, how do FIFO, Static Priority and ACAPS differ in deadline misses, packet
   loss, delay, jitter and starvation across a set of load regimes?
2. **Control.** In the overloaded scenarios, are the scheduler-dependent **packet loss** differences caused by
   scheduling, or by packet-size differences combined with a packet-count buffer? (Section 8; section 8.3 states
   what the control can and cannot show.)

## 2. Methodology

1. **Scenarios are plain configurations** over one simulation engine (`src/acaps/config/presets.py`). They were
   defined by *load regime* (offered load rho) before any scheduler comparison and are not tuned afterwards.
   Two later additions are disclosed in section 8.4.
2. **Repeated runs.** Each scenario is run with **20 consecutive seeds, 42, 43, ..., 61**, each for **10 s** of
   generated traffic followed by a drain phase in which the queue empties.
3. **Fixed parameters** (identical in every run and scenario unless the scenario says otherwise):
   queue capacity 100 packets, class delay budgets 50 / 150 / 100 / 500 ms (emergency, video, GPS, normal),
   ranks 0 / 1 / 2 / 3, expired packets are transmitted late (`TRANSMIT_LATE`), congestion thresholds 0.30 / 0.70,
   ACAPS aging quantum 25% of the packet's own budget with at most 2 promotions, excessive-wait fraction 0.8,
   Poisson arrivals.
4. **For every seed** one workload is generated and replayed by all three schedulers (section 4).
5. **Every metric** is computed from the finished run (`METRICS.md`), then aggregated over seeds (section 6).

## 3. Scenarios used

Classes in all scenarios: `emergency` (rank 0, 50 ms), `video` (rank 1, 150 ms), `gps` (rank 2, 100 ms),
`normal` (rank 3, 500 ms). Packet sizes in the variable-size scenarios: emergency uniform 100-400 B, video uniform
800-1400 B, GPS uniform 60-140 B, normal 64 B (40%) or 1500 B (60%). rho = offered load =
`rate x mean packet bits / link bandwidth`.

| Scenario | Rate (pkt/s) | Link | Class mix (E / V / G / N) | Bursts | Sizes | rho | ~Packets / run |
|---|---:|---:|---|---|---|---:|---:|
| `normalTraffic` | 400 | 5 Mbps | 20 / 30 / 20 / 30 | none | class-correlated | 0.43 | 4,072 |
| `heavyTraffic` | 800 | 5 Mbps | 20 / 30 / 20 / 30 | none | class-correlated | 0.87 | 8,064 |
| `emergencyBurst` | 500 | 5 Mbps | 10 / 30 / 20 / 40 | 1 s at t = 4 s, 3x rate, mix 60 / 15 / 10 / 15 | class-correlated | 0.60 (burst 1.11) | 6,090 |
| `videoHeavy` | 600 | 5 Mbps | 5 / 60 / 10 / 25 | none | class-correlated | 0.88 | 6,090 |
| `networkOverload` | 800 | 4 Mbps | 20 / 30 / 20 / 30 | none | class-correlated | 1.08 | 8,064 |
| `mixedTraffic` | 600 | 5 Mbps | 20 / 30 / 20 / 30 | two 1 s bursts at t = 3 s and 7 s, 2x rate | class-correlated | 0.65 (bursts 1.30) | 7,283 |
| `sizeNeutralControl` | 800 | 5 Mbps | 20 / 30 / 20 / 30 | none | fixed 678 B, all classes | 0.87 | 8,064 |
| `emergencyBurstSizeNeutral` | 500 | 5 Mbps | as `emergencyBurst` | as `emergencyBurst` | fixed 464 B, all classes | 0.37 (burst 1.11) | 6,090 |
| `networkOverloadSizeNeutral` | 800 | 4 Mbps | as `networkOverload` | none | fixed 678 B, all classes | 1.08 | 8,064 |

`~Packets / run` is the count for seed 42; it varies by a percent or two across seeds (Poisson arrivals).

## 4. Same-workload replay methodology

The research question is only meaningful if the schedulers face **exactly the same packets**. The runner enforces it:

1. For a seed, `TrafficGenerator` generates the workload **once** (tested: the generator is called once per seed).
2. The workload is an immutable object (frozen packets, sorted by arrival time and id) with a **SHA-256 fingerprint**
   over every packet field.
3. FIFO, Static Priority and ACAPS each replay **that same object** in a **fresh engine** (no state carries over;
   tested by running the schedulers in reverse order and getting identical results).
4. Each run recomputes the fingerprint at its end; the runner asserts that all three equal the original. The API
   returns the fingerprint so it can be checked from outside.
5. Only the scheduling policy differs between the three runs. Network, buffer, drop policy, deadlines and event
   ordering are identical.

Randomness is used only for arrival gaps, class choice and packet size, from three independent seeded streams; it is
never used for waiting time, latency or congestion, which emerge from the queue.

## 5. Metrics used

Full definitions and denominators are in `METRICS.md`. The ones reported here:

| Metric | Definition | Denominator |
|---|---|---|
| Deadline miss rate | (delivered late + dropped by deadline expiry) / generated | generated packets |
| Packet loss rate | (queue-overflow drops + expiry drops) / generated | generated packets |
| Avg waiting time, p95 total delay, jitter | measured from timestamps of delivered packets | delivered packets |
| Starved packets | waited more than 80% of the own delay budget **and** overtaken at least once | count |
| Utilization | link busy time / observation window | fraction |

Loss and deadline miss are different things: an overflow drop is a loss but not a deadline miss, and a late delivery
is a miss but not a loss. Read both together. FIFO never overtakes a packet, so its starvation count is zero by
definition.

## 6. Aggregation and paired comparison versus FIFO

* **Per scheduler**: for each metric, the mean, the **sample** standard deviation (n - 1), min, max and n over the
  20 seeds. Tables show `mean ± std`. The std describes seed-to-seed variability of the per-run value; the
  standard error of the mean is roughly std / sqrt(20) = 0.22 x std.
* **Paired delta versus FIFO**: for each seed, `metric(scheduler) - metric(FIFO)` is computed on the *identical*
  workload, and then the mean and std of those 20 differences are reported. This is the appropriate comparison
  because it cancels the large seed-to-seed workload variation that both schedulers share. Comparing two
  independent averages would not.
* Negative deltas are improvements for "lower is better" metrics (loss, misses, delay, jitter, starvation).
* No significance test is built in. As an informal guide, a paired mean that is several times std / sqrt(20) is
  unlikely to be noise; a paired std of exactly 0.00 with a mean of 0.00 means the difference was identically zero
  in every run.

## 7. Event-ordering convention

Events at the same microsecond are processed as `DEADLINE_EXPIRY`, `DEPARTURE`, `ARRIVAL` (then by packet id), one at
a time, and a scheduling decision is taken after every single event. So a decision right after a departure does not
see an arrival of the same microsecond, and two simultaneous arrivals at an idle link are served in packet-id order.
This is identical for all schedulers and affects only exact microsecond coincidences (a handful per run; measured in
`ARCHITECTURE.md` section 7.1, which lists every consequence). It is a convention of the model, not a networking rule.

## 8. Size-neutral control experiments

### 8.1 Why they are needed

The presets give small packets to emergency and GPS and large packets to video and normal traffic. A scheduler that
favours the small-packet classes therefore also tends to finish work sooner (a shortest-job-first effect). The buffer
capacity is measured in **packets**, so serving small packets first frees buffer slots sooner and can reduce overflow
loss for a reason unrelated to deadline-awareness. The size-neutral control removes exactly that link.

### 8.2 Design

`emergencyBurstSizeNeutral` and `networkOverloadSizeNeutral` are the two overloaded scenarios with **only the packet
sizes changed**: every class uses one fixed size. Rate, link bandwidth, buffer, class mix, bursts, delay budgets,
ranks and seeds are identical, and so are the arrival times and the class of every packet (the size stream is
independent of the arrival and class streams; tested). They are generated from their source scenarios by the same
function that the API option `includeSizeNeutralControl` uses, so they cannot drift from them (tested).

**Which fixed size?** The mean packet size of the *peak-load period*, so the overload keeps the same offered load:

* `networkOverload` has one class mix throughout: 678 B (rho 1.084 -> 1.085).
* `emergencyBurst`'s burst uses a different mix (60% small emergency packets, mean 464 B). Using the base-mix mean
  (745 B) would have raised the burst load from 1.11 to 1.79, i.e. a different overload. The control therefore uses
  464 B: burst load 1.113 -> 1.114, at the cost of a lighter base period (rho 0.60 -> 0.37). The base period is well
  below overload in both versions, but the two versions do not have identical queue states before the burst.

### 8.3 An exact consequence, and how to read the control

With one fixed size, every packet has the same transmission time, so **any work-conserving, non-preemptive scheduler
produces the same departure instants**. The number of waiting packets over time is then identical for all three
schedulers, and the class-blind tail-drop discards exactly the same arrivals. So **in the size-neutral scenarios
(with the `TRANSMIT_LATE` policy used here) the overflow loss must be identical across schedulers, packet for
packet** (tested on both scenarios: the sets of dropped packet ids are equal). Under `DROP_EXPIRED` this
guarantee would not hold, because which packets expire depends on the order of service. Consequently:

* Because this identity holds for **any single fixed size**, the size-neutral loss result is a **consistency
  check, not an independent measurement of the schedulers**: it is guaranteed by construction and confirmed packet for
  packet by the tests. What it establishes is that, with equal packet sizes, the ordering logic of these schedulers
  cannot change the loss at all, so a loss difference between schedulers can only arise when packets differ in size.
* It does **not** separate *class-correlated* size differences from size variability in general. That would need a
  control in which every class shares the same *variable* size model; such a control was **not run** in Phase 1.
* Deadline misses, per-class delay and starvation still depend on the scheduler in the neutral versions, because
  scheduling still decides *who* waits.

### 8.4 Disclosure of changes made after the first comparison run

The seven original scenarios were run first. The two size-neutral scenarios were requested afterwards. While adding
them, the helper that chooses the neutral size was changed from "base-mix mean size" to "mean size of the peak-load
period" (section 8.2). The rule follows from offered-load arithmetic (a base-mix mean of 745 B would have changed the
burst load from 1.11 to 1.79), not from scheduler results. This repository does not record when the rule was chosen
relative to the first runs, so that ordering is **not asserted** here. The loss conclusion does not depend on the choice,
because the identity in section 8.3 holds for any single fixed size. The rule does not change `sizeNeutralControl`
(single mix). The aggregate numbers of the seven original scenarios are unchanged from their first run. No scheduler,
scenario parameter or metric definition was altered on the basis of any result.

### 8.5 Results of the size-neutral experiments

Same protocol as section 2 (20 seeds, 42 to 61, paired deltas versus FIFO).

#### emergencyBurst  vs  emergencyBurstSizeNeutral

* `emergencyBurst`: class-correlated sizes; offered load ρ 0.60 (burst 1.11)
* `emergencyBurstSizeNeutral`: fixed 464 B for every class; offered load ρ 0.37 (burst 1.11)

**Packet loss rate**

| Scenario | FIFO | Static Priority | ACAPS | Δ Static vs FIFO (paired) | Δ ACAPS vs FIFO (paired) |
|---|---:|---:|---:|---:|---:|
| emergencyBurst | 1.45% ± 0.83 | 0.31% ± 0.36 | 0.25% ± 0.32 | -1.15% ± 0.55 | -1.21% ± 0.61 |
| emergencyBurstSizeNeutral | 1.36% ± 0.60 | 1.36% ± 0.60 | 1.36% ± 0.60 | +0.00% ± 0.00 | +0.00% ± 0.00 |

**Deadline miss rate**

| Scenario | FIFO | Static Priority | ACAPS | Δ Static vs FIFO (paired) | Δ ACAPS vs FIFO (paired) |
|---|---:|---:|---:|---:|---:|
| emergencyBurst | 8.12% ± 2.78 | 0.01% ± 0.03 | 0.00% ± 0.00 | -8.12% ± 2.77 | -8.12% ± 2.78 |
| emergencyBurstSizeNeutral | 8.59% ± 1.67 | 0.10% ± 0.15 | 0.00% ± 0.00 | -8.50% ± 1.66 | -8.59% ± 1.67 |

**Packet loss rate by class**

| Class / version | FIFO | Static Priority | ACAPS |
|---|---:|---:|---:|
| emergency / original | 3.88% ± 2.14 | 0.77% ± 0.90 | 0.61% ± 0.76 |
| emergency / size-neutral | 3.45% ± 1.51 | 3.45% ± 1.51 | 3.45% ± 1.51 |
| gps / original | 0.80% ± 0.69 | 0.24% ± 0.32 | 0.18% ± 0.28 |
| gps / size-neutral | 0.91% ± 0.56 | 0.91% ± 0.56 | 0.91% ± 0.56 |
| normal / original | 0.64% ± 0.38 | 0.13% ± 0.17 | 0.12% ± 0.18 |
| normal / size-neutral | 0.62% ± 0.32 | 0.62% ± 0.32 | 0.62% ± 0.32 |
| video / original | 0.83% ± 0.57 | 0.18% ± 0.24 | 0.14% ± 0.21 |
| video / size-neutral | 0.79% ± 0.43 | 0.79% ± 0.43 | 0.79% ± 0.43 |

#### networkOverload  vs  networkOverloadSizeNeutral

* `networkOverload`: class-correlated sizes; offered load ρ 1.08
* `networkOverloadSizeNeutral`: fixed 678 B for every class; offered load ρ 1.08

**Packet loss rate**

| Scenario | FIFO | Static Priority | ACAPS | Δ Static vs FIFO (paired) | Δ ACAPS vs FIFO (paired) |
|---|---:|---:|---:|---:|---:|
| networkOverload | 6.20% ± 1.32 | 5.78% ± 1.31 | 5.71% ± 1.31 | -0.42% ± 0.24 | -0.49% ± 0.21 |
| networkOverloadSizeNeutral | 6.65% ± 0.95 | 6.65% ± 0.95 | 6.65% ± 0.95 | +0.00% ± 0.00 | +0.00% ± 0.00 |

**Deadline miss rate**

| Scenario | FIFO | Static Priority | ACAPS | Δ Static vs FIFO (paired) | Δ ACAPS vs FIFO (paired) |
|---|---:|---:|---:|---:|---:|
| networkOverload | 32.47% ± 2.68 | 0.45% ± 0.53 | 0.00% ± 0.00 | -32.02% ± 2.60 | -32.47% ± 2.68 |
| networkOverloadSizeNeutral | 33.47% ± 1.85 | 0.82% ± 0.51 | 0.00% ± 0.00 | -32.65% ± 1.82 | -33.47% ± 1.85 |

**Packet loss rate by class**

| Class / version | FIFO | Static Priority | ACAPS |
|---|---:|---:|---:|
| emergency / original | 6.13% ± 1.32 | 5.84% ± 1.33 | 5.67% ± 1.45 |
| emergency / size-neutral | 6.60% ± 1.17 | 6.60% ± 1.17 | 6.60% ± 1.17 |
| gps / original | 6.32% ± 1.47 | 5.87% ± 1.64 | 5.80% ± 1.35 |
| gps / size-neutral | 6.78% ± 1.20 | 6.78% ± 1.20 | 6.78% ± 1.20 |
| normal / original | 6.20% ± 1.30 | 5.76% ± 1.34 | 5.59% ± 1.27 |
| normal / size-neutral | 6.65% ± 0.90 | 6.65% ± 0.90 | 6.65% ± 0.90 |
| video / original | 6.17% ± 1.44 | 5.70% ± 1.31 | 5.78% ± 1.54 |
| video / size-neutral | 6.60% ± 1.11 | 6.60% ± 1.11 | 6.60% ± 1.11 |

### 8.6 Interpretation (tested configurations only)

* **Packet loss.** In both size-neutral scenarios the paired delta versus FIFO is `+0.00% ± 0.00`: loss was identical
  for FIFO, Static Priority and ACAPS in every one of the 20 runs, for every class (1.36% in
  `emergencyBurstSizeNeutral`, 6.65% in `networkOverloadSizeNeutral`). Section 8.3 shows this is an identity for any
  single fixed size, so it is a consistency check rather than a new finding. In the original scenarios the
  priority-type schedulers showed lower loss than FIFO (`emergencyBurst`: -1.15 ± 0.55 points for Static Priority and
  -1.21 ± 0.61 for ACAPS; `networkOverload`: -0.42 ± 0.24 and -0.49 ± 0.21). What the control shows is that these
  differences **depend on packets differing in size**: with one size they are exactly zero. Therefore, **in these two
  tested scenarios the loss differences cannot be attributed to the ordering logic alone and should not be presented
  as a loss advantage of any scheduler.** The control does not identify *which* aspect of the size differences is
  responsible (class-correlation, or size variability as such). `mixedTraffic` shows a similar loss pattern (5.30%
  for FIFO against 4.33% and 4.27%), but no control was run for it, so no conclusion is drawn for that scenario.
* **Deadline misses persist without size differences.** The size-neutral versions still show FIFO at 8.59% and
  33.47%, Static Priority at 0.10% and 0.82%, and ACAPS at 0.00% in all 20 runs. The differences in deadline misses
  in these two scenarios are therefore not explained by packet sizes.
* **Average waiting time.** With one packet size it is identical across schedulers (12.77 ms and 116.53 ms),
  consistent with work conservation. In the original scenarios it differs slightly (`networkOverload`: 109.61,
  109.01, 109.43 ms), which is again a size effect: only *who* waits changes with the schedule.
* **Comparing absolute values between versions is not meaningful** (for example FIFO loss 6.20% against 6.65% in
  `networkOverload`), because the control changes the packet sizes and therefore the amount of data offered. Compare
  scheduler differences within each version.


## 9. Results

Full tables (all metrics, all classes, all nine scenarios) are in `SAMPLE_RESULTS.md`, generated by
`scripts/run_sample.py`. Numbers below are copied from that file. Format: `mean ± std` over 20 seeds; the last two
columns are paired deltas versus FIFO.

### 9.1 Deadline misses and packet loss

**Deadline miss rate** (mean ± std over seeds; paired deltas versus FIFO)

| Scenario | FIFO | Static Priority | ACAPS | Δ Static vs FIFO (paired) | Δ ACAPS vs FIFO (paired) |
|---|---:|---:|---:|---:|---:|
| normalTraffic (ρ 0.43) | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.00% ± 0.00 | +0.00% ± 0.00 | +0.00% ± 0.00 |
| heavyTraffic (ρ 0.87) | 0.00% ± 0.01 | 0.00% ± 0.00 | 0.00% ± 0.00 | -0.00% ± 0.01 | -0.00% ± 0.01 |
| emergencyBurst (ρ 0.60 (burst 1.11)) | 8.12% ± 2.78 | 0.01% ± 0.03 | 0.00% ± 0.00 | -8.12% ± 2.77 | -8.12% ± 2.78 |
| videoHeavy (ρ 0.88) | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.00% ± 0.00 | -0.00% ± 0.00 | -0.00% ± 0.00 |
| networkOverload (ρ 1.08) | 32.47% ± 2.68 | 0.45% ± 0.53 | 0.00% ± 0.00 | -32.02% ± 2.60 | -32.47% ± 2.68 |
| mixedTraffic (ρ 0.65 (burst 1.30, 1.30)) | 7.84% ± 0.60 | 0.02% ± 0.05 | 0.00% ± 0.00 | -7.82% ± 0.59 | -7.84% ± 0.60 |
| sizeNeutralControl (ρ 0.87) | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.00% ± 0.00 | +0.00% ± 0.00 | +0.00% ± 0.00 |
| emergencyBurstSizeNeutral (ρ 0.37 (burst 1.11)) | 8.59% ± 1.67 | 0.10% ± 0.15 | 0.00% ± 0.00 | -8.50% ± 1.66 | -8.59% ± 1.67 |
| networkOverloadSizeNeutral (ρ 1.08) | 33.47% ± 1.85 | 0.82% ± 0.51 | 0.00% ± 0.00 | -32.65% ± 1.82 | -33.47% ± 1.85 |

**Packet loss rate** (mean ± std over seeds; paired deltas versus FIFO)

| Scenario | FIFO | Static Priority | ACAPS | Δ Static vs FIFO (paired) | Δ ACAPS vs FIFO (paired) |
|---|---:|---:|---:|---:|---:|
| normalTraffic (ρ 0.43) | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.00% ± 0.00 | +0.00% ± 0.00 | +0.00% ± 0.00 |
| heavyTraffic (ρ 0.87) | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.00% ± 0.00 | +0.00% ± 0.00 | +0.00% ± 0.00 |
| emergencyBurst (ρ 0.60 (burst 1.11)) | 1.45% ± 0.83 | 0.31% ± 0.36 | 0.25% ± 0.32 | -1.15% ± 0.55 | -1.21% ± 0.61 |
| videoHeavy (ρ 0.88) | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.00% ± 0.00 | +0.00% ± 0.00 | +0.00% ± 0.00 |
| networkOverload (ρ 1.08) | 6.20% ± 1.32 | 5.78% ± 1.31 | 5.71% ± 1.31 | -0.42% ± 0.24 | -0.49% ± 0.21 |
| mixedTraffic (ρ 0.65 (burst 1.30, 1.30)) | 5.30% ± 0.79 | 4.33% ± 0.81 | 4.27% ± 0.76 | -0.97% ± 0.24 | -1.03% ± 0.25 |
| sizeNeutralControl (ρ 0.87) | 0.00% ± 0.00 | 0.00% ± 0.00 | 0.00% ± 0.00 | +0.00% ± 0.00 | +0.00% ± 0.00 |
| emergencyBurstSizeNeutral (ρ 0.37 (burst 1.11)) | 1.36% ± 0.60 | 1.36% ± 0.60 | 1.36% ± 0.60 | +0.00% ± 0.00 | +0.00% ± 0.00 |
| networkOverloadSizeNeutral (ρ 1.08) | 6.65% ± 0.95 | 6.65% ± 0.95 | 6.65% ± 0.95 | +0.00% ± 0.00 | +0.00% ± 0.00 |


**Exact counts.** A rate printed as `0.00%` is rounded and can hide a few packets, so the same data as counts:

**Deadline misses per run (packets; min..max over seeds, mean in brackets)**

| Scenario | FIFO | Static Priority | ACAPS |
|---|---:|---:|---:|
| normalTraffic | 0..0 (0.0) | 0..0 (0.0) | 0..0 (0.0) |
| heavyTraffic | 0..3 (0.2) | 0..0 (0.0) | 0..0 (0.0) |
| emergencyBurst | 20..680 (488.8) | 0..6 (0.6) | 0..0 (0.0) |
| videoHeavy | 0..1 (0.1) | 0..0 (0.0) | 0..0 (0.0) |
| networkOverload | 2106..2977 (2597.8) | 0..125 (35.8) | 0..0 (0.0) |
| mixedTraffic | 449..625 (564.6) | 0..13 (1.3) | 0..0 (0.0) |
| sizeNeutralControl | 0..0 (0.0) | 0..0 (0.0) | 0..0 (0.0) |
| emergencyBurstSizeNeutral | 225..649 (516.7) | 0..22 (5.8) | 0..0 (0.0) |
| networkOverloadSizeNeutral | 2354..2887 (2676.6) | 2..131 (65.3) | 0..0 (0.0) |

**Packets dropped per run (overflow + expiry; min..max over seeds, mean in brackets)**

| Scenario | FIFO | Static Priority | ACAPS |
|---|---:|---:|---:|
| normalTraffic | 0..0 (0.0) | 0..0 (0.0) | 0..0 (0.0) |
| heavyTraffic | 0..0 (0.0) | 0..0 (0.0) | 0..0 (0.0) |
| emergencyBurst | 0..182 (87.7) | 0..77 (18.7) | 0..61 (14.9) |
| videoHeavy | 0..0 (0.0) | 0..0 (0.0) | 0..0 (0.0) |
| networkOverload | 258..755 (496.7) | 242..746 (463.1) | 219..721 (457.2) |
| mixedTraffic | 293..480 (381.6) | 212..432 (311.6) | 233..437 (307.7) |
| sizeNeutralControl | 0..0 (0.0) | 0..0 (0.0) | 0..0 (0.0) |
| emergencyBurstSizeNeutral | 0..144 (81.9) | 0..144 (81.9) | 0..144 (81.9) |
| networkOverloadSizeNeutral | 347..764 (532.8) | 347..764 (532.8) | 347..764 (532.8) |

### 9.2 Delay and starvation

Mean ± std over 20 seeds. Delay metrics use delivered packets only.

**Average waiting time (ms), all delivered packets**

| Scenario | FIFO | Static Priority | ACAPS |
|---|---:|---:|---:|
| normalTraffic | 0.71 ± 0.05 | 0.68 ± 0.04 | 0.68 ± 0.04 |
| heavyTraffic | 5.97 ± 1.18 | 4.99 ± 0.85 | 4.99 ± 0.85 |
| emergencyBurst | 13.30 ± 2.14 | 10.79 ± 3.02 | 10.79 ± 3.03 |
| videoHeavy | 6.74 ± 1.07 | 7.04 ± 1.11 | 6.97 ± 1.09 |
| networkOverload | 109.61 ± 7.63 | 109.01 ± 7.25 | 109.43 ± 7.30 |
| mixedTraffic | 29.24 ± 1.50 | 29.08 ± 1.71 | 29.06 ± 1.63 |
| sizeNeutralControl | 3.51 ± 0.42 | 3.51 ± 0.42 | 3.51 ± 0.42 |
| emergencyBurstSizeNeutral | 12.77 ± 1.30 | 12.77 ± 1.30 | 12.77 ± 1.30 |
| networkOverloadSizeNeutral | 116.53 ± 5.49 | 116.53 ± 5.49 | 116.53 ± 5.49 |

**p95 total delay (ms)**

| Scenario | FIFO | Static Priority | ACAPS |
|---|---:|---:|---:|
| normalTraffic | 4.63 ± 0.23 | 4.51 ± 0.18 | 4.51 ± 0.18 |
| heavyTraffic | 20.53 ± 4.52 | 26.18 ± 5.21 | 26.09 ± 5.16 |
| emergencyBurst | 69.07 ± 9.59 | 21.83 ± 6.69 | 26.83 ± 11.23 |
| videoHeavy | 22.55 ± 3.78 | 37.22 ± 7.23 | 35.78 ± 7.31 |
| networkOverload | 146.20 ± 3.02 | 441.77 ± 14.63 | 398.19 ± 5.18 |
| mixedTraffic | 112.09 ± 3.47 | 285.78 ± 14.60 | 286.32 ± 14.53 |
| sizeNeutralControl | 12.19 ± 1.53 | 18.85 ± 2.64 | 18.85 ± 2.64 |
| emergencyBurstSizeNeutral | 71.84 ± 4.01 | 16.34 ± 3.10 | 34.97 ± 4.49 |
| networkOverloadSizeNeutral | 136.44 ± 0.09 | 456.80 ± 10.57 | 404.30 ± 3.54 |

**Starved packets per run (count; FIFO is zero by definition)**

| Scenario | FIFO | Static Priority | ACAPS |
|---|---:|---:|---:|
| normalTraffic | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| heavyTraffic | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| emergencyBurst | 0.0 ± 0.0 | 21.8 ± 28.0 | 5.5 ± 12.7 |
| videoHeavy | 0.0 ± 0.0 | 0.3 ± 0.7 | 0.0 ± 0.0 |
| networkOverload | 0.0 ± 0.0 | 950.1 ± 199.3 | 298.6 ± 121.7 |
| mixedTraffic | 0.0 ± 0.0 | 5.9 ± 11.7 | 0.0 ± 0.0 |
| sizeNeutralControl | 0.0 ± 0.0 | 0.0 ± 0.0 | 0.0 ± 0.0 |
| emergencyBurstSizeNeutral | 0.0 ± 0.0 | 74.0 ± 28.9 | 30.0 ± 27.3 |
| networkOverloadSizeNeutral | 0.0 ± 0.0 | 1282.5 ± 164.2 | 476.9 ± 120.5 |


### 9.3 What these runs show, and what they do not

Everything below refers to the nine scenarios above, their workloads and 20 runs each.

1. **Sub-critical load (rho 0.43 to 0.88: `normalTraffic`, `heavyTraffic`, `videoHeavy`, `sizeNeutralControl`).** No packet
   was dropped in any run by any scheduler. ACAPS and Static Priority had **no deadline miss in any of the 20 runs** of
   these four scenarios; FIFO had a few rare ones (at most 3 packets per run in `heavyTraffic`, at most 1 in
   `videoHeavy`, none in the other two), which the percentage tables round to 0.00%. The two priority-type schedulers
   gave a higher p95 total delay than FIFO in three of the four (`heavyTraffic` 20.53 ms for FIFO against 26.18 and
   26.09; `videoHeavy` 22.55 against 37.22 and 35.78; `sizeNeutralControl` 12.19 against 18.85 for both) and were
   about equal in `normalTraffic` (4.63 against 4.51).
2. **Overload and bursts (`emergencyBurst`, `networkOverload`, `mixedTraffic` and the two size-neutral versions).**
   FIFO missed 7.84% to 33.47% of deadlines (up to 2,977 packets in one run). Static Priority missed 0.01% to 0.82% (up
   to 131 packets in one run). ACAPS had **exactly zero deadline misses in each of the 100 runs** (5 scenarios x 20
   seeds; see the counts table). That is an observation about these runs, not a claim that misses are impossible. The
   miss rate is measured over generated packets; overflow drops are losses, not misses (loss was 5.71% for ACAPS in
   `networkOverload`, and identical across schedulers in the neutral version).
3. **Starvation.** Static Priority produced starved packets in the stressed scenarios (for example 950.1 ± 199.3 per
   run in `networkOverload` and 1,282.5 ± 164.2 in `networkOverloadSizeNeutral`). ACAPS produced fewer starved packets
   than Static Priority in every scenario where Static Priority had any. It was **not zero** in `emergencyBurst` (5.5),
   `networkOverload` (298.6 ± 121.7) and the two size-neutral overload versions (30.0 and 476.9 ± 120.5); it was zero in
   every run of `mixedTraffic` and `videoHeavy`. FIFO has zero by definition.
4. **Tail delay is a real cost of the priority-type schedulers here.** In `networkOverload` the p95 total delay was
   146.20 ms for FIFO against 441.77 ms for Static Priority and 398.19 ms for ACAPS, because the low-priority classes
   wait behind the protected ones. In `emergencyBurst` and `emergencyBurstSizeNeutral` the p95 was lower than FIFO for
   both, but **Static Priority's p95 was lower than ACAPS's** (21.83 against 26.83 ms; 16.34 against 34.97 ms).
5. **Average waiting time is almost scheduler-independent** (for example 109.61, 109.01, 109.43 ms in
   `networkOverload`); schedulers mainly change which packets wait.
6. **Loss.** See sections 8.3 and 8.6: in the two original overloaded scenarios that have a control, the loss
   differences between schedulers disappear (identically, by construction) when every class has one packet size, so
   they are not evidence of a loss benefit of the ordering logic. The limits of that control are stated in 8.3.
7. **Not shown by these experiments.** Behaviour with other delay budgets, buffer sizes, class mixes, aging
   parameters, non-Poisson traffic, byte-capacity buffers or multiple hops; sensitivity to any of those parameters;
   any statistical significance beyond the mean, standard deviation and paired differences reported.


## 10. Limitations of these experiments

* **Tested configurations only.** Nine scenarios, one buffer size (100 packets), one set of delay budgets and ranks,
  one aging setting, Poisson arrivals with rate/mix bursts, one link, one hop.
* **20 runs per scenario.** Means and paired deltas carry sampling noise (std / sqrt(20)); no significance testing or
  confidence intervals are computed. Scenarios where a metric is exactly 0.00% in every run for a scheduler mean "no
  occurrence in these 20 runs", not "impossible".
* **Illustrative parameters.** Budgets, ranks, sizes and mixes are simulation parameters, not measured application
  requirements. Results can change with them; sensitivity to them was not studied.
* **Packet-count buffer.** Loss comparisons in the class-correlated scenarios are confounded with packet size (that
  is what section 8 examines). A byte-capacity buffer is not implemented.
* **The size-neutral control uses one fixed size**, which makes the loss identity of section 8.3 a mathematical
  guarantee. A control with one common *variable* size model (class-independent random sizes) was not run, so
  class-correlation and size variability are not separated.
* **The size-neutral control changes the workload in bits** (same packet count and arrival times, different sizes), so
  absolute values differ between an original scenario and its control; compare the *differences between schedulers*
  within each.
* **Metric trade-offs are real.** Deadline misses, tail delay, starvation and loss move in different directions for
  different schedulers in the tested scenarios; no single number ranks them.
* **No tuning.** Scenarios, aging parameters and schedulers were not adjusted on the basis of these results.

## 11. How to reproduce

Python 3.11 or newer. From the project root:

```bash
pip install -e ".[dev]"                                   # or: pip install pydantic fastapi uvicorn pytest httpx
pytest                                                    # 148 tests must pass first
python scripts/run_sample.py --runs 20 --out docs/SAMPLE_RESULTS.md
```

* Runtime: about 4 minutes on one core (3.7 minutes in the sandbox that produced the reported numbers; the two
  `networkOverload` scenarios take about 50 seconds each).
* Everything is deterministic on a given machine and Python build: the same command produces the same numbers
  (only `random.random()` from seeded generators is used, plus `log` for Poisson gaps). Bit-identical results across
  different platforms or Python builds were **not tested**; a difference in the C math library could in principle
  move an arrival by one microsecond.
* Options: `--runs N` (consecutive seeds starting at 42), `--scenarios name ...` (subset), `--json path` (also dump
  aggregated numbers), `--out path`.
* Single scenario over HTTP: `POST /api/v1/experiments` with `{"scenario": "networkOverloadSizeNeutral", "runs": 20}`
  (default base seed 42), or add `"options": {"includeSizeNeutralControl": true}` to any scenario to get its
  size-neutral control in the same response.
* Single seed, full detail: `POST /api/v1/simulate` (fingerprint, per-packet records, decisions, queue timeline).
