"""
Vector Store for RAG Pipeline

FAISS-based vector index with persistent disk storage.
Falls back to brute-force numpy cosine similarity if FAISS is unavailable.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from src.utils.config import rag_cfg, get_path


class NumpyVectorStore:
    """Fallback vector store using numpy brute-force search."""

    def __init__(self):
        self.embeddings: Optional[np.ndarray] = None
        self.metadata: List[Dict[str, Any]] = []

    def add(self, embeddings: np.ndarray, metadata: List[Dict[str, Any]]):
        if self.embeddings is None:
            self.embeddings = embeddings
        else:
            self.embeddings = np.vstack([self.embeddings, embeddings])
        self.metadata.extend(metadata)

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Tuple[Dict, float]]:
        if self.embeddings is None or len(self.embeddings) == 0:
            return []

        # Cosine similarity
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)
        emb_norms = self.embeddings / (np.linalg.norm(self.embeddings, axis=1, keepdims=True) + 1e-10)
        scores = np.dot(emb_norms, query_norm)

        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            results.append((self.metadata[idx], float(scores[idx])))
        return results

    def save(self, path: Path):
        path.mkdir(parents=True, exist_ok=True)
        np.save(path / "embeddings.npy", self.embeddings)
        with open(path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2)

    def load(self, path: Path):
        self.embeddings = np.load(path / "embeddings.npy")
        with open(path / "metadata.json", "r", encoding="utf-8") as f:
            self.metadata = json.load(f)


class FAISSVectorStore:
    """FAISS-based vector store with L2 index."""

    def __init__(self, dim: int = 384):
        import faiss
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)  # Inner Product (cosine sim for normalized vectors)
        self.metadata: List[Dict[str, Any]] = []

    def add(self, embeddings: np.ndarray, metadata: List[Dict[str, Any]]):
        # Normalize for cosine similarity via inner product
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        normalized = embeddings / (norms + 1e-10)
        self.index.add(normalized.astype(np.float32))
        self.metadata.extend(metadata)

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Tuple[Dict, float]]:
        # Normalize query
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-10)
        query_norm = query_norm.reshape(1, -1).astype(np.float32)

        scores, indices = self.index.search(query_norm, top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self.metadata):
                results.append((self.metadata[idx], float(score)))
        return results

    def save(self, path: Path):
        import faiss
        path.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(path / "faiss.index"))
        with open(path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2)

    def load(self, path: Path):
        import faiss
        self.index = faiss.read_index(str(path / "faiss.index"))
        with open(path / "metadata.json", "r", encoding="utf-8") as f:
            self.metadata = json.load(f)


def create_vector_store(dim: int = 384):
    """Create a vector store, preferring FAISS, falling back to numpy."""
    try:
        import faiss
        print("✅ Using FAISS vector store")
        return FAISSVectorStore(dim=dim)
    except ImportError:
        print("⚠️  FAISS not available, using numpy fallback vector store")
        return NumpyVectorStore()


def build_index(
    chunks: List[Dict[str, Any]],
    index_path: Optional[Path] = None,
):
    """
    Build a vector index from embedded chunks.
    Chunks must have 'embedding' field (numpy array).
    """
    if index_path is None:
        index_path = get_path("paths.faiss_index")

    if not chunks:
        raise ValueError("No chunks to index")

    dim = len(chunks[0]["embedding"])
    store = create_vector_store(dim=dim)

    embeddings = np.array([c["embedding"] for c in chunks], dtype=np.float32)
    metadata = [{k: v for k, v in c.items() if k != "embedding"} for c in chunks]

    store.add(embeddings, metadata)
    store.save(index_path)

    print(f"✅ Built vector index with {len(chunks)} chunks → {index_path}")
    return store


def load_index(index_path: Optional[Path] = None):
    """Load a previously built vector index."""
    if index_path is None:
        index_path = get_path("paths.faiss_index")

    try:
        import faiss
        store = FAISSVectorStore()
    except ImportError:
        store = NumpyVectorStore()

    store.load(index_path)
    return store


if __name__ == "__main__":
    from src.rag.chunker import chunk_all_runbooks
    from src.rag.embedder import embed_chunks

    chunks = chunk_all_runbooks()
    embedded = embed_chunks(chunks)
    store = build_index(embedded)

    # Test search
    from src.rag.embedder import embed_query
    query_emb = embed_query("how to fix high CPU on a router")
    results = store.search(query_emb, top_k=3)
    print(f"\n🔍 Test query: 'how to fix high CPU on a router'")
    for meta, score in results:
        print(f"   [{score:.4f}] {meta['runbook_id']} — {meta['section'][:60]}")
