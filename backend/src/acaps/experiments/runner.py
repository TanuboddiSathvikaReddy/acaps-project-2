"""ExperimentRunner: workload replay, scheduler comparison, size-neutral control, repeated runs.

RESEARCH FAIRNESS (enforced here)
    1. The workload is generated ONCE per seed.
    2. FIFO, Static Priority and ACAPS all replay that exact immutable Workload object, on
       identical network configuration, duration and packet properties.
    3. Each scheduler run starts from a fresh engine state (reset by construction).
    4. The three run fingerprints are asserted equal to the workload fingerprint.
    The ONLY thing that differs between the runs is the scheduling policy.
"""

from dataclasses import dataclass
from typing import Any

from acaps.config.models import SimulationConfig
from acaps.config.presets import make_size_neutral
from acaps.core.network import describe_network
from acaps.engine.simulation import RunRecord, SimulationEngine
from acaps.experiments.aggregate import aggregate_metric_dicts, delta_metric_dicts
from acaps.metrics.engine import MetricsEngine
from acaps.schedulers.acaps import make_scheduler
from acaps.schedulers.base import SchedulerName
from acaps.traffic.generator import TrafficGenerator
from acaps.traffic.workload import Workload

SCHEDULER_ORDER = (SchedulerName.FIFO, SchedulerName.STATIC_PRIORITY, SchedulerName.ACAPS)
BASELINE = SchedulerName.FIFO

# Metrics shown side by side in the comparison block, with the direction that is "better".
OVERALL_COMPARISON_METRICS = {
    "packetLossRate": "lower",
    "deadlineMissRate": "lower",
    "onTimeRate": "higher",
    "avgWaitingTimeMs": "lower",
    "avgServiceTimeMs": "lower",
    "avgTotalDelayMs": "lower",
    "p95TotalDelayMs": "lower",
    "maxWaitingTimeMs": "lower",
    "jitterMs": "lower",
    "throughputPps": "higher",
    "throughputBps": "higher",
    "utilization": "higher",
    "excessiveWaitCount": "lower",
    "starvationCount": "lower",
}
CLASS_COMPARISON_METRICS = {
    "deadlineMissRate": "lower",
    "onTimeRate": "higher",
    "packetLossRate": "lower",
    "avgWaitingTimeMs": "lower",
    "avgTotalDelayMs": "lower",
    "p95TotalDelayMs": "lower",
    "jitterMs": "lower",
    "starvationCount": "lower",
}


@dataclass
class SchedulerRun:
    run: RunRecord
    metrics: dict[str, Any]


@dataclass
class SimulationResult:
    config: SimulationConfig
    workload: Workload
    runs: dict[SchedulerName, SchedulerRun]
    comparison: dict[str, Any]
    size_neutral_control: "SimulationResult | None" = None

    @property
    def metrics(self) -> dict[SchedulerName, dict[str, Any]]:
        return {name: r.metrics for name, r in self.runs.items()}


# ------------------------------------------------------------------ single seed


def run_schedulers(config: SimulationConfig, workload: Workload) -> dict[SchedulerName, SchedulerRun]:
    """Replay ONE workload under every scheduler (same object, fresh engine each time)."""
    metrics_engine = MetricsEngine(config.starvation.excessive_wait_fraction)
    runs: dict[SchedulerName, SchedulerRun] = {}
    for name in SCHEDULER_ORDER:
        scheduler = make_scheduler(name, config.aging)
        run = SimulationEngine(config, workload, scheduler).run()
        if run.workload_fingerprint != workload.fingerprint:
            raise AssertionError(f"{name}: workload changed during the run")
        metrics = metrics_engine.compute(run, config.classes, config.queue_capacity)
        runs[name] = SchedulerRun(run, metrics)
    fingerprints = {r.run.workload_fingerprint for r in runs.values()}
    if len(fingerprints) != 1:
        raise AssertionError("schedulers did not replay an identical workload")
    return runs


