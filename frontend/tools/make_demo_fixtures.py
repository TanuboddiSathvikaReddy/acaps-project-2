#!/usr/bin/env python3
"""
DEMO FIXTURE GENERATOR (development only, NOT part of the shipped frontend runtime).

Produces API-shaped JSON (schema 1.0, see docs/API.md) so the UI can be developed while the real backend is
unreachable. It is a throwaway approximation of the documented model (docs/ARCHITECTURE.md, ALGORITHMS.md,
METRICS.md). It is NOT the source of truth: the frontend never ships this logic, only its JSON output, and every
screen that shows this data is labelled "Demo data".

Usage: python3 tools/make_demo_fixtures.py  -> public/mock/*.json
"""
import heapq, json, math, os, random, hashlib, sys

OUT = os.path.join(os.path.dirname(__file__), "..", "public", "mock")
os.makedirs(OUT, exist_ok=True)

CLASSES = ["emergency", "video", "gps", "normal"]
RANK = {"emergency": 0, "video": 1, "gps": 2, "normal": 3}
BUDGET_MS = {"emergency": 50, "video": 150, "gps": 100, "normal": 500}
SIZE = {
    "emergency": {"type": "uniform", "minBytes": 100, "maxBytes": 400},
    "video": {"type": "uniform", "minBytes": 800, "maxBytes": 1400},
    "gps": {"type": "uniform", "minBytes": 60, "maxBytes": 140},
    "normal": {"type": "discrete", "values": [{"bytes": 64, "probability": 0.4}, {"bytes": 1500, "probability": 0.6}]},
}
MIX = {"emergency": .2, "video": .3, "gps": .2, "normal": .3}

# name: label, description, overrides, demo duration (s)
PRESETS = {
    "normalTraffic": ("Normal Traffic", "Light load. The link is idle much of the time and queues stay short.",
                      dict(incomingRate=400, linkBandwidthMbps=5), 3),
    "heavyTraffic": ("Heavy Traffic", "High but sub-critical load. Queues form and drain without sustained overflow.",
                     dict(incomingRate=800, linkBandwidthMbps=5), 3),
    "emergencyBurst": ("Emergency Burst", "Moderate base load with a one-second, 3x burst dominated by emergency packets.",
                       dict(incomingRate=500, linkBandwidthMbps=5, trafficMix={"emergency": .1, "video": .3, "gps": .2, "normal": .4},
                            bursts=[{"startTime": 4, "duration": 1, "rateMultiplier": 3,
                                     "trafficMixOverride": {"emergency": .6, "video": .15, "gps": .1, "normal": .15}}]), 6),
    "videoHeavy": ("Video Heavy", "Video dominates the mix, so large packets keep the link busy.",
                   dict(incomingRate=600, linkBandwidthMbps=5, trafficMix={"emergency": .05, "video": .6, "gps": .1, "normal": .25}), 3),
    "networkOverload": ("Network Overload", "Offered load exceeds link capacity. The buffer fills and tail-drop begins.",
                        dict(incomingRate=800, linkBandwidthMbps=4), 3),
    "mixedTraffic": ("Mixed Traffic", "Steady traffic interrupted by two one-second bursts at 2x rate.",
                     dict(incomingRate=600, linkBandwidthMbps=5,
                          bursts=[{"startTime": 3, "duration": 1, "rateMultiplier": 2}, {"startTime": 7, "duration": 1, "rateMultiplier": 2}]), 8),
}


def base_config(name, ov, duration, seed=42):
    cfg = dict(scenario=name, incomingRate=800, linkBandwidthMbps=5, queueCapacity=100, packetSize=1200,
               simulationDuration=duration, randomSeed=seed, trafficMix=dict(MIX),
               classes={c: {"criticalityRank": RANK[c], "delayBudgetMs": BUDGET_MS[c], "sizeModel": SIZE[c]} for c in CLASSES},
               arrivalModel="poisson", bursts=[], expiredPacketPolicy="TRANSMIT_LATE",
               congestionThresholds={"medium": .3, "high": .7}, aging={"quantumFraction": .25, "maxPromotionLevels": 2},
               starvation={"excessiveWaitFraction": .8}, observedRateWindowMs=500)
    cfg.update(ov)
    return cfg


