"""
Feature Engineering for Predictive Failure Analysis

Computes rolling statistics (mean, slope, variance, max, rate-of-change)
over configurable sliding windows per metric per device.
The slopes are the primary predictive signal — a rising slope on error_rate
or temperature precedes failures.
"""

import sqlite3
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from pandas.errors import PerformanceWarning

from src.utils.config import analytics_cfg, get_path

# Suppress pandas fragmentation performance warnings
warnings.simplefilter(action="ignore", category=PerformanceWarning)


def load_snmp_data(db_path: Optional[Path] = None) -> pd.DataFrame:
    """Load SNMP metrics from SQLite into a DataFrame."""
    if db_path is None:
        db_path = get_path("paths.sqlite_db")
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql("SELECT * FROM snmp_metrics", conn)
    conn.close()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def load_failure_events(db_path: Optional[Path] = None) -> pd.DataFrame:
    """Load ground-truth failure events from SQLite."""
    if db_path is None:
        db_path = get_path("paths.sqlite_db")
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql("SELECT * FROM failure_events", conn)
    conn.close()
    df["failure_time"] = pd.to_datetime(df["failure_time"])
    return df


def _compute_slope_raw(arr: np.ndarray) -> float:
    """Linear regression slope over a window. Uses raw numpy array (fast)."""
    n = len(arr)
    if n < 2:
        return 0.0
    mask = ~np.isnan(arr)
    if mask.sum() < 2:
        return 0.0
    x = np.arange(n, dtype=np.float64)
    y = arr.astype(np.float64)
    if not np.all(mask):
        x, y = x[mask], y[mask]
        n = len(x)
    sx = x.sum()
    sy = y.sum()
    slope = (n * np.dot(x, y) - sx * sy) / (n * np.dot(x, x) - sx * sx + 1e-10)
    return float(slope)


def _roc_raw(arr: np.ndarray) -> float:
    """Rate of change: (last - first) / len. Uses raw numpy array (fast)."""
    if len(arr) < 2:
        return 0.0
    return float(arr[-1] - arr[0]) / (len(arr) + 1e-10)


def compute_rolling_features(
    df: pd.DataFrame,
    windows: Optional[List[int]] = None,
) -> pd.DataFrame:
    """
    Compute rolling window features for each (device_id, metric) pair.

    For each window size W (in minutes), computes:
      - rolling_mean_W
      - rolling_std_W
      - rolling_max_W
      - rolling_slope_W  (key predictive signal)
      - rolling_range_W  (max - min)
      - rate_of_change_W

    Returns a wide-format DataFrame indexed by (timestamp, device_id) with
    one column per (metric, feature, window) combination.
    """
    cfg = analytics_cfg()
    if windows is None:
        windows = cfg.get("feature_windows", [5, 15, 30, 60])

    # Pivot to wide format: one column per metric
    pivot = df.pivot_table(
        index=["timestamp", "device_id"],
        columns="metric",
        values="value",
        aggfunc="first",
    ).reset_index()
    pivot = pivot.sort_values(["device_id", "timestamp"])

    metrics = [c for c in pivot.columns if c not in ("timestamp", "device_id")]
    all_features = []

    for device_id, group in pivot.groupby("device_id"):
        group = group.sort_values("timestamp").reset_index(drop=True)

        # Estimate interval between rows (in minutes)
        if len(group) > 1:
            avg_interval = (group["timestamp"].diff().dt.total_seconds().median()) / 60.0
        else:
            avg_interval = 1.0

        device_features = group[["timestamp", "device_id"]].copy()

        for metric in metrics:
            series = group[metric].astype(float)

            for w in windows:
                window_rows = max(2, int(w / avg_interval))

                col_prefix = f"{metric}_w{w}"

                device_features[f"{col_prefix}_mean"] = series.rolling(
                    window=window_rows, min_periods=1
                ).mean()

                device_features[f"{col_prefix}_std"] = series.rolling(
                    window=window_rows, min_periods=1
                ).std().fillna(0)

                device_features[f"{col_prefix}_max"] = series.rolling(
                    window=window_rows, min_periods=1
                ).max()

                device_features[f"{col_prefix}_min"] = series.rolling(
                    window=window_rows, min_periods=1
                ).min()

                device_features[f"{col_prefix}_range"] = (
                    device_features[f"{col_prefix}_max"] - device_features[f"{col_prefix}_min"]
                )

                # Slope via rolling apply — raw=True passes numpy array (10-50x faster)
                device_features[f"{col_prefix}_slope"] = series.rolling(
                    window=window_rows, min_periods=2
                ).apply(_compute_slope_raw, raw=True).fillna(0)

                # Rate of change — raw=True for speed
                device_features[f"{col_prefix}_roc"] = series.rolling(
                    window=window_rows, min_periods=2
                ).apply(_roc_raw, raw=True).fillna(0)

            # Current value as a feature too
            device_features[f"{metric}_current"] = series

        all_features.append(device_features)

    result = pd.concat(all_features, ignore_index=True)
    return result


