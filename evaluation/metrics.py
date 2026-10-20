"""
Evaluation Metrics and Statistical Significance Testing for Member 4.
Computes MTTD, MTTR, PDR, latency, throughput recovery, and Mann-Whitney U test.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.7, 8 and Plan_docs/member-4-frontend-eval.md.
"""
from typing import Any, Dict, List, Optional, Tuple, Union
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


def compute_split_mttr(
    reroute_events: List[Any],
) -> Dict[str, Any]:
    """
    Compute split MTTR across reactive (SNMP TRAP) and proactive (ML Engine) detection mechanisms.
    Determines bucket by trigger_alert.source ('snmp_trap' vs 'ml_engine').

    Returns dict:
      - reactive_mttr_ms: mean recovery latency (ms) for SNMP TRAP-triggered reroutes
      - proactive_mttr_ms: mean recovery latency (ms) for ML Engine-triggered reroutes
      - overall_mttr_ms: overall mean recovery latency (ms)
      - reactive_count: count of reactive reroutes
      - proactive_count: count of proactive reroutes
      - total_count: total reroutes evaluated
    """
    reactive_mttrs: List[float] = []
    proactive_mttrs: List[float] = []

    for ev in reroute_events:
        if ev is None:
            continue
        # Extract recovery_latency_ms
        if hasattr(ev, "recovery_latency_ms"):
            lat = ev.recovery_latency_ms
        elif isinstance(ev, dict):
            lat = ev.get("recovery_latency_ms")
        else:
            lat = None

        if lat is None:
            continue

        try:
            val = float(lat)
        except (ValueError, TypeError):
            continue

        # Extract trigger_alert source
        source = None
        if hasattr(ev, "trigger_alert"):
            alert = ev.trigger_alert
            source = getattr(alert, "source", None) if not isinstance(alert, dict) else alert.get("source")
        elif isinstance(ev, dict):
            alert = ev.get("trigger_alert", {})
            source = alert.get("source") if isinstance(alert, dict) else getattr(alert, "source", None)

        if source == "snmp_trap":
            reactive_mttrs.append(val)
        elif source == "ml_engine":
            proactive_mttrs.append(val)

    all_mttrs = reactive_mttrs + proactive_mttrs

    return {
        "reactive_mttr_ms": round(sum(reactive_mttrs) / len(reactive_mttrs), 2) if reactive_mttrs else None,
        "proactive_mttr_ms": round(sum(proactive_mttrs) / len(proactive_mttrs), 2) if proactive_mttrs else None,
        "overall_mttr_ms": round(sum(all_mttrs) / len(all_mttrs), 2) if all_mttrs else None,
        "reactive_count": len(reactive_mttrs),
        "proactive_count": len(proactive_mttrs),
        "total_count": len(all_mttrs),
    }


def compute_pdr(delivered_packets: int, total_packets: int) -> float:
    """
    Packet Delivery Ratio (PDR) = delivered / total.
    """
    if total_packets == 0:
        return 1.0
    return round(delivered_packets / total_packets, 4)


def compute_avg_rtt_latency(readings: Union[Dict[str, Any], List[Any]]) -> float:
    """
    Avg RTT Latency = arithmetic mean of the `latency` field from the most recent
    TelemetryReading of every currently-monitored link that has a valid reading,
    at the time of calculation.

    valid_readings = [
        r.latency
        for r in latest_reading_per_link.values()
        if r is not None and r.latency is not None
    ]
    avg_rtt_latency = sum(valid_readings) / len(valid_readings) if valid_readings else 0

    Rules enforced:
    1. Include every link that still has a valid telemetry reading (degraded or
       congested links are included, weighted equally as 1 link out of N).
    2. Exclude a link only if it has no valid reading (e.g. link_failure / router_crash).
       Never substitute 0, a sentinel value, or last-known-good value.
    3. Never use a routing-cost or penalty value in this calculation.
    4. Recompute fresh on every poll cycle using latest valid readings.
    """
    if isinstance(readings, dict):
        reading_list = readings.values()
    else:
        reading_list = readings

    valid_readings: List[float] = []
    for r in reading_list:
        if r is None:
            continue
        lat = getattr(r, "latency", None) if not isinstance(r, dict) else r.get("latency")
        if lat is not None:
            try:
                val = float(lat)
                valid_readings.append(val)
            except (ValueError, TypeError):
                pass

    if not valid_readings:
        return 0.0
    return round(sum(valid_readings) / len(valid_readings), 2)