def mean_size(model):
    if model["type"] == "fixed": return model["bytes"]
    if model["type"] == "uniform": return (model["minBytes"] + model["maxBytes"]) / 2
    return sum(v["bytes"] * v["probability"] for v in model["values"])


def draw_size(rng, m):
    if m["type"] == "fixed": return m["bytes"]
    if m["type"] == "uniform": return rng.randint(m["minBytes"], m["maxBytes"])
    r, a = rng.random(), 0
    for v in m["values"]:
        a += v["probability"]
        if r <= a: return v["bytes"]
    return m["values"][-1]["bytes"]


def pick_class(rng, mix):
    r, a = rng.random(), 0
    for c in CLASSES:
        a += mix[c]
        if r <= a: return c
    return CLASSES[-1]


def gen_workload(cfg):
    ra, rc, rs = (random.Random(cfg["randomSeed"] * 10 + i) for i in range(3))
    dur = cfg["simulationDuration"]
    t, pid, pk = 0.0, 1, []
    while True:
        rate, mix = cfg["incomingRate"], cfg["trafficMix"]
        for b in cfg["bursts"]:
            if b["startTime"] <= t < b["startTime"] + b["duration"]:
                rate *= b["rateMultiplier"]
                mix = b.get("trafficMixOverride", mix)
        t += ra.expovariate(rate)
        if t >= dur: break
        c = pick_class(rc, mix)
        us = int(t * 1e6)
        bud = int(cfg["classes"][c]["delayBudgetMs"] * 1000)
        pk.append(dict(packetId=pid, trafficClass=c, arrivalTimeUs=us, sizeBytes=draw_size(rs, cfg["classes"][c]["sizeModel"]),
                       source=f"src-{c}", destination="sink", criticalityRank=RANK[c], delayBudgetUs=bud, deadlineUs=us + bud))
        pid += 1
    return pk


def tx_us(size, bw_mbps): return max(1, math.ceil(size * 8 / bw_mbps))


def congestion(occ, th): return "HIGH" if occ >= th["high"] else "MEDIUM" if occ >= th["medium"] else "LOW"


# ---------------- schedulers ----------------
def sel_fifo(now, q, P, cfg, bw):
    c = min(q, key=lambda p: (p["arrivalTimeUs"], p["packetId"]))
    return c, "FIFO_HEAD" if len(q) > 1 else "ONLY_CANDIDATE", {}


def sel_static(now, q, P, cfg, bw):
    c = min(q, key=lambda p: (p["criticalityRank"], p["arrivalTimeUs"], p["packetId"]))
    return c, "STATIC_PRIORITY_CLASS" if len(q) > 1 else "ONLY_CANDIDATE", {}


