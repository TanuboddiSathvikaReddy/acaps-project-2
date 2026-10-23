#!/usr/bin/env python3
"""Run every scenario over consecutive seeds and write a Markdown report.

    python scripts/run_sample.py --runs 20 --out docs/SAMPLE_RESULTS.md

Protocol (see docs/EXPERIMENTS.md):
  * each seed generates ONE workload that FIFO, Static Priority and ACAPS all replay;
  * seeds are consecutive: 42, 43, ..., 42 + runs - 1;
  * tables show mean +- sample standard deviation (n-1) over seeds;
  * "paired delta" = (scheduler - FIFO) computed per seed on the identical workload, then aggregated.
Scenarios are used exactly as defined in src/acaps/config/presets.py. They were fixed before any
scheduler comparison and are not tuned. Everything here describes the TESTED configurations only.
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from acaps import __version__  # noqa: E402
from acaps.config.presets import PRESETS, resolve_config  # noqa: E402
from acaps.core.network import describe_network  # noqa: E402
from acaps.experiments.runner import SCHEDULER_ORDER, run_experiment  # noqa: E402

SCENARIOS = [
    "normalTraffic",
    "heavyTraffic",
    "emergencyBurst",
    "videoHeavy",
    "networkOverload",
    "mixedTraffic",
    "sizeNeutralControl",
    "emergencyBurstSizeNeutral",
    "networkOverloadSizeNeutral",
]
# (original scenario, its size-neutral version)
SIZE_NEUTRAL_PAIRS = [
    ("emergencyBurst", "emergencyBurstSizeNeutral"),
    ("networkOverload", "networkOverloadSizeNeutral"),
]
SCHED = [n.value for n in SCHEDULER_ORDER]

OVERALL_ROWS = [
    ("Packet loss rate", "packetLossRate", "pct"),
    ("Deadline miss rate", "deadlineMissRate", "pct"),
    ("Avg waiting time (ms)", "avgWaitingTimeMs", "ms"),
    ("p95 total delay (ms)", "p95TotalDelayMs", "ms"),
    ("Jitter (ms)", "jitterMs", "ms"),
    ("Starved packets", "starvationCount", "count"),
    ("Utilization", "utilization", "pct"),
]


def fmt(stat: dict | None, kind: str, signed: bool = False) -> str:
    if stat is None or stat.get("mean") is None:
        return "n/a"
    mean, std = stat["mean"], stat["std"]
    sign = "+" if signed else ""
    if kind == "pct":
        text, spread = f"{mean * 100:{sign}.2f}%", None if std is None else f"{std * 100:.2f}"
    elif kind == "count":
        text, spread = f"{mean:{sign}.1f}", None if std is None else f"{std:.1f}"
    else:
        text, spread = f"{mean:{sign}.2f}", None if std is None else f"{std:.2f}"
    return text if spread is None else f"{text} ± {spread}"


def overall_cells(exp: dict, key: str, kind: str) -> list[str]:
    """[FIFO, Static, ACAPS, paired delta Static, paired delta ACAPS] for an overall metric."""
    return [fmt(exp["aggregate"][s]["overall"][key], kind) for s in SCHED] + [
        fmt(exp["pairedDeltasVsFifo"][s]["overall"][key], kind, signed=True) for s in SCHED[1:]
    ]


def load_text(derived: dict) -> str:
    text = f"{derived['offeredLoad']:.2f}"
    if derived["burstOfferedLoad"]:
        text += " (burst " + ", ".join(f"{x:.2f}" for x in derived["burstOfferedLoad"]) + ")"
    return text


HEADER5 = ["FIFO", "Static Priority", "ACAPS", "Δ Static vs FIFO (paired)", "Δ ACAPS vs FIFO (paired)"]


def table(first: str, rows: list[list[str]]) -> list[str]:
    head = "| " + first + " | " + " | ".join(HEADER5) + " |"
    return [head, "|---|" + "---:|" * 5] + ["| " + " | ".join(r) + " |" for r in rows] + [""]


def summary_section(results: dict) -> list[str]:
    lines = ["## Summary across scenarios", ""]
    for title, key in (("Deadline miss rate", "deadlineMissRate"), ("Packet loss rate", "packetLossRate")):
        rows = [
            [f"{name} (ρ {load_text(results[name]['derived'])})"] + overall_cells(results[name]["exp"], key, "pct")
            for name in results
        ]
        lines += [f"**{title}** (mean ± std over seeds; paired deltas versus FIFO)", ""] + table("Scenario", rows)
    # Exact counts: a rate printed as 0.00% can hide a single late packet, so also show the counts.
    for title, key in (
        ("Deadline misses per run (packets; min..max over seeds, mean in brackets)", "deadlineMisses"),
        ("Packets dropped per run (overflow + expiry; min..max over seeds, mean in brackets)", "dropped"),
    ):
        lines += [f"**{title}**", "", "| Scenario | FIFO | Static Priority | ACAPS |", "|---|---:|---:|---:|"]
        for name in results:
            cells = []
            for sched in SCHED:
                stat = results[name]["exp"]["aggregate"][sched]["overall"][key]
                cells.append(f"{stat['min']:.0f}..{stat['max']:.0f} ({stat['mean']:.1f})")
            lines.append(f"| {name} | " + " | ".join(cells) + " |")
        lines.append("")
    return lines


def size_neutral_section(results: dict, runs: int) -> list[str]:
    lines = [
        "## Size-neutral control experiments",
        "",
        "Purpose: check whether scheduler-dependent **packet loss** differences in an overloaded scenario come",
        "from scheduling or from class-correlated packet sizes. Each pair below has identical rate, bandwidth,",
        "queue, class mix, bursts, deadlines, ranks, seeds, and identical arrival times and class sequence;",
        "the only difference is that the size-neutral version gives every class the same fixed packet size.",
        f"Same protocol (seeds 42..{42 + runs - 1}, paired deltas vs FIFO).",
        "",
    ]
    for original, neutral in SIZE_NEUTRAL_PAIRS:
        if original not in results or neutral not in results:
            continue
        lines += [f"### {original}  vs  {neutral}", ""]
        for name in (original, neutral):
            d = results[name]["derived"]
            sizes = {v["meanSizeBytes"] for v in d["byClass"].values()}
            size_text = "class-correlated sizes" if len(sizes) > 1 else f"fixed {next(iter(sizes)):.0f} B for every class"
            lines.append(f"* `{name}`: {size_text}; offered load ρ {load_text(d)}")
        lines.append("")
        for title, key in (("Packet loss rate", "packetLossRate"), ("Deadline miss rate", "deadlineMissRate")):
            rows = [[name] + overall_cells(results[name]["exp"], key, "pct") for name in (original, neutral)]
            lines += [f"**{title}**", ""] + table("Scenario", rows)
        classes = sorted(results[original]["exp"]["aggregate"]["FIFO"]["perClass"])
        rows = []
        for c in classes:
            for name in (original, neutral):
                agg = results[name]["exp"]["aggregate"]
                rows.append([f"{c} / {'original' if name == original else 'size-neutral'}"] + [fmt(agg[s]["perClass"][c]["packetLossRate"], "pct") for s in SCHED])
        lines += ["**Packet loss rate by class**", "", "| Class / version | FIFO | Static Priority | ACAPS |", "|---|---:|---:|---:|"]
        lines += ["| " + " | ".join(r) + " |" for r in rows] + [""]
    return lines


def scenario_section(name: str, runs: int, seconds: float, exp: dict, derived: dict) -> list[str]:
    agg = exp["aggregate"]
    lines = [
        f"### {name}",
        "",
        PRESETS[name].description,
        "",
        f"Offered load ρ = {load_text(derived)}; {runs} seeds; ~{exp['runs'][0]['packetCount']} packets per run; computed in {seconds:.0f} s.",
        "",
        "**Overall (mean ± std over seeds)**",
        "",
    ]
    lines += table("Metric", [[label] + overall_cells(exp, key, kind) for label, key, kind in OVERALL_ROWS])
    classes = sorted(agg["FIFO"]["perClass"], key=lambda c: derived["byClass"][c]["criticalityRank"])
    for title, key, kind in (
        ("Deadline miss rate by class", "deadlineMissRate", "pct"),
        ("Packet loss rate by class", "packetLossRate", "pct"),
        ("Average waiting time by class (ms)", "avgWaitingTimeMs", "ms"),
    ):
        lines += [f"**{title}**", "", "| Class (rank, budget) | FIFO | Static Priority | ACAPS |", "|---|---:|---:|---:|"]
        for c in classes:
            info = derived["byClass"][c]
            label = f"{c} (rank {info['criticalityRank']}, {info['delayBudgetUs'] / 1000:.0f} ms)"
            lines.append(f"| {label} | " + " | ".join(fmt(agg[s]["perClass"][c][key], kind) for s in SCHED) + " |")
        lines.append("")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=int, default=20, help="consecutive seeds per scenario")
    parser.add_argument("--out", type=Path, default=Path("docs/SAMPLE_RESULTS.md"))
    parser.add_argument("--json", type=Path, default=None, help="also dump the aggregated results as JSON")
    parser.add_argument("--scenarios", nargs="*", default=SCENARIOS)
    args = parser.parse_args()

    results: dict[str, dict] = {}
    for name in args.scenarios:
        config = resolve_config({"scenario": name})
        started = time.time()
        print(f"running {name} x{args.runs} ...", flush=True)
        exp = run_experiment(config, args.runs, include_size_neutral_control=False)
        results[name] = {"exp": exp, "derived": describe_network(config), "seconds": time.time() - started}
        print(f"  done in {results[name]['seconds']:.0f} s", flush=True)

    report = [
        "# Sample experiment results",
        "",
        f"Generated by `scripts/run_sample.py` (ACAPS {__version__}, Python {platform.python_version()}).",
        f"{args.runs} consecutive seeds per scenario (42..{42 + args.runs - 1}); each seed generates ONE workload replayed by",
        "FIFO, Static Priority and ACAPS. Values are mean ± sample standard deviation over seeds. Paired deltas are",
        "(scheduler − FIFO) per seed on the identical workload, then aggregated.",
        "Scenarios were fixed before any comparison and are not tuned. Every statement here refers to the tested",
        "configurations, workloads and number of runs only. Read `docs/EXPERIMENTS.md` before interpreting the numbers.",
        "",
    ]
    report += summary_section(results) + size_neutral_section(results, args.runs)
    report += ["## Per-scenario details", ""]
    for name, r in results.items():
        report += scenario_section(name, args.runs, r["seconds"], r["exp"], r["derived"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(report) + "\n")
    if args.json:
        args.json.write_text(json.dumps({n: {"derived": r["derived"], "aggregate": r["exp"]["aggregate"],
                                             "pairedDeltasVsFifo": r["exp"]["pairedDeltasVsFifo"]} for n, r in results.items()}, indent=1))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
