# Scheduling algorithms

All three schedulers are pure functions `select(state) -> Decision`. They see the same `SchedulingState`
(see `ARCHITECTURE.md` section 8) and choose one packet from the waiting queue.

## Design principle (ACAPS)

> **Deadline feasibility takes priority over class criticality when a packet is genuinely at risk.
> Criticality is used within the appropriate urgency tier rather than being converted into an
> arbitrary numerical weight.**

**There is no weighted score in ACAPS.** Formulas of the form `Score = 0.35*criticality + 0.25*deadline + ...`
were explicitly rejected: the weights are arbitrary, unjustifiable in a viva, and let a large value of one factor
silently buy back a small value of another. ACAPS instead uses a **lexicographic hierarchy** over measured
quantities: compare the first key; only on a tie compare the second, and so on.

---

## 1. FIFO (baseline)

Select the waiting packet with the smallest `(arrivalTime, packetId)`.

No priority, no deadline awareness, no aging. Reason code: `FIFO_HEAD`.

## 2. Static Priority (baseline)

Select the waiting packet with the smallest `(criticalityRank, arrivalTime, packetId)`.

The rank is a fixed property of the traffic class (0 = most critical), configured per scenario. It never changes
with waiting time, deadline or queue state. Within one class the order is FIFO. Reason code:
`STATIC_PRIORITY_CLASS`.

Known behaviour, by design: a sustained stream of high-priority packets can **starve** lower classes.

## 3. ACAPS

### 3.1 The hierarchy at a glance

```
waiting time -> remaining deadline -> slack -> classify -> aging -> pick within the first non-empty tier

AT_RISK exists?   yes -> least slack first (tie: effective rank, arrival, id)
                  no  -> SAFE exists?  yes -> effective rank, then earliest deadline (tie: arrival, id)
                                       no  -> INFEASIBLE: triage, same key as SAFE
```

### 3.2 Step 1: measure (everything derived from the clock)

For every waiting packet `p` at decision time `t`:

| Quantity | Formula |
|---|---|
| waiting time | `t - arrival(p)` |
| remaining deadline | `deadline(p) - t`, where `deadline = arrival + delayBudget` |
| service time | `ceil(sizeBits(p) / linkBandwidthBps)` (transmission time on this link) |
| **slack** | `remaining - service`: how long `p` can still wait and finish on time |

### 3.3 Step 2: classify (deadline feasibility and urgency)

```
INFEASIBLE   slack < 0                              cannot meet its deadline even if sent right now
liveWork   = sum of service times of all packets that are NOT infeasible
AT_RISK      slack < liveWork - service(p)          would miss its deadline if sent LAST
SAFE         otherwise                              would still make it even if sent last
```

Two different ideas, kept separate:

* **Feasibility** (`INFEASIBLE`) is a property of the packet alone: not enough time is left.
* **Urgency** (`AT_RISK` vs `SAFE`) depends on the backlog: `liveWork - service(p)` is the work every other live
  packet could put in front of `p`. A deeper queue makes more packets `AT_RISK`. This is how congestion (backlog)
  enters ACAPS, without a "congestion score".

`liveWork` **excludes infeasible packets** because they will be served last, so they cannot delay packets that
can still be saved. (Counting them would wrongly mark saveable packets AT_RISK; there is a test for this.)

Why this test? If `p` is sent last among the live packets it starts after `liveWork - service(p)` and misses its
deadline exactly when `slack < liveWork - service(p)`. Packets that fail this are the only ones that need to jump
the queue.

### 3.4 Step 3: aging (bounded, relative to the packet's own budget)

```
quantum          = round(quantumFraction x delayBudget(p))            default fraction 0.25
promotions       = min(maxPromotionLevels, floor(waiting / quantum))  default cap 2
effectiveRank    = max(0, criticalityRank - promotions)
```

* Aging is computed from the actual waiting time on every decision. There is no stored counter.
* It is relative to the packet's **own** budget, so a 50 ms class ages faster in absolute time than a 500 ms class.
* It is **bounded**: with the defaults a `normal` packet (rank 3) can rise to at most rank 1, so it can **never**
  reach emergency level (rank 0) by waiting alone.
* Aging only affects the *criticality* keys inside a tier. It can **never** move a packet across tiers, so it
  cannot override a deadline decision. Its purpose is to *limit* starvation of low classes within the SAFE tier. It does not eliminate it: in the tested
  scenarios ACAPS still produced starved packets (`EXPERIMENTS.md` section 9.3).
* `maxPromotionLevels = 0` switches aging off (useful for ablation).

### 3.5 Step 4: select

The first non-empty tier wins:

| Tier | Selection key (smallest wins) | Reason code |
|---|---|---|
| AT_RISK | `(slack, effectiveRank, arrival, packetId)` | `AT_RISK_LEAST_SLACK` |
| SAFE | `(effectiveRank, deadline, arrival, packetId)` | `SAFE_BY_CRITICALITY`, or `SAFE_AGING_CHANGED_CHOICE` if raw ranks would have chosen someone else |
| INFEASIBLE | `(effectiveRank, deadline, arrival, packetId)` | `INFEASIBLE_TRIAGE` |

A single waiting packet gets `ONLY_CANDIDATE`. Every key ends in `(arrival, packetId)`, so the order is total:
exactly one winner, deterministic, independent of the order packets are listed.

Infeasible packets are still delivered (under `TRANSMIT_LATE`) but only after everything saveable, and the more
critical / earlier-deadline ones first (triage).

### 3.6 Why each rule is there (viva answers)

