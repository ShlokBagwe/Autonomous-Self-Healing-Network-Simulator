"""
Evaluation Metrics and Statistical Significance Testing for Member 4.
Computes MTTD, MTTR, PDR, latency, throughput recovery, and Mann-Whitney U test.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.7, 8 and Plan_docs/member-4-frontend-eval.md.
"""
from typing import Dict, List, Optional, Tuple
import numpy as np
from scipy import stats


def mean_std(values: List[float]) -> Tuple[float, float]:
    """Calculate mean ± standard deviation."""
    if not values:
        return 0.0, 0.0
    arr = np.array(values, dtype=float)
    return float(np.mean(arr)), float(np.std(arr, ddof=1 if len(arr) > 1 else 0))


def format_mean_std(values: List[float], unit: str = "ms") -> str:
    """Format as 'mean ± std unit'."""
    m, s = mean_std(values)
    return f"{m:.2f} ± {s:.2f} {unit}"


def compute_mann_whitney(
    baseline_samples: List[float],
    test_samples: List[float],
    alternative: str = "two-sided",
) -> Dict[str, float]:
    """
    Perform non-parametric Mann-Whitney U test between static baseline and self-healing.
    Returns U statistic, p-value, and whether difference is statistically significant (p < 0.05).
    """
    if len(baseline_samples) < 3 or len(test_samples) < 3:
        return {"u_stat": 0.0, "p_value": 1.0, "is_significant": False}

    res = stats.mannwhitneyu(baseline_samples, test_samples, alternative=alternative)
    return {
        "u_stat": float(res.statistic),
        "p_value": float(res.pvalue),
        "is_significant": bool(res.pvalue < 0.05),
    }


def compute_mttd(t_fault_onset: float, alert_timestamps: List[float]) -> Optional[float]:
    """
    Mean Time to Detect (MTTD) = first detection timestamp - fault onset.
    """
    valid_ts = [t for t in alert_timestamps if t >= t_fault_onset]
    if not valid_ts:
        return None
    return round((min(valid_ts) - t_fault_onset) * 1000.0, 2)  # in ms


def compute_mttr(t_fault_onset: float, t_recovered: float) -> float:
    """
    Mean Time to Recover (MTTR) = recovery timestamp - fault onset.
    """
    return round(max(0.0, (t_recovered - t_fault_onset) * 1000.0), 2)  # in ms


def compute_pdr(delivered_packets: int, total_packets: int) -> float:
    """
    Packet Delivery Ratio (PDR) = delivered / total.
    """
    if total_packets == 0:
        return 1.0
    return round(delivered_packets / total_packets, 4)