def sel_acaps(now, q, P, cfg, bw):
    ag = cfg["aging"]
    rows = []
    for p in q:
        svc = tx_us(p["sizeBytes"], bw)
        rem = p["deadlineUs"] - now
        rows.append(dict(p=p, svc=svc, rem=rem, slack=rem - svc, wait=now - p["arrivalTimeUs"]))
    live = [r for r in rows if r["slack"] >= 0]
    live_work = sum(r["svc"] for r in live)
    for r in rows:
        if r["slack"] < 0: r["tier"] = "INFEASIBLE"
        elif r["slack"] < live_work - r["svc"]: r["tier"] = "AT_RISK"
        else: r["tier"] = "SAFE"
        quantum = round(ag["quantumFraction"] * r["p"]["delayBudgetUs"])
        promo = min(ag["maxPromotionLevels"], r["wait"] // quantum) if quantum else 0
        r["eff"] = max(0, r["p"]["criticalityRank"] - promo)
    at = [r for r in rows if r["tier"] == "AT_RISK"]
    sf = [r for r in rows if r["tier"] == "SAFE"]
    inf = [r for r in rows if r["tier"] == "INFEASIBLE"]
    aging_changed = False
    if at:
        w = min(at, key=lambda r: (r["slack"], r["eff"], r["p"]["arrivalTimeUs"], r["p"]["packetId"])); reason = "AT_RISK_LEAST_SLACK"
    else:
        pool = sf or inf
        key = lambda r: (r["eff"], r["p"]["deadlineUs"], r["p"]["arrivalTimeUs"], r["p"]["packetId"])
        w = min(pool, key=key)
        raw = min(pool, key=lambda r: (r["p"]["criticalityRank"], r["p"]["deadlineUs"], r["p"]["arrivalTimeUs"], r["p"]["packetId"]))
        aging_changed = raw is not w
        reason = "INFEASIBLE_TRIAGE" if not sf else ("SAFE_AGING_CHANGED_CHOICE" if aging_changed else "SAFE_BY_CRITICALITY")
    if len(q) == 1: reason = "ONLY_CANDIDATE"
    d = dict(tier=w["tier"], agingChangedChoice=aging_changed, waitingTimeUs=w["wait"], remainingDeadlineUs=w["rem"], slackUs=w["slack"],
             criticalityRank=w["p"]["criticalityRank"], effectiveRank=w["eff"], liveWorkUs=live_work,
             atRiskCount=len(at), safeCount=len(sf), infeasibleCount=len(inf))
    return w["p"], reason, d


SCHED = {"FIFO": sel_fifo, "STATIC_PRIORITY": sel_static, "ACAPS": sel_acaps}


def run(cfg, workload, name, events=True):
    bw = cfg["linkBandwidthMbps"]
    K = cfg["queueCapacity"]
    th = cfg["congestionThresholds"]
    P = {p["packetId"]: p for p in workload}
    rec = {pid: dict(packetId=pid, outcome=None, dropReason=None, enqueueTimeUs=None, txStartUs=None, txEndUs=None, dropTimeUs=None,
                     waitingTimeUs=None, serviceTimeUs=None, totalDelayUs=None, deadlineMissed=False, overtakenCount=0) for pid in P}
    ev, decisions, timeline, log = [], [], [], []
    for p in workload: heapq.heappush(ev, (p["arrivalTimeUs"], 2, p["packetId"], "A"))
    q, busy, cur = [], False, None
    arr_times, dep_times, dep_bits, arr_bits = [], [], [], []
    win = int(cfg["observedRateWindowMs"] * 1000)

    def emit(t, typ, pid, data=None):
        if events: log.append(dict(timeUs=t, type=typ, packetId=pid, data=data or {}))

    def snap(t):
        occ = len(q) / K
        a = [(x, b) for x, b in arr_times if t - win < x <= t]
        d = [(x, b) for x, b in dep_times if t - win < x <= t]
        w = win / 1e6
        timeline.append(dict(timeUs=t, queueLength=len(q), occupancy=round(occ, 4), congestionLevel=congestion(occ, th), serverBusy=busy,
                             observedArrivalRatePps=round(len(a) / w, 2), observedArrivalRateBps=round(sum(b for _, b in a) / w, 1),
                             observedDepartureRatePps=round(len(d) / w, 2), observedDepartureRateBps=round(sum(b for _, b in d) / w, 1)))

    def dispatch(t):
        nonlocal busy, cur
        if busy or not q: return
        chosen, reason, details = SCHED[name](t, q, P, cfg, bw)
        for o in q:
            if (o["arrivalTimeUs"], o["packetId"]) < (chosen["arrivalTimeUs"], chosen["packetId"]): rec[o["packetId"]]["overtakenCount"] += 1
        occ = len(q) / K
        decisions.append(dict(timeUs=t, chosenPacketId=chosen["packetId"], chosenClass=chosen["trafficClass"], queueLength=len(q),
                              occupancy=round(occ, 4), congestionLevel=congestion(occ, th), reasonCode=reason, details=details))
        emit(t, "SCHEDULER_DECISION", chosen["packetId"], {"reasonCode": reason, **details})
        q.remove(chosen)
        busy, cur = True, chosen
        r = rec[chosen["packetId"]]
        r["txStartUs"] = t
        emit(t, "PACKET_TRANSMISSION_STARTED", chosen["packetId"])
        heapq.heappush(ev, (t + tx_us(chosen["sizeBytes"], bw), 1, chosen["packetId"], "D"))
        snap(t)

    while ev:
        t, _, pid, typ = heapq.heappop(ev)
        p = P[pid]; r = rec[pid]
        if typ == "A":
            emit(t, "PACKET_CREATED", pid); emit(t, "PACKET_ARRIVED", pid)
            arr_times.append((t, p["sizeBytes"] * 8))
            if len(q) >= K:
                r.update(outcome="DROPPED", dropReason="QUEUE_OVERFLOW", dropTimeUs=t)
                emit(t, "PACKET_DROPPED", pid, {"reason": "QUEUE_OVERFLOW"})
            else:
                q.append(p); r["enqueueTimeUs"] = t
                emit(t, "PACKET_QUEUED", pid)
                heapq.heappush(ev, (p["deadlineUs"], 0, pid, "X"))
            snap(t)
        elif typ == "X":
            if r["txEndUs"] is None and r["txStartUs"] is None and not r["deadlineMissed"]:
                r["deadlineMissed"] = True; emit(t, "DEADLINE_MISSED", pid)
            elif cur is not None and cur["packetId"] == pid:
                if r["txStartUs"] + tx_us(p["sizeBytes"], bw) > p["deadlineUs"] and not r["deadlineMissed"]:
                    r["deadlineMissed"] = True; emit(t, "DEADLINE_MISSED", pid)
        else:
            busy, cur = False, None
            r["txEndUs"] = t
            r["waitingTimeUs"] = r["txStartUs"] - p["arrivalTimeUs"]
            r["serviceTimeUs"] = t - r["txStartUs"]
            r["totalDelayUs"] = t - p["arrivalTimeUs"]
            late = t > p["deadlineUs"]
            r["outcome"] = "LATE" if late else "ON_TIME"
            if late: r["deadlineMissed"] = True
            dep_times.append((t, p["sizeBytes"] * 8))
            emit(t, "PACKET_TRANSMISSION_COMPLETED", pid, {"outcome": r["outcome"]})
            snap(t)
        dispatch(t)
    return dict(records=[rec[k] for k in sorted(rec)], decisions=decisions, timeline=timeline, events=log)


# ---------------- metrics ----------------
def pct95(v):
    if not v: return None
    s = sorted(v); return s[max(0, math.ceil(0.95 * len(s)) - 1)]


def ms(x): return None if x is None else round(x / 1000, 4)


def block(pkts, recs, cfg, W, busy=None):
    G = len(pkts)
    R = [recs[p["packetId"]] for p in pkts]
    D = [r for r in R if r["txEndUs"] is not None]
    O = [r for r in D if r["outcome"] == "ON_TIME"]
    Lo = [r for r in R if r["dropReason"] == "QUEUE_OVERFLOW"]
    Le = [r for r in R if r["dropReason"] == "DEADLINE_EXPIRED"]
    A = len(D) + len(Le)
    miss = (len(D) - len(O)) + len(Le)
    frac = cfg["starvation"]["excessiveWaitFraction"]
    byid = {p["packetId"]: p for p in pkts}
    exc = [r for r in D if r["waitingTimeUs"] > frac * byid[r["packetId"]]["delayBudgetUs"]]
    starv = [r for r in exc if r["overtakenCount"] >= 1]
    avg = lambda k: ms(sum(r[k] for r in D) / len(D)) if D else None
    # jitter: consecutive delivered of same class, departure order
    jit = []
    pairs = {}
    for r in sorted(D, key=lambda r: r["txEndUs"]):
        c = byid[r["packetId"]]["trafficClass"]
        if c in pairs: jit.append(abs(r["totalDelayUs"] - pairs[c]))
        pairs[c] = r["totalDelayUs"]
    bits = sum(byid[r["packetId"]]["sizeBytes"] * 8 for r in D)
    d = lambda n: (n / G) if G else None
    m = dict(generated=G, accepted=A, delivered=len(D), deliveredOnTime=len(O), deliveredLate=len(D) - len(O),
             droppedOverflow=len(Lo), droppedExpired=len(Le), dropped=len(Lo) + len(Le),
             packetLossRate=d(len(Lo) + len(Le)), deadlineMisses=miss, deadlineMissRate=d(miss),
             deadlineMissRateAccepted=(miss / A) if A else None, onTimeRate=d(len(O)),
             avgWaitingTimeMs=avg("waitingTimeUs"), avgServiceTimeMs=avg("serviceTimeUs"), avgTotalDelayMs=avg("totalDelayUs"),
             maxWaitingTimeMs=ms(max((r["waitingTimeUs"] for r in D), default=None)) if D else None,
             p95TotalDelayMs=ms(pct95([r["totalDelayUs"] for r in D])),
             throughputPps=len(D) / (W / 1e6), throughputBps=bits / (W / 1e6), deliveredBits=bits,
             meanPacketSizeBytes=(sum(p["sizeBytes"] for p in pkts) / G) if G else None,
             jitterMs=ms(sum(jit) / len(jit)) if jit else None,
             excessiveWaitCount=len(exc), excessiveWaitRateAccepted=(len(exc) / A) if A else None,
             starvationCount=len(starv), starvationRateAccepted=(len(starv) / A) if A else None)
    if busy is not None:
        m["utilization"] = busy / W; m["observationWindowMs"] = W / 1000
    return m


def metrics(cfg, workload, out):
    recs = {r["packetId"]: r for r in out["records"]}
    last = max((r["txEndUs"] for r in out["records"] if r["txEndUs"]), default=0)
    W = max(int(cfg["simulationDuration"] * 1e6), last)
    busy = sum(r["serviceTimeUs"] for r in out["records"] if r["serviceTimeUs"])
    overall = block(workload, recs, cfg, W, busy)
    per = {c: block([p for p in workload if p["trafficClass"] == c], recs, cfg, W) for c in CLASSES}
    tl = out["timeline"]; K = cfg["queueCapacity"]
    integ, share = 0, {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    for a, b in zip(tl, tl[1:] + [dict(timeUs=W)]):
        dt = max(0, b["timeUs"] - a["timeUs"]); integ += a["queueLength"] * dt; share[a["congestionLevel"]] += dt
    qm = dict(meanQueueLength=integ / W, meanOccupancy=integ / W / K, maxQueueLength=max((x["queueLength"] for x in tl), default=0),
              maxOccupancy=max((x["queueLength"] for x in tl), default=0) / K,
              congestionTimeShare={k: v / W for k, v in share.items()})
    return dict(overall=overall, perClass=per, queue=qm)


def downsample(tl, n):
    if len(tl) <= n: return tl
    idx = sorted({round(i * (len(tl) - 1) / (n - 1)) for i in range(n)})
    return [tl[i] for i in idx]


def derived(cfg):
    mix = cfg["trafficMix"]
    mean = sum(mix[c] * mean_size(cfg["classes"][c]["sizeModel"]) for c in CLASSES)
    bps = cfg["linkBandwidthMbps"] * 1e6
    d = dict(linkBandwidthBps=bps, meanPacketSizeBytes=round(mean, 2), offeredLoad=round(cfg["incomingRate"] * mean * 8 / bps, 4),
             equivalentPacketRatePps=round(bps / (mean * 8), 2), burstOfferedLoad=[], byClass={}, warnings=[])
    for b in cfg["bursts"]:
        bm = b.get("trafficMixOverride", mix)
        bmean = sum(bm[c] * mean_size(cfg["classes"][c]["sizeModel"]) for c in CLASSES)
        d["burstOfferedLoad"].append(round(cfg["incomingRate"] * b["rateMultiplier"] * bmean * 8 / bps, 4))
    for c in CLASSES:
        m = cfg["classes"][c]["sizeModel"]
        lo = m.get("minBytes", m.get("bytes", min(v["bytes"] for v in m.get("values", [{"bytes": 0}]))))
        hi = m.get("maxBytes", m.get("bytes", max(v["bytes"] for v in m.get("values", [{"bytes": 0}]))))
        d["byClass"][c] = dict(txTimeMinUs=tx_us(lo, cfg["linkBandwidthMbps"]), txTimeMaxUs=tx_us(hi, cfg["linkBandwidthMbps"]))
    if d["offeredLoad"] >= 1: d["warnings"].append("Offered load is at or above 1: the link cannot carry the traffic and the queue will overflow.")
    return d


def simulate(name, seed=42):
    label, desc, ov, dur = PRESETS[name]
    cfg = base_config(name, ov, dur, seed)
    cfg["derived"] = derived(cfg)
    wl = gen_workload(cfg)
    fp = hashlib.sha256(json.dumps(wl, sort_keys=True).encode()).hexdigest()
    schedulers = {}
    for s in SCHED:
        out = run(cfg, wl, s)
        schedulers[s] = dict(metrics=metrics(cfg, wl, out), packets=out["records"], queueTimeline=downsample(out["timeline"], 1200),
                             decisions=out["decisions"], **({"events": out["events"]} if s == "ACAPS" else {}))  # event log kept for ACAPS only to bound fixture size
    mets = ["avgWaitingTimeMs", "avgTotalDelayMs", "deadlineMissRate", "throughputPps", "packetLossRate", "jitterMs", "starvationCount"]
    comp = dict(baseline="FIFO", metricDirections={m: "higher" if m.startswith("throughput") else "lower" for m in mets},
                metrics={m: {s: schedulers[s]["metrics"]["overall"][m] for s in SCHED} for m in mets},
                deltasVsFifo={m: {s: (None if schedulers[s]["metrics"]["overall"][m] is None or schedulers["FIFO"]["metrics"]["overall"][m] is None
                                      else schedulers[s]["metrics"]["overall"][m] - schedulers["FIFO"]["metrics"]["overall"][m]) for s in ("STATIC_PRIORITY", "ACAPS")} for m in mets},
                perClass={c: {m: {s: schedulers[s]["metrics"]["perClass"][c][m] for s in SCHED} for m in mets} for c in CLASSES})
    return dict(schemaVersion="1.0", config=cfg, workload=dict(fingerprint=fp, packetCount=len(wl), packets=wl), schedulers=schedulers, comparison=comp)


def aggregate(vals):
    v = [x for x in vals if x is not None]
    if not v: return dict(mean=None, std=None, min=None, max=None, n=0)
    mu = sum(v) / len(v)
    sd = math.sqrt(sum((x - mu) ** 2 for x in v) / (len(v) - 1)) if len(v) > 1 else None
    return dict(mean=mu, std=sd, min=min(v), max=max(v), n=len(v))


def agg_tree(items):
    if isinstance(items[0], dict): return {k: agg_tree([i[k] for i in items]) for k in items[0]}
    return aggregate(items)


def experiment(name, runs=12, seed=42):
    label, desc, ov, dur = PRESETS[name]
    cfg = base_config(name, ov, dur, seed); cfg["derived"] = derived(cfg)
    res, per = [], {s: [] for s in SCHED}
    for i in range(runs):
        c = dict(cfg, randomSeed=seed + i); wl = gen_workload(c)
        entry = dict(seed=seed + i, workloadFingerprint=hashlib.sha256(json.dumps(wl, sort_keys=True).encode()).hexdigest(), packetCount=len(wl), schedulers={})
        for s in SCHED:
            m = metrics(c, wl, run(c, wl, s, events=False)); entry["schedulers"][s] = m; per[s].append(m)
        res.append(entry)
    def strip(m):  # keep numeric leaves only
        return {"overall": {k: v for k, v in m["overall"].items()}, "perClass": m["perClass"], "queue": {k: v for k, v in m["queue"].items() if k != "congestionTimeShare"}}
    agg = {s: agg_tree([strip(m) for m in per[s]]) for s in SCHED}
    def delta(a, b):
        if isinstance(a, dict): return {k: delta(a[k], b[k]) for k in a}
        return None if a is None or b is None else a - b
    paired = {s: agg_tree([delta(strip(per[s][i]), strip(per["FIFO"][i])) for i in range(runs)]) for s in ("STATIC_PRIORITY", "ACAPS")}
    return dict(schemaVersion="1.0", config=cfg, baseSeed=seed, runCount=runs, runs=res, aggregate=agg, pairedDeltasVsFifo=paired)


def scenarios():
    lst = [dict(name="custom", label="Custom", description="Start from the base configuration and set every parameter yourself.",
                config={**base_config("custom", dict(incomingRate=800, linkBandwidthMbps=5), 10)})]
    for n, (label, desc, ov, dur) in PRESETS.items():
        c = base_config(n, ov, 10); c["derived"] = derived(c)
        lst.append(dict(name=n, label=label, description=desc, config=c))
    lst[0]["config"]["derived"] = derived(lst[0]["config"])
    return lst


def dump(name, obj):
    p = os.path.join(OUT, name)
    with open(p, "w") as f: json.dump(obj, f, separators=(",", ":"))
    print(name, round(os.path.getsize(p) / 1e6, 2), "MB")


if __name__ == "__main__":
    dump("scenarios.json", scenarios())
    for n in PRESETS: dump(f"simulate-{n}.json", simulate(n))
    for n in ("networkOverload", "emergencyBurst"): dump(f"experiments-{n}.json", experiment(n))
