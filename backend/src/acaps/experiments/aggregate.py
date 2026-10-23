"""Aggregation of metrics over repeated runs: mean, sample standard deviation, min, max, n."""

import statistics
from typing import Any


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def summarize_values(values: list[float | None]) -> dict[str, Any]:
    """Statistics over the non-null values. std is the SAMPLE std (n-1); None if n < 2."""
    present = [v for v in values if v is not None]
    n = len(present)
    if n == 0:
        return {"mean": None, "std": None, "min": None, "max": None, "n": 0}
    return {
        "mean": round(statistics.fmean(present), 6),
        "std": round(statistics.stdev(present), 6) if n >= 2 else None,
        "min": round(min(present), 6),
        "max": round(max(present), 6),
        "n": n,
    }


def aggregate_metric_dicts(dicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Recursively aggregate a list of identically-shaped metric dicts (numeric leaves only)."""
    template = dicts[0]
    out: dict[str, Any] = {}
    for key, value in template.items():
        column = [d.get(key) for d in dicts]
        if isinstance(value, dict):
            out[key] = aggregate_metric_dicts([c if isinstance(c, dict) else {} for c in column])
        elif _is_number(value) or value is None:
            if all(c is None or _is_number(c) for c in column):
                out[key] = summarize_values(column)
    return out


def delta_metric_dicts(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """candidate - baseline for every numeric leaf (None if either side is None)."""
    out: dict[str, Any] = {}
    for key, value in candidate.items():
        base = baseline.get(key)
        if isinstance(value, dict) and isinstance(base, dict):
            out[key] = delta_metric_dicts(value, base)
        elif _is_number(value) or value is None:
            if value is None or base is None or not _is_number(base):
                out[key] = None
            else:
                out[key] = round(value - base, 6)
    return out