def build_comparison(metrics: dict[SchedulerName, dict[str, Any]], class_names: list[str]) -> dict[str, Any]:
    """Common-format comparison: values per scheduler and difference versus the FIFO baseline."""

    def side_by_side(getter, keys: dict[str, str]) -> dict[str, Any]:
        return {k: {n.value: getter(metrics[n], k) for n in SCHEDULER_ORDER} for k in keys}

    def deltas(table: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, row in table.items():
            base = row[BASELINE.value]
            out[key] = {
                n.value: (None if row[n.value] is None or base is None else round(row[n.value] - base, 6))
                for n in SCHEDULER_ORDER
                if n is not BASELINE
            }
        return out

    overall = side_by_side(lambda m, k: m["overall"][k], OVERALL_COMPARISON_METRICS)
    per_class: dict[str, Any] = {}
    for cls in class_names:
        table = side_by_side(lambda m, k, c=cls: m["perClass"][c][k], CLASS_COMPARISON_METRICS)
        per_class[cls] = {"metrics": table, "deltasVsFifo": deltas(table)}
    return {
        "baseline": BASELINE.value,
        "metricDirections": {"overall": OVERALL_COMPARISON_METRICS, "perClass": CLASS_COMPARISON_METRICS},
        "metrics": overall,
        "deltasVsFifo": deltas(overall),
        "perClass": per_class,
    }


def run_simulation(config: SimulationConfig, include_size_neutral_control: bool | None = None) -> SimulationResult:
    """One seed, all three schedulers, one shared workload."""
    workload = TrafficGenerator(config).generate()  # generated exactly once
    runs = run_schedulers(config, workload)
    class_names = sorted(config.classes)
    result = SimulationResult(
        config=config,
        workload=workload,
        runs=runs,
        comparison=build_comparison({n: r.metrics for n, r in runs.items()}, class_names),
    )
    if include_size_neutral_control is None:
        include_size_neutral_control = config.options.include_size_neutral_control
    if include_size_neutral_control:
        result.size_neutral_control = run_simulation(make_size_neutral(config), include_size_neutral_control=False)
    return result


# ------------------------------------------------------------------ repeated runs


def _seed_sweep(config: SimulationConfig, runs: int) -> dict[str, Any]:
    """Run seeds baseSeed .. baseSeed+runs-1; aggregate per scheduler plus paired deltas vs FIFO."""
    per_run: list[dict[str, Any]] = []
    metrics_by_scheduler: dict[SchedulerName, list[dict[str, Any]]] = {n: [] for n in SCHEDULER_ORDER}
    paired: dict[SchedulerName, list[dict[str, Any]]] = {n: [] for n in SCHEDULER_ORDER if n is not BASELINE}

    for i in range(runs):
        seed = config.random_seed + i
        run_config = config.model_copy(update={"random_seed": seed})
        workload = TrafficGenerator(run_config).generate()
        scheduler_runs = run_schedulers(run_config, workload)
        metrics = {n: r.metrics for n, r in scheduler_runs.items()}
        per_run.append(
            {
                "seed": seed,
                "workloadFingerprint": workload.fingerprint,
                "packetCount": len(workload),
                "schedulers": {n.value: m for n, m in metrics.items()},
            }
        )
        for name in SCHEDULER_ORDER:
            metrics_by_scheduler[name].append(metrics[name])
            if name is not BASELINE:
                # PAIRED difference: same seed => same workload for both schedulers.
                paired[name].append(delta_metric_dicts(metrics[name], metrics[BASELINE]))

    return {
        "runs": per_run,
        "aggregate": {n.value: aggregate_metric_dicts(m) for n, m in metrics_by_scheduler.items()},
        "pairedDeltasVsFifo": {n.value: aggregate_metric_dicts(d) for n, d in paired.items()},
    }


def run_experiment(config: SimulationConfig, runs: int, include_size_neutral_control: bool | None = None) -> dict[str, Any]:
    """Repeat the scenario over `runs` consecutive seeds and aggregate."""
    if runs < 1:
        raise ValueError("runs must be >= 1")
    result: dict[str, Any] = {"baseSeed": config.random_seed, "runCount": runs, **_seed_sweep(config, runs)}
    if include_size_neutral_control is None:
        include_size_neutral_control = config.options.include_size_neutral_control
    if include_size_neutral_control:
        control_config = make_size_neutral(config)
        result["sizeNeutralControl"] = {
            "scenario": control_config.scenario,
            "derived": describe_network(control_config),
            **_seed_sweep(control_config, runs),
        }
    return result
