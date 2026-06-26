"""
SNMP Metrics Simulator
Generates time-series telemetry (CPU%, error rate, latency, packet loss, temperature)
per device with realistic noise + injected degradation trends leading to known failure events.

The failure ground truth is stored so forecasting models can be trained/evaluated against it.
"""

import json
import random
import sqlite3
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.utils.config import simulator_cfg, get_path


METRICS = ["cpu_percent", "error_rate", "latency_ms", "packet_loss", "temperature_c"]


def _get_normal_range(metric: str, cfg: Dict) -> Tuple[float, float]:
    """Return (low, high) for a metric under normal conditions."""
    metrics_cfg = cfg.get("metrics", {})
    ranges = {
        "cpu_percent": metrics_cfg.get("cpu_normal_range", [10, 60]),
        "error_rate": metrics_cfg.get("error_rate_normal", [0.0, 0.02]),
        "latency_ms": metrics_cfg.get("latency_normal_ms", [1, 20]),
        "packet_loss": metrics_cfg.get("packet_loss_normal", [0.0, 0.01]),
        "temperature_c": metrics_cfg.get("temperature_normal", [30, 55]),
    }
    r = ranges.get(metric, [0, 50])
    return float(r[0]), float(r[1])


def _get_critical_value(metric: str, cfg: Dict) -> float:
    """Return the critical threshold for a metric."""
    metrics_cfg = cfg.get("metrics", {})
    crits = {
        "cpu_percent": metrics_cfg.get("cpu_critical", 95),
        "error_rate": metrics_cfg.get("error_rate_critical", 0.15),
        "latency_ms": metrics_cfg.get("latency_critical_ms", 200),
        "packet_loss": metrics_cfg.get("packet_loss_critical", 0.10),
        "temperature_c": metrics_cfg.get("temperature_critical", 85),
    }
    return float(crits.get(metric, 90))


def plan_failure_events(
    device_ids: List[str],
    start_time: datetime,
    duration_hours: int,
    seed: int = 42,
) -> List[Dict[str, Any]]:
    """
    Plan failure events for the simulation.
    Returns list of: {device_id, failure_time, affected_metrics, pre_failure_window_min}
    """
    cfg = simulator_cfg()
    rng = random.Random(seed)
    failure_cfg = cfg.get("failure_injection", {})
    min_f = failure_cfg.get("min_failures", 3)
    max_f = failure_cfg.get("max_failures", 6)
    pre_window = failure_cfg.get("pre_failure_window_minutes", 30)

    num_failures = rng.randint(min_f, max_f)
    events = []

    for _ in range(num_failures):
        device_id = rng.choice(device_ids)
        # Failures happen in the latter 70% of the timeline (so we have clean training data)
        offset_minutes = rng.randint(
            int(duration_hours * 60 * 0.3),
            int(duration_hours * 60 * 0.95),
        )
        failure_time = start_time + timedelta(minutes=offset_minutes)
        # Pick 1-3 metrics that degrade
        num_affected = rng.randint(1, 3)
        affected = rng.sample(METRICS, num_affected)
        events.append({
            "device_id": device_id,
            "failure_time": failure_time.isoformat(),
            "failure_timestamp": failure_time,
            "affected_metrics": affected,
            "pre_failure_window_min": pre_window,
            "severity": rng.choice(["critical", "major"]),
            "fault_type": rng.choice([
                "hardware_degradation",
                "link_flapping",
                "memory_leak",
                "thermal_throttling",
                "interface_errors",
            ]),
        })

    return events


