# Limitations (Phase 1)

What this simulation deliberately does **not** do, and what it therefore cannot claim.

## Deliberately out of scope

* **No machine learning**, no learned weights, no prediction.
* **No real packet capture** or real traffic traces. Traffic is synthetic (Poisson or constant arrivals with
  configured mixes and sizes).
* **No multi-hop / routing / propagation delay.** One link, one queue. End-to-end latency is not modelled.
* **No frontend.** Only a JSON API.
* **No per-flow modelling** (TCP congestion control, retransmission, feedback). Sources do not react to loss.

## Modelling limitations

1. **Packet-count queue.** Buffer capacity is a number of packets, not bytes. With variable packet sizes the
   buffer holds a variable amount of data, so loss can differ between schedulers partly because of packet sizes.
   The size-neutral control exposes this; a **byte-capacity queue is a planned extension**, not implemented.
2. **Single shared queue and single link**, work-conserving and non-preemptive; no per-class buffers or drop
   policies (only class-blind tail-drop).
3. **Only two arrival patterns** (Poisson, constant) plus rate/mix bursts. Real traffic is often bursty and
   self-similar.
4. **Delay budgets and ranks are illustrative parameters**, not measured application requirements.
5. **Deterministic service time** (`bits / bandwidth`); no MAC-layer effects, no link-rate changes.
6. **ACAPS needs the delay budget** of each packet (a per-class deadline) and the packet size. It assumes these
   are known at the router; real networks would have to convey them (e.g. via DSCP class mapping).
7. **ACAPS feasibility uses the current backlog only** (no forecast of future arrivals). A packet SAFE now can
   become AT_RISK if a burst arrives (proved in `ALGORITHMS.md` 3.7: only arrivals can cause this).
8. **Aging parameters** (`quantumFraction`, `maxPromotionLevels`) are configured, not learned; results depend
   on them.
9. **Statistical scope.** Results are means over a finite number of seeds; no confidence-interval or
   significance testing is built in (mean, sample std, min, max, n are reported, and paired differences).
10. **Presets were fixed before comparison and not tuned**, but they are still one particular family of load
    regimes. A different traffic mix or budget set can change the ranking of the schedulers.
11. **Size-neutral controls change the offered load outside the peak period.** The control uses the mean packet size of the
    peak-load period so that the overload keeps its offered load. In `emergencyBurst`, whose burst has a different
    class mix, this makes the calmer base period lighter (rho 0.60 -> 0.37). Controls were run for `heavyTraffic`,
    `emergencyBurst` and `networkOverload` only; `mixedTraffic` and `videoHeavy` have no control run
    (`EXPERIMENTS.md` section 8).

## How to read results honestly

* Compare at equal offered load and on the same workloads (the runner does).
* Use the **size-neutral control** before crediting a scheduler with a delay or loss advantage, and read
  `EXPERIMENTS.md` section 8.3 for what it can and cannot show.
* Describe every result as a property of **the tested configuration, workload and number of runs**, never as a
  property of a scheduler in general.
* Prefer **paired deltas vs FIFO** over comparing two independent averages.
* Report loss and deadline misses **together**: an overflow drop is not a deadline miss, so a scheduler can look
  good on misses while losing more packets.
* Remember that the average waiting time is nearly scheduler-independent for equal-size packets (work
  conservation); schedulers mainly change **who** waits.

## Future extensions (not implemented)

A size-neutral control with one common *variable* size model (to separate class-correlated sizes from size
variability); byte-capacity queue; multiple drop policies (e.g. drop-lowest-class); per-class queues; TCP-like sources;
additional arrival models (on/off, self-similar); multi-hop topologies; a frontend visualizer.
