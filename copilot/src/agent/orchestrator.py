"""
Orchestrator — Main Pipeline Controller

Rule-based orchestration (NOT a heavy agent framework):
1. Poll latest simulated metrics
2. Run forecasting engine → get failure probabilities
3. If prob > threshold → auto-trigger RAG retrieval → generate proactive alert with explanation
4. Handle on-demand operator chat queries (same RAG+LLM pipeline, but reactive)
5. Log all alerts and interactions

This is deliberately simple and debuggable — a strength, not a weakness.
"""

import json
import time
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import numpy as np

from src.utils.config import (
    analytics_cfg, get_path, ensure_dirs,
    simulator_cfg, mls_cfg,
)


class CoPilotOrchestrator:
    """
    Main orchestration engine for the predictive co-pilot.

    Pipeline:
      metrics → features → forecast → correlate → retrieve → explain → alert
    """

    def __init__(self):
        self.alerts: List[Dict[str, Any]] = []
        self.chat_history: List[Dict[str, Any]] = []
        self.model_artifact: Optional[Dict] = None
        self.vector_store = None
        self._initialized = False

    def initialize(self):
        """
        Full initialization pipeline:
        1. Generate/load topology + simulated data
        2. Train forecasting model
        3. Build RAG index
        """
        ensure_dirs()
        print("=" * 60)
        print("🚀 INITIALIZING CO-PILOT SYSTEM")
        print("=" * 60)

        # ── Step 1: Generate Topology ──
        print("\n📡 Step 1/5: Generating network topology...")
        from src.ingestion.topology_sim import generate_topology, save_topology
        self.graph, self.devices = generate_topology()
        save_topology(self.graph, self.devices)
        print(f"   ✅ {len(self.devices)} devices, {self.graph.number_of_edges()} links")

        # ── Step 2: Generate Simulated Data ──
        print("\n📊 Step 2/5: Generating simulated telemetry data...")
        from src.ingestion.snmp_sim import (
            plan_failure_events, generate_snmp_data,
            save_snmp_to_sqlite, save_failure_events,
        )
        from src.ingestion.syslog_sim import generate_syslog_data, save_syslog_to_sqlite

        device_ids = list(self.devices.keys())
        self.start_time = datetime.now() - timedelta(hours=24)

        self.failure_events = plan_failure_events(device_ids, self.start_time, 24)
        print(f"   Planned {len(self.failure_events)} failure events")

        # Generate with 1-minute intervals for manageable data size
        snmp_df = generate_snmp_data(
            device_ids, self.failure_events,
            start_time=self.start_time, duration_hours=24,
            interval_seconds=60,
        )
        save_snmp_to_sqlite(snmp_df)
        save_failure_events(self.failure_events)
        print(f"   ✅ {len(snmp_df)} SNMP metrics + failure events → SQLite")

        syslog_df = generate_syslog_data(
            self.devices, self.failure_events,
            start_time=self.start_time, duration_hours=24,
        )
        save_syslog_to_sqlite(syslog_df)
        self.syslog_df = syslog_df
        print(f"   ✅ {len(syslog_df)} syslog entries → SQLite")

        # ── Step 3: Train Forecasting Model ──
        print("\n🤖 Step 3/5: Training predictive model...")
        from src.analytics.feature_engineering import (
            load_snmp_data, load_failure_events,
            compute_rolling_features, create_training_labels,
        )
        from src.analytics.forecast_models import train_failure_classifier

        snmp_data = load_snmp_data()
        features = compute_rolling_features(snmp_data)
        failures = load_failure_events()
        labeled = create_training_labels(features, failures)

        result = train_failure_classifier(labeled)
        self.model_artifact = result
        print(f"   ✅ Model trained — F1: {result['metrics']['f1_score']:.4f}, "
              f"AUC: {result['metrics']['auc_roc']:.4f}")

        # Store features for dashboard use
        self.features_df = features
        self.labeled_df = labeled

        # ── Step 4: Build RAG Index ──
        print("\n📚 Step 4/5: Building knowledge base index...")
        from src.rag.chunker import chunk_all_runbooks
        from src.rag.embedder import embed_chunks
        from src.rag.vector_store import build_index

        chunks = chunk_all_runbooks()
        embedded = embed_chunks(chunks)
        self.vector_store = build_index(embedded)
        print(f"   ✅ Indexed {len(chunks)} runbook chunks")

        # ── Step 5: Run Predictions ──
        print("\n🔮 Step 5/5: Running predictive analysis...")
        self._run_predictions()

        self._initialized = True
        print("\n" + "=" * 60)
        print("✅ CO-PILOT SYSTEM READY")
        print("=" * 60)

    def _run_predictions(self):
        """Run the full prediction + correlation pipeline."""
        from src.analytics.forecast_models import predict_failures, get_device_risk_summary
        from src.analytics.anomaly_correlator import correlate_anomalies, get_anomaly_report, load_syslog_data

        # Predict
        predictions = predict_failures(self.features_df, self.model_artifact)

        # Correlate with syslog
        if self.syslog_df is not None:
            predictions = correlate_anomalies(predictions, self.syslog_df)

        self.predictions = predictions
        self.risk_summary = get_device_risk_summary(predictions)

        # Generate alerts for high-risk devices
        self.alerts = []
        for device in self.risk_summary:
            if device["predicted_failure"]:
                alert = self._generate_alert(device)
                self.alerts.append(alert)

        # Update device statuses in topology
        for device in self.risk_summary:
            did = device["device_id"]
            if did in self.devices:
                self.devices[did]["risk_score"] = device["max_failure_prob"]
                if device["risk_level"] == "CRITICAL":
                    self.devices[did]["status"] = "critical"
                elif device["risk_level"] == "HIGH":
                    self.devices[did]["status"] = "warning"
                elif device["risk_level"] == "MEDIUM":
                    self.devices[did]["status"] = "degraded"
                else:
                    self.devices[did]["status"] = "healthy"

        print(f"   ✅ {len(self.alerts)} proactive alerts generated")

    def _generate_alert(self, device_risk: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a proactive alert with RAG-grounded explanation."""
        from src.rag.retriever import retrieve, format_context_for_llm, build_alert_query
        from src.llm.local_llm import generate_response

        # Build query from alert context
        query = build_alert_query(device_risk)

        # Retrieve relevant runbooks
        chunks = retrieve(query, top_k=3)
        context = format_context_for_llm(chunks)

        # Generate explanation
        alert_context = (
            f"Device {device_risk['device_id']} — Risk: {device_risk['risk_level']} "
            f"({device_risk['max_failure_prob']:.0%} failure probability). "
            f"Contributing metrics: {device_risk.get('contributing_metrics', [])}"
        )
        response = generate_response(
            question=f"What should I do about the predicted failure on {device_risk['device_id']}?",
            context=context,
            alert_context=alert_context,
        )

        alert = {
            "id": f"ALERT-{len(self.alerts)+1:04d}",
            "timestamp": datetime.now().isoformat(),
            "device_id": device_risk["device_id"],
            "risk_level": device_risk["risk_level"],
            "failure_probability": device_risk["max_failure_prob"],
            "contributing_metrics": device_risk.get("contributing_metrics", []),
            "recommended_runbooks": [c.get("runbook_id", "") for c in chunks],
            "explanation": response["answer"],
            "llm_model": response["model_type"],
            "retrieval_scores": [c.get("score", 0) for c in chunks],
            "status": "active",
        }
        return alert

    def handle_chat(
        self,
        question: str,
        operator_clearance: str = "RESTRICTED",
    ) -> Dict[str, Any]:
        """
        Handle an operator chat query through the RAG+LLM pipeline.
        """
        from src.rag.retriever import retrieve, format_context_for_llm
        from src.llm.local_llm import generate_response

        start = time.time()

        # Retrieve
        chunks = retrieve(
            question,
            top_k=5,
            operator_clearance=operator_clearance,
        )
        context = format_context_for_llm(chunks)

        # Generate response
        response = generate_response(
            question=question,
            context=context,
        )

        result = {
            "question": question,
            "answer": response["answer"],
            "sources": [
                {
                    "runbook_id": c.get("runbook_id", ""),
                    "section": c.get("section", ""),
                    "score": c.get("score", 0),
                    "classification": c.get("classification", ""),
                }
                for c in chunks
            ],
            "model_type": response["model_type"],
            "latency_ms": round((time.time() - start) * 1000, 1),
            "timestamp": datetime.now().isoformat(),
            "operator_clearance": operator_clearance,
        }

        self.chat_history.append(result)
        return result

    def get_topology_data(self) -> Dict[str, Any]:
        """Get topology data for dashboard visualization."""
        if not self._initialized:
            return {"devices": {}, "edges": []}

        edges = [
            {
                "source": u,
                "target": v,
                **data,
            }
            for u, v, data in self.graph.edges(data=True)
        ]

        return {
            "devices": self.devices,
            "edges": edges,
        }

    def get_alerts(self) -> List[Dict[str, Any]]:
        return self.alerts

    def get_risk_summary(self) -> List[Dict[str, Any]]:
        return self.risk_summary if hasattr(self, 'risk_summary') else []

    def get_predictions_df(self) -> pd.DataFrame:
        return self.predictions if hasattr(self, 'predictions') else pd.DataFrame()

    def get_failure_events(self) -> List[Dict[str, Any]]:
        return self.failure_events if hasattr(self, 'failure_events') else []

    def get_model_metrics(self) -> Dict[str, Any]:
        if self.model_artifact:
            return self.model_artifact.get("metrics", {})
        return {}

    def get_feature_importances(self) -> Dict[str, float]:
        if self.model_artifact:
            return self.model_artifact.get("feature_importances", {})
        return {}


# ── Singleton ──
_ORCHESTRATOR: Optional[CoPilotOrchestrator] = None


def get_orchestrator() -> CoPilotOrchestrator:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is None:
        _ORCHESTRATOR = CoPilotOrchestrator()
    return _ORCHESTRATOR


if __name__ == "__main__":
    orch = get_orchestrator()
    orch.initialize()

    # Test chat
    result = orch.handle_chat("How do I fix high CPU on a router?")
    print(f"\n💬 Chat response:")
    print(f"   Model: {result['model_type']}")
    print(f"   Latency: {result['latency_ms']}ms")
    print(f"   Sources: {[s['runbook_id'] for s in result['sources']]}")
    print(f"   Answer: {result['answer'][:200]}...")