def generate_snmp_data(
    device_ids: List[str],
    failure_events: List[Dict[str, Any]],
    start_time: Optional[datetime] = None,
    duration_hours: Optional[int] = None,
    interval_seconds: Optional[int] = None,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Generate SNMP time-series metrics for all devices.

    Normal data has realistic noise. Pre-failure windows show gradual degradation
    ramping toward critical values. This creates the signal for ML models.
    """
    cfg = simulator_cfg()
    if start_time is None:
        start_time = datetime.now() - timedelta(hours=cfg.get("history_hours", 24))
    if duration_hours is None:
        duration_hours = cfg.get("history_hours", 24)
    if interval_seconds is None:
        interval_seconds = cfg.get("tick_interval_seconds", 5)

    rng = np.random.RandomState(seed)
    end_time = start_time + timedelta(hours=duration_hours)
    timestamps = pd.date_range(start=start_time, end=end_time, freq=f"{interval_seconds}s")

    # Build a lookup: (device_id) -> list of failure events
    failure_lookup: Dict[str, List[Dict]] = {}
    for evt in failure_events:
        did = evt["device_id"]
        if did not in failure_lookup:
            failure_lookup[did] = []
        failure_lookup[did].append(evt)

    records = []

    for device_id in device_ids:
        device_failures = failure_lookup.get(device_id, [])

        for metric in METRICS:
            lo, hi = _get_normal_range(metric, cfg)
            crit = _get_critical_value(metric, cfg)
            base = rng.uniform(lo, hi)

            for ts in timestamps:
                # Start with normal noise
                noise = rng.normal(0, (hi - lo) * 0.05)
                # Add diurnal pattern (sinusoidal)
                hour_frac = ts.hour + ts.minute / 60.0
                diurnal = math.sin(2 * math.pi * hour_frac / 24) * (hi - lo) * 0.1
                value = base + noise + diurnal

                # Check if we're in a pre-failure degradation window
                is_degrading = False
                for evt in device_failures:
                    ft = evt["failure_timestamp"]
                    pre_window = evt["pre_failure_window_min"]
                    window_start = ft - timedelta(minutes=pre_window)

                    if metric in evt["affected_metrics"] and window_start <= ts <= ft:
                        # Calculate degradation progress (0 = window start, 1 = failure)
                        total_seconds = pre_window * 60
                        elapsed = (ts - window_start).total_seconds()
                        progress = elapsed / total_seconds

                        # Exponential ramp toward critical value
                        degradation = (crit - base) * (progress ** 2)
                        value = base + degradation + rng.normal(0, (hi - lo) * 0.03)
                        is_degrading = True
                        break

                # Clamp values
                if metric == "cpu_percent":
                    value = np.clip(value, 0, 100)
                elif metric in ("error_rate", "packet_loss"):
                    value = max(0.0, value)
                elif metric == "latency_ms":
                    value = max(0.1, value)
                elif metric == "temperature_c":
                    value = max(15.0, value)

                records.append({
                    "timestamp": ts,
                    "device_id": device_id,
                    "metric": metric,
                    "value": round(float(value), 4),
                    "is_degrading": is_degrading,
                })

    df = pd.DataFrame(records)
    return df


def save_snmp_to_sqlite(df: pd.DataFrame, db_path: Optional[Path] = None):
    """Save SNMP metrics DataFrame to SQLite."""
    if db_path is None:
        db_path = get_path("paths.sqlite_db")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    df_copy = df.copy()
    df_copy["timestamp"] = df_copy["timestamp"].astype(str)
    df_to_save = df_copy
    df_to_save.to_sql("snmp_metrics", conn, if_exists="replace", index=False)

    # Create index for fast queries
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snmp_device_ts ON snmp_metrics(device_id, timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snmp_metric ON snmp_metrics(metric)")
    conn.commit()
    conn.close()


def save_failure_events(events: List[Dict[str, Any]], db_path: Optional[Path] = None):
    """Save ground truth failure events to SQLite."""
    if db_path is None:
        db_path = get_path("paths.sqlite_db")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    clean_events = []
    for evt in events:
        clean_events.append({
            "device_id": evt["device_id"],
            "failure_time": evt["failure_time"],
            "affected_metrics": json.dumps(evt["affected_metrics"]),
            "pre_failure_window_min": evt["pre_failure_window_min"],
            "severity": evt["severity"],
            "fault_type": evt["fault_type"],
        })

    df = pd.DataFrame(clean_events)
    conn = sqlite3.connect(str(db_path))
    df.to_sql("failure_events", conn, if_exists="replace", index=False)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    from src.utils.config import ensure_dirs
    from src.ingestion.topology_sim import generate_topology
    ensure_dirs()

    _, devices = generate_topology()
    device_ids = list(devices.keys())
    start = datetime.now() - timedelta(hours=24)

    events = plan_failure_events(device_ids, start, 24)
    print(f"✅ Planned {len(events)} failure events")
    for e in events:
        print(f"   {e['device_id']} @ {e['failure_time']} — {e['fault_type']} ({e['affected_metrics']})")

    df = generate_snmp_data(device_ids, events, start_time=start, duration_hours=24, interval_seconds=60)
    save_snmp_to_sqlite(df)
    save_failure_events(events)
    print(f"✅ Generated {len(df)} SNMP metric rows → SQLite")
