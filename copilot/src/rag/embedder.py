"""
Local Embedder for RAG Pipeline

Uses sentence-transformers (all-MiniLM-L6-v2) to embed document chunks locally.
Falls back to a simple TF-IDF-based embedding if sentence-transformers is not
available (for environments where the model hasn't been downloaded yet).
"""

import json
import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

from src.utils.config import rag_cfg, get_path


_EMBEDDER = None  # cached model instance


class TFIDFEmbedder:
    """
    Fallback embedder using TF-IDF when sentence-transformers is unavailable.
    Produces deterministic, reasonable embeddings without any model download.
    """

    def __init__(self, dim: int = 384):
        self.dim = dim
        self.vocabulary: Dict[str, int] = {}
        self.idf: Optional[np.ndarray] = None
        self._fitted = False

    def fit(self, texts: List[str]):
        """Build vocabulary and compute IDF from corpus."""
        from collections import Counter

        # Build vocabulary from all texts
        all_words: Dict[str, int] = {}
        doc_freq: Dict[str, int] = {}

        for text in texts:
            words = set(self._tokenize(text))
            for word in words:
                doc_freq[word] = doc_freq.get(word, 0) + 1
                if word not in all_words:
                    all_words[word] = len(all_words)

        self.vocabulary = all_words
        n_docs = len(texts)

        # Compute IDF
        self.idf = np.zeros(len(all_words))
        for word, idx in all_words.items():
            self.idf[idx] = np.log((n_docs + 1) / (doc_freq.get(word, 0) + 1)) + 1

        self._fitted = True

    def _tokenize(self, text: str) -> List[str]:
        """Simple whitespace + punctuation tokenizer."""
        import re
        text = text.lower()
        tokens = re.findall(r"\b[a-z0-9]+\b", text)
        return tokens

    def encode(self, texts: Union[str, List[str]], **kwargs) -> np.ndarray:
        """Encode texts to embeddings."""
        if isinstance(texts, str):
            texts = [texts]

        if not self._fitted:
            self.fit(texts)

        embeddings = []
        for text in texts:
            tokens = self._tokenize(text)
            vec = np.zeros(len(self.vocabulary))
            from collections import Counter
            tf = Counter(tokens)
            for word, count in tf.items():
                if word in self.vocabulary:
                    idx = self.vocabulary[word]
                    vec[idx] = count * self.idf[idx]

            # Normalize and project to fixed dimension via hashing
            if np.linalg.norm(vec) > 0:
                vec = vec / np.linalg.norm(vec)

            # Project to target dimension using a deterministic hash-based projection
            if len(vec) > self.dim:
                # Simple dimensionality reduction: take first `dim` components
                projected = vec[:self.dim]
            else:
                projected = np.zeros(self.dim)
                projected[:len(vec)] = vec

            if np.linalg.norm(projected) > 0:
                projected = projected / np.linalg.norm(projected)
            embeddings.append(projected)

        return np.array(embeddings, dtype=np.float32)


def get_embedder():
    """
    Get or create the embedding model.
    Tries sentence-transformers first, falls back to TF-IDF.
    """
    global _EMBEDDER
    if _EMBEDDER is not None:
        return _EMBEDDER

    cfg = rag_cfg()
    model_name = cfg.get("embedding_model_name", "all-MiniLM-L6-v2")
    embeddings_path = get_path("paths.models_dir") / "embeddings"

    try:
        from sentence_transformers import SentenceTransformer

        # Try loading from local cache first
        if embeddings_path.exists() and any(embeddings_path.iterdir()):
            _EMBEDDER = SentenceTransformer(str(embeddings_path))
        else:
            _EMBEDDER = SentenceTransformer(model_name)
            # Save for air-gap use
            embeddings_path.mkdir(parents=True, exist_ok=True)
            _EMBEDDER.save(str(embeddings_path))

        print(f"✅ Loaded sentence-transformers model: {model_name}")
    except (ImportError, Exception) as e:
        print(f"⚠️  sentence-transformers not available ({e}), using TF-IDF fallback")
        _EMBEDDER = TFIDFEmbedder(dim=384)

    return _EMBEDDER


def embed_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Embed all chunks and attach embeddings.
    Returns chunks with an added 'embedding' field (numpy array).
    """
    embedder = get_embedder()
    texts = [chunk["text"] for chunk in chunks]

    # Fit TF-IDF if using fallback
    if isinstance(embedder, TFIDFEmbedder) and not embedder._fitted:
        embedder.fit(texts)

    # Batch encode
    if isinstance(embedder, TFIDFEmbedder):
        embeddings = embedder.encode(texts)
    else:
        embeddings = embedder.encode(texts, show_progress_bar=True, batch_size=32)

    for chunk, embedding in zip(chunks, embeddings):
        chunk["embedding"] = embedding

    return chunks


def embed_query(query: str) -> np.ndarray:
    """Embed a single query string."""
    embedder = get_embedder()
    if isinstance(embedder, TFIDFEmbedder):
        return embedder.encode(query)[0]
    else:
        return embedder.encode([query])[0]


def save_embeddings_cache(
    chunks: List[Dict[str, Any]],
    cache_path: Optional[Path] = None,
):
    """Save embedded chunks to disk for fast loading."""
    if cache_path is None:
        cache_path = get_path("paths.store_dir") / "embeddings_cache.npz"
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    embeddings = np.array([c["embedding"] for c in chunks])
    # Save metadata separately (without numpy arrays)
    metadata = []
    for c in chunks:
        meta = {k: v for k, v in c.items() if k != "embedding"}
        metadata.append(meta)

    np.savez_compressed(
        cache_path,
        embeddings=embeddings,
    )
    # Save metadata as JSON
    meta_path = cache_path.with_suffix(".json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return cache_path


def load_embeddings_cache(
    cache_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Load cached embeddings."""
    if cache_path is None:
        cache_path = get_path("paths.store_dir") / "embeddings_cache.npz"

    data = np.load(cache_path)
    embeddings = data["embeddings"]

    meta_path = cache_path.with_suffix(".json")
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    chunks = []
    for meta, emb in zip(metadata, embeddings):
        meta["embedding"] = emb
        chunks.append(meta)

    return chunks


if __name__ == "__main__":
    from src.rag.chunker import chunk_all_runbooks
    chunks = chunk_all_runbooks()
    print(f"Embedding {len(chunks)} chunks...")
    embedded = embed_chunks(chunks)
    save_embeddings_cache(embedded)
    print(f"✅ Embedded and cached {len(embedded)} chunks")
    print(f"   Embedding dim: {embedded[0]['embedding'].shape}")
