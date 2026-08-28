"""评测统计辅助函数。"""
from __future__ import annotations

import math
import random


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def latency_summary(values_ms: list[float]) -> dict[str, float]:
    if not values_ms:
        return {"AvgLatencyMs": 0.0, "P95LatencyMs": 0.0}
    return {
        "AvgLatencyMs": round(sum(values_ms) / len(values_ms), 2),
        "P95LatencyMs": round(percentile(values_ms, 0.95), 2),
    }


def bootstrap_mean_ci(
    values: list[float], *, seed: int = 42, samples: int = 2000
) -> tuple[float, float]:
    """固定随机种子的 percentile bootstrap 95% 均值置信区间。"""
    if not values:
        return 0.0, 0.0
    rng = random.Random(seed)
    n = len(values)
    means = sorted(
        sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(samples)
    )
    lo = means[max(0, int(samples * 0.025) - 1)]
    hi = means[min(samples - 1, int(samples * 0.975))]
    return round(lo, 4), round(hi, 4)