| Question | Answer |
|---|---|
| Why not just priority? | It ignores deadlines and can starve low classes. |
| Why not just earliest deadline first? | It ignores class criticality among packets that are not in danger. |
| Why is at-risk above criticality? | A packet that will miss its deadline unless served now loses all value; a safe packet can wait without harm. The most critical packet is not helped by being served earlier if it would have been on time anyway. |
| Why least slack among at-risk? | It is the most urgent one: the smallest margin for error (least-laxity-first). |
| Why tier-then-criticality rather than a score? | Weights are arbitrary. A hierarchy states priorities explicitly and is explainable in one sentence. |
| Why can't aging cause chaos? | It is bounded, deterministic, and cannot cross tiers. |
| Complexity? | O(n) per decision, n <= queue capacity K. |

### 3.7 Property: serving one packet never makes a SAFE packet AT_RISK

Without new arrivals, if `p` is SAFE (`slack(p) >= liveWork - service(p)`) and another packet `q` is served
next (taking `service(q)`), then `slack'(p) = slack(p) - service(q)` and the new `liveWork'` is at most
`liveWork - service(q)`. So `slack'(p) >= liveWork' - service(p)` and `p` stays SAFE. Only new arrivals can
change it. This is checked by a randomized test (150 cases).

---

## 4. Worked example (this is executed by the test suite)

Link 1 Mbps, so `service(us) = bytes x 8`. Five packets are waiting at `t = 300 ms`:

| Packet | Class (rank) | Size | Service | Arrival | Deadline | Waiting | Remaining | Slack |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| P1 | normal (3) | 1500 B | 12 ms | 0 | 500 | 300 | 200 | 188 |
| P2 | gps (2) | 250 B | 2 ms | 290 | 390 | 10 | 90 | 88 |
| P3 | video (1) | 1250 B | 10 ms | 173 | 323 | 127 | 23 | **13** |
| P4 | emergency (0) | 125 B | 1 ms | 285 | 335 | 15 | 35 | 34 |
| P5 | video (1) | 1000 B | 8 ms | 140 | 290 | 160 | -10 | -18 |

**Decision 1 (t = 300).** P5 has negative slack: INFEASIBLE. `liveWork = 12+2+10+1 = 25 ms` (P5 excluded).
P3: `13 < 25-10 = 15` -> **AT_RISK**. The others are SAFE (e.g. P4: `34 >= 24`). An AT_RISK packet exists, so P3 is
chosen even though the emergency packet P4 has a better class. `AT_RISK_LEAST_SLACK`. P3 finishes at 310.

**Decision 2 (t = 310).** P1, P2, P4 all SAFE (P4 slack 24 >= 14). Effective ranks: P4 = 0, P1 = 3 - 2 = 1 (waited
310 ms = 2 quanta of 125 ms), P2 = 2. P4 wins: `SAFE_BY_CRITICALITY`. Finishes at 311.

**Decision 3 (t = 311).** P1 (effective rank 1) beats P2 (rank 2, only 21 ms waited). Without aging P2 would win
(raw ranks 3 vs 2), so `SAFE_AGING_CHANGED_CHOICE`. Finishes at 323.

**Decision 4 (t = 323).** P2, then P5 (infeasible, served last). Finishes at 325, then 333.

| Packet | FIFO done | Static Priority done | ACAPS done | Deadline |
|---|---:|---:|---:|---:|
| P1 | 312 | 333 | 323 | 500 |
| P2 | 333 | 321 | 325 | 390 |
| P3 | **330** (late) | 319 | 310 | 323 |
| P4 | 331 | 301 | 311 | 335 |
| P5 | 320 (late) | 309 (late) | 333 (late) | 290 |

P5 was already lost at t = 300 for every scheduler (`remaining < 0`). Of the packets that could still be
saved, **FIFO misses P3**; Static Priority and ACAPS miss none. So in this particular instance ACAPS and Static
Priority tie on deadline misses, and the difference is in *how the delay is distributed*:

* ACAPS sends the video packet P3 **before** the emergency packet P4, because P3 was about to become
  unsaveable while P4 could safely wait 10 ms (P4 still finishes at 311, deadline 335).
* ACAPS sends P1 (waited 300 ms) **before** P2 (waited 20 ms) thanks to aging; Static Priority makes P1 wait for
  everything (finishes at 333).

One constructed situation in which Static Priority misses a deadline that ACAPS meets (a low class starved by a
continuous high-priority stream) is in `tests/test_schedulers.py`. How often such differences occur is an empirical
question; measured results for the tested scenarios are in `EXPERIMENTS.md`, and they are not a general property.

All schedulers finish the last packet at 333 ms: the link is work-conserving, only the order differs.

---

## 5. Tie-breaking summary

| Situation | Resolution |
|---|---|
| Equal arrival time (FIFO) | lower `packetId` |
| Equal class (Static Priority) | earlier arrival, then lower `packetId` |
| Equal slack (AT_RISK) | lower effective rank, then earlier arrival, then lower `packetId` |
| Equal effective rank (SAFE / INFEASIBLE) | earlier deadline, then earlier arrival, then lower `packetId` |
| Simultaneous events | `DEADLINE_EXPIRY`, `DEPARTURE`, `ARRIVAL`, then `packetId` |

## 6. Original context factors: where they went

| Original factor | In ACAPS |
|---|---|
| Criticality | traffic class -> `criticalityRank` -> `effectiveRank` (a lexicographic key, never a weight) |
| Deadline | delay budget -> `remainingDeadline` -> `slack` -> tier |
| Age | measured waiting time -> aging promotions |
| Latency | waiting + transmission; reported as a metric, not an input |
| Congestion | queue backlog (`liveWork`) turning packets AT_RISK; occupancy level is reported in the log |
