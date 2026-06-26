"""
Anomaly Correlator

Cross-references syslog burst patterns with SNMP threshold breaches to
raise or lower confidence of failure predictions. A device showing both
SNMP degradation AND correlated syslog bursts gets a confidence boost.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np

from src.utils.config import analytics_cfg, get_path


def load_syslog_data(db_path: Optional[Path] = None) -> pd.DataFrame:
    """Load syslog data from SQLite."""
    if db_path is None:
        db_path = get_path("paths.sqlite_db")
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql("SELECT * FROM syslog", conn)
    conn.close()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def compute_syslog_burst_score(
    syslog_df: pd.DataFrame,
    device_id: str,
    window_start: datetime,
    window_end: datetime,
) -> Dict[str, Any]:
    """
    Compute a burst score for a device over a time window.

    High severity (0-3) log frequency is compared to baseline.
    A burst indicates correlated anomalous activity.
    """
    device_logs = syslog_df[syslog_df["device_id"] == device_id].copy()

    if device_logs.empty:
        return {"burst_score": 0.0, "high_severity_count": 0, "total_count": 0, "burst_detected": False}

    # Ensure timestamp is datetime
    if not pd.api.types.is_datetime64_any_dtype(device_logs["timestamp"]):
        device_logs["timestamp"] = pd.to_datetime(device_logs["timestamp"])

    # Window logs
    window_mask = (device_logs["timestamp"] >= window_start) & (device_logs["timestamp"] <= window_end)
    window_logs = device_logs[window_mask]

    # Baseline: all logs before window
    baseline_logs = device_logs[device_logs["timestamp"] < window_start]

    # Count high-severity logs (severity 0-3: EMERG, ALERT, CRIT, ERROR)
    high_sev_window = len(window_logs[window_logs["severity"] <= 3])
    total_window = len(window_logs)

    # Baseline rate (high-severity per minute)
    if not baseline_logs.empty:
        baseline_duration = (baseline_logs["timestamp"].max() - baseline_logs["timestamp"].min()).total_seconds() / 60.0
        baseline_high_sev = len(baseline_logs[baseline_logs["severity"] <= 3])
        baseline_rate = baseline_high_sev / max(baseline_duration, 1.0)
    else:
        baseline_rate = 0.1  # default low rate

    # Window rate
    window_duration = (window_end - window_start).total_seconds() / 60.0
    window_rate = high_sev_window / max(window_duration, 1.0)

    # Burst score: how much window rate exceeds baseline
    if baseline_rate > 0:
        burst_ratio = window_rate / baseline_rate
    else:
        burst_ratio = window_rate * 10  # no baseline = any high-sev is significant

    burst_score = min(1.0, burst_ratio / 5.0)  # normalize to [0, 1]
    burst_detected = burst_score > 0.3

    return {
        "burst_score": round(float(burst_score), 4),
        "high_severity_count": int(high_sev_window),
        "total_count": int(total_window),
        "window_rate_per_min": round(float(window_rate), 4),
        "baseline_rate_per_min": round(float(baseline_rate), 4),
        "burst_detected": burst_detected,
    }


def correlate_anomalies(
    predictions: pd.DataFrame,
    syslog_df: pd.DataFrame,
    lookback_minutes: int = 30,
) -> pd.DataFrame:
    """
    Adjust failure probabilities based on syslog correlation.

    For each device with elevated failure probability:
    - Check syslog for burst activity in the recent window
    - Boost confidence if correlated burst found
    - Slightly reduce confidence if syslog is clean (possible false positive)
    """
    cfg = analytics_cfg()
    confidence_boost = cfg.get("anomaly_confidence_boost", 0.15)

    adjusted = predictions.copy()
    correlation_details = []

    for device_id in adjusted["device_id"].unique():
        device_mask = adjusted["device_id"] == device_id
        device_preds = adjusted[device_mask]

        if device_preds.empty:
            continue

        latest_ts = device_preds["timestamp"].max()
        window_start = latest_ts - timedelta(minutes=lookback_minutes)

        burst_info = compute_syslog_burst_score(
            syslog_df, device_id, window_start, latest_ts
        )

        if burst_info["burst_detected"]:
            # Boost failure probability
            boost = confidence_boost * burst_info["burst_score"]
            adjusted.loc[device_mask, "failure_prob"] = np.clip(
                adjusted.loc[device_mask, "failure_prob"] + boost, 0.0, 1.0
            )
            adjusted.loc[device_mask, "syslog_correlated"] = True
        else:
            # Mild reduction if SNMP says degrading but syslog is clean
            high_prob_mask = device_mask & (adjusted["failure_prob"] > 0.5)
            adjusted.loc[high_prob_mask, "failure_prob"] *= 0.9
            adjusted.loc[device_mask, "syslog_correlated"] = False

        correlation_details.append({
            "device_id": device_id,
            **burst_info,
        })

    if "syslog_correlated" not in adjusted.columns:
        adjusted["syslog_correlated"] = False

    return adjusted


def get_anomaly_report(
    predictions: pd.DataFrame,
    syslog_df: pd.DataFrame,
) -> List[Dict[str, Any]]:
    """
    Generate a comprehensive anomaly report combining SNMP predictions
    and syslog correlation for each device.
    """
    report = []
    threshold = analytics_cfg().get("failure_probability_threshold", 0.65)

    for device_id in predictions["device_id"].unique():
        device_preds = predictions[predictions["device_id"] == device_id]
        latest = device_preds.sort_values("timestamp").iloc[-1]

        if latest["failure_prob"] < 0.3:
            continue  # Skip healthy devices

        latest_ts = latest["timestamp"]
        burst_info = compute_syslog_burst_score(
            syslog_df, device_id,
            latest_ts - timedelta(minutes=30), latest_ts
        )

        entry = {
            "device_id": device_id,
            "failure_probability": round(float(latest["failure_prob"]), 4),
            "risk_level": (
                "CRITICAL" if latest["failure_prob"] >= 0.8 else
                "HIGH" if latest["failure_prob"] >= 0.6 else
                "MEDIUM"
            ),
            "syslog_burst": burst_info,
            "contributing_metrics": latest.get("contributing_metrics", []),
            "correlated": burst_info["burst_detected"] and latest["failure_prob"] >= threshold,
            "timestamp": str(latest_ts),
            "recommendation": (
                "IMMEDIATE ACTION REQUIRED — correlated SNMP + syslog anomalies"
                if burst_info["burst_detected"] and latest["failure_prob"] >= 0.8
                else "Monitor closely — elevated failure probability detected"
                if latest["failure_prob"] >= threshold
                else "Within acceptable range but trending upward"
            ),
        }
        report.append(entry)

    report.sort(key=lambda x: -x["failure_probability"])
    return report
