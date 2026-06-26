"""
Retriever for RAG Pipeline

Given a query (user question or auto-generated alert context), retrieves
the top-k relevant runbook chunks with MLS access-control filtering.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.utils.config import rag_cfg, mls_cfg, get_path
from src.rag.embedder import embed_query
from src.rag.vector_store import load_index


# MLS classification hierarchy
CLASSIFICATION_HIERARCHY = {
    "UNCLASSIFIED": 0,
    "RESTRICTED": 1,
    "CONFIDENTIAL": 2,
}


def retrieve(
    query: str,
    top_k: Optional[int] = None,
    operator_clearance: Optional[str] = None,
    device_type_filter: Optional[str] = None,
    index_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant runbook chunks for a query.

    Args:
        query: natural language query or alert context
        top_k: number of results to return
        operator_clearance: MLS clearance level of the querying operator
        device_type_filter: optional filter to restrict results to a device type
        index_path: path to the FAISS index

    Returns:
        List of dicts: {text, runbook_id, section, score, classification, ...}
    """
    cfg = rag_cfg()
    mls = mls_cfg()

    if top_k is None:
        top_k = cfg.get("top_k", 5)
    if operator_clearance is None:
        operator_clearance = mls.get("default_operator_clearance", "RESTRICTED")

    min_score = cfg.get("min_retrieval_score", 0.35)

    # Embed the query
    query_embedding = embed_query(query)

    # Load the index
    store = load_index(index_path)

    # Retrieve more than top_k to account for filtering
    raw_results = store.search(query_embedding, top_k=top_k * 3)

    # Filter and rank
    filtered = []
    operator_level = CLASSIFICATION_HIERARCHY.get(operator_clearance, 1)

    for meta, score in raw_results:
        # MLS access control: only show chunks at or below operator's clearance
        chunk_classification = meta.get("classification", "UNCLASSIFIED")
        chunk_level = CLASSIFICATION_HIERARCHY.get(chunk_classification, 0)

        if mls.get("enabled", True) and chunk_level > operator_level:
            # Operator doesn't have clearance for this chunk
            continue

        # Device type filter
        if device_type_filter:
            applicable_devices = meta.get("applicable_devices", [])
            if applicable_devices and device_type_filter.lower() not in [
                d.lower() for d in applicable_devices
            ]:
                continue

        # Score filter
        if score < min_score:
            continue

        result = {
            **meta,
            "score": round(float(score), 4),
            "clearance_required": chunk_classification,
        }
        filtered.append(result)

        if len(filtered) >= top_k:
            break

    return filtered


def format_context_for_llm(
    retrieved_chunks: List[Dict[str, Any]],
    include_citations: bool = True,
) -> str:
    """
    Format retrieved chunks into a context string for LLM prompt injection.
    Includes runbook citations for grounded answers.
    """
    if not retrieved_chunks:
        return "No relevant runbook content found for this query."

    context_parts = []
    for i, chunk in enumerate(retrieved_chunks, 1):
        runbook_id = chunk.get("runbook_id", "UNKNOWN")
        section = chunk.get("section", "")
        classification = chunk.get("classification", "UNCLASSIFIED")
        text = chunk.get("text", "")

        header = f"[Source {i}: {runbook_id}"
        if section:
            header += f" — {section}"
        header += f" | Classification: {classification}]"

        context_parts.append(f"{header}\n{text}")

    return "\n\n---\n\n".join(context_parts)


def build_alert_query(alert: Dict[str, Any]) -> str:
    """
    Convert a predictive alert into a natural language query for retrieval.
    This bridges the analytics → RAG pipeline.
    """
    device_id = alert.get("device_id", "unknown device")
    risk_level = alert.get("risk_level", "unknown")
    failure_prob = alert.get("failure_probability", alert.get("max_failure_prob", 0))
    contributing = alert.get("contributing_metrics", [])
    fault_type = alert.get("fault_type", "")

    query_parts = [
        f"Device {device_id} has {risk_level} risk of failure",
        f"with {failure_prob:.0%} probability.",
    ]

    if contributing:
        metrics_str = ", ".join(contributing) if isinstance(contributing, list) else str(contributing)
        query_parts.append(f"Contributing metrics: {metrics_str}.")

    if fault_type:
        query_parts.append(f"Suspected fault type: {fault_type}.")

    query_parts.append("What are the diagnosis and remediation steps?")

    return " ".join(query_parts)


if __name__ == "__main__":
    # Test retrieval
    test_queries = [
        "how to fix high CPU on a router",
        "CRC errors on interface",
        "temperature too high server overheating",
        "memory growing process leak",
        "BGP neighbor down",
    ]

    for q in test_queries:
        print(f"\n🔍 Query: {q}")
        results = retrieve(q, top_k=3)
        for r in results:
            print(f"   [{r['score']:.4f}] {r['runbook_id']} — {r.get('section', '')[:50]} [{r['clearance_required']}]")

        context = format_context_for_llm(results)
        print(f"   Context length: {len(context)} chars")
