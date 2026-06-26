"""
Forecasting Models for Predictive Failure Analysis

Two-stage approach:
  1. RandomForest / XGBoost classifier: predicts failure probability within horizon
  2. Complementary ARIMA baseline for per-metric trend extrapolation

Outputs: {device_id, predicted_failure_prob, eta_window, contributing_metrics}
"""

import json
import sqlite3
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    classification_report,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler
import joblib

from src.utils.config import analytics_cfg, get_path


FEATURE_EXCLUDE_COLS = {"timestamp", "device_id", "will_fail", "time_to_failure_min", "failure_prob"}


def _get_feature_columns(df: pd.DataFrame) -> List[str]:
    """Get all feature columns (excluding metadata and labels)."""
    return [c for c in df.columns if c not in FEATURE_EXCLUDE_COLS]


def train_failure_classifier(
    labeled_df: pd.DataFrame,
    model_type: Optional[str] = None,
    save_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Train a failure prediction classifier.

    Args:
        labeled_df: DataFrame with features + will_fail label
        model_type: 'random_forest' or 'xgboost'
        save_path: where to save the trained model

    Returns:
        Dict with model, scaler, metrics, feature_importances
    """
    cfg = analytics_cfg()
    if model_type is None:
        model_type = cfg.get("model_type", "random_forest")
    if save_path is None:
        save_path = get_path("paths.store_dir") / "forecast_model.pkl"

    feature_cols = _get_feature_columns(labeled_df)
    X = labeled_df[feature_cols].fillna(0).values
    y = labeled_df["will_fail"].values

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42, stratify=y if y.sum() > 1 else None
    )

    # Train
    if model_type == "xgboost":
        try:
            from xgboost import XGBClassifier
            model = XGBClassifier(
                n_estimators=200,
                max_depth=6,
                learning_rate=0.1,
                random_state=42,
                use_label_encoder=False,
                eval_metric="logloss",
            )
        except ImportError:
            print("⚠️  XGBoost not available, falling back to RandomForest")
            model_type = "random_forest"

    if model_type == "random_forest":
        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=8,
            min_samples_leaf=5,
            random_state=42,
            class_weight="balanced",
            n_jobs=-1,
        )

    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1] if hasattr(model, "predict_proba") else y_pred.astype(float)

    precision, recall, f1, _ = precision_recall_fscore_support(y_test, y_pred, average="binary", zero_division=0)

    try:
        auc = roc_auc_score(y_test, y_prob)
    except ValueError:
        auc = 0.0

    metrics = {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "auc_roc": round(auc, 4),
        "test_samples": len(y_test),
        "positive_ratio": round(y.mean(), 4),
    }

    # Feature importances
    importances = {}
    if hasattr(model, "feature_importances_"):
        for col, imp in zip(feature_cols, model.feature_importances_):
            importances[col] = round(float(imp), 6)
        importances = dict(sorted(importances.items(), key=lambda x: -x[1]))

    # Save model + scaler
    save_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "model": model,
        "scaler": scaler,
        "feature_columns": feature_cols,
        "model_type": model_type,
        "metrics": metrics,
    }
    joblib.dump(artifact, save_path)

    return {
        "model": model,
        "scaler": scaler,
        "feature_columns": feature_cols,
        "metrics": metrics,
        "feature_importances": dict(list(importances.items())[:20]),  # top 20
    }


def load_trained_model(model_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load a previously trained model."""
    if model_path is None:
        model_path = get_path("paths.store_dir") / "forecast_model.pkl"
    return joblib.load(model_path)


def predict_failures(
    feature_df: pd.DataFrame,
    model_artifact: Optional[Dict[str, Any]] = None,
    threshold: Optional[float] = None,
) -> pd.DataFrame:
    """
    Run failure predictions on new/live feature data.

    Returns DataFrame with columns:
      device_id, timestamp, failure_prob, will_fail_pred, contributing_metrics
    """
    cfg = analytics_cfg()
    if threshold is None:
        threshold = cfg.get("failure_probability_threshold", 0.65)

    if model_artifact is None:
        model_artifact = load_trained_model()

    model = model_artifact["model"]
    scaler = model_artifact["scaler"]
    feature_cols = model_artifact["feature_columns"]

    # Ensure all feature columns exist
    for col in feature_cols:
        if col not in feature_df.columns:
            feature_df[col] = 0.0

    X = feature_df[feature_cols].fillna(0).values
    X_scaled = scaler.transform(X)

    # Predict probabilities
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(X_scaled)[:, 1]
    else:
        probs = model.predict(X_scaled).astype(float)

    results = feature_df[["timestamp", "device_id"]].copy()
    results["failure_prob"] = probs
    results["will_fail_pred"] = (probs >= threshold).astype(int)

    # Identify contributing metrics (which features have highest value × importance)
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        contributing = []
        for i in range(len(X_scaled)):
            # Weighted feature contribution
            contributions = np.abs(X_scaled[i]) * importances
            top_indices = np.argsort(contributions)[-5:][::-1]
            top_features = [feature_cols[j] for j in top_indices]
            # Extract base metric names
            base_metrics = set()
            for f in top_features:
                parts = f.split("_w")
                if len(parts) > 1:
                    base_metrics.add(parts[0])
                else:
                    base_metrics.add(f.replace("_current", ""))
            contributing.append(list(base_metrics)[:3])
        results["contributing_metrics"] = contributing
    else:
        results["contributing_metrics"] = [[] for _ in range(len(results))]

    return results


def get_device_risk_summary(predictions: pd.DataFrame) -> List[Dict[str, Any]]:
    """
    Aggregate predictions to get a per-device risk summary.
    Returns list of {device_id, max_failure_prob, avg_failure_prob, risk_level, contributing_metrics}
    """
    summaries = []
    for device_id, group in predictions.groupby("device_id"):
        max_prob = group["failure_prob"].max()
        avg_prob = group["failure_prob"].mean()
        latest = group.sort_values("timestamp").iloc[-1]

        if max_prob >= 0.8:
            risk_level = "CRITICAL"
        elif max_prob >= 0.6:
            risk_level = "HIGH"
        elif max_prob >= 0.4:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        summaries.append({
            "device_id": device_id,
            "max_failure_prob": round(float(max_prob), 4),
            "avg_failure_prob": round(float(avg_prob), 4),
            "latest_failure_prob": round(float(latest["failure_prob"]), 4),
            "risk_level": risk_level,
            "contributing_metrics": latest.get("contributing_metrics", []),
            "predicted_failure": bool(max_prob >= 0.65),
        })

    summaries.sort(key=lambda x: -x["max_failure_prob"])
    return summaries


if __name__ == "__main__":
    from src.analytics.feature_engineering import load_snmp_data, load_failure_events, compute_rolling_features, create_training_labels

    print("Loading data and computing features...")
    snmp = load_snmp_data()
    features = compute_rolling_features(snmp)
    failures = load_failure_events()
    labeled = create_training_labels(features, failures)

    print(f"Training classifier on {len(labeled)} samples...")
    result = train_failure_classifier(labeled)
    print(f"✅ Model trained — Metrics: {result['metrics']}")
    print(f"   Top features: {list(result['feature_importances'].keys())[:5]}")

    print("Running predictions...")
    preds = predict_failures(features, result)
    summary = get_device_risk_summary(preds)
    print(f"✅ Risk Summary:")
    for s in summary[:5]:
        print(f"   {s['device_id']}: {s['risk_level']} (prob={s['max_failure_prob']:.2f})")