def create_training_labels(
    feature_df: pd.DataFrame,
    failure_events: pd.DataFrame,
    horizon_minutes: Optional[int] = None,
) -> pd.DataFrame:
    """
    Create binary labels for training: 1 if a failure occurs within the next
    `horizon_minutes` for that device, 0 otherwise.

    Also adds `time_to_failure_minutes` for regression targets.
    """
    cfg = analytics_cfg()
    if horizon_minutes is None:
        horizon_minutes = cfg.get("forecast_horizon_minutes", 60)

    # Pre-sort/group failure events
    failures_by_device = {}
    for device_id, group in failure_events.groupby("device_id"):
        failures_by_device[device_id] = sorted(group["failure_time"].tolist())

    will_fail = np.zeros(len(feature_df), dtype=int)
    time_to_failure_min = np.full(len(feature_df), float("inf"))
    failure_prob = np.zeros(len(feature_df))

    # Fast group-wise lookup
    for device_id, group in feature_df.groupby("device_id"):
        device_failures = failures_by_device.get(device_id, [])
        if not device_failures:
            continue

        indices = group.index
        timestamps = group["timestamp"].values

        for f_time in device_failures:
            f_time_np = np.datetime64(f_time)
            # Time difference in minutes
            time_diff = (f_time_np - timestamps) / np.timedelta64(1, "m")
            # Only future failures that occur sooner than any previously found
            valid_mask = (time_diff > 0) & (time_diff < time_to_failure_min[indices])
            time_to_failure_min[indices[valid_mask]] = time_diff[valid_mask]

    # Compute binary labels and failure probability
    will_fail_mask = time_to_failure_min <= horizon_minutes
    will_fail[will_fail_mask] = 1
    failure_prob[will_fail_mask] = 1.0 - (time_to_failure_min[will_fail_mask] / horizon_minutes)
    failure_prob = np.clip(failure_prob, 0.0, 1.0)

    labels_df = pd.DataFrame({
        "will_fail": will_fail,
        "time_to_failure_min": time_to_failure_min,
        "failure_prob": failure_prob,
    })

    result = pd.concat([feature_df.reset_index(drop=True), labels_df], axis=1)
    return result


if __name__ == "__main__":
    print("Loading SNMP data from SQLite...")
    df = load_snmp_data()
    print(f"  Loaded {len(df)} rows")

    print("Computing rolling features...")
    features = compute_rolling_features(df)
    print(f"  Feature matrix shape: {features.shape}")
    print(f"  Feature columns: {[c for c in features.columns if c not in ('timestamp', 'device_id')][:10]}...")

    print("Creating training labels...")
    failures = load_failure_events()
    labeled = create_training_labels(features, failures)
    pos = labeled["will_fail"].sum()
    neg = len(labeled) - pos
    print(f"  Labels: {pos} positive (approaching failure), {neg} negative")
