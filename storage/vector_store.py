from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class VectorRecord:
    id: int
    doc_id: str
    filename: str
    page_number: int
    line_start: int
    line_end: int
    text_hash: str
    text: str


class VectorStore:
    """
    Simple vector store backed by FAISS if available, else NumPy fallback.

    Persists index and metadata under `storage/` directory.
    """

    def __init__(self, dim: int = 384, storage_dir: str = "storage"):
        self.dim = dim
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.index_path = os.path.join(self.storage_dir, "index.faiss")
        self.meta_path = os.path.join(self.storage_dir, "meta.json")
        self.fallback_index_path = os.path.join(self.storage_dir, "index.npy")

        self.use_faiss = False
        self.index = None
        self.embeddings: Optional[np.ndarray] = None  # fallback
        self.metadata: List[VectorRecord] = []

        self._init_index()
        self._load_metadata()

    def _init_index(self):
        try:
            import faiss  # type: ignore

            self.use_faiss = True
            if os.path.exists(self.index_path):
                self.index = faiss.read_index(self.index_path)
                logger.info("Loaded FAISS index from %s", self.index_path)
            else:
                self.index = faiss.IndexFlatIP(self.dim)
                logger.info("Initialized new FAISS index (dim=%d)", self.dim)
        except Exception as e:  # pragma: no cover - depends on env
            self.use_faiss = False
            if os.path.exists(self.fallback_index_path):
                self.embeddings = np.load(self.fallback_index_path)
                logger.info("Loaded fallback NumPy index from %s", self.fallback_index_path)
            else:
                self.embeddings = np.zeros((0, self.dim), dtype=np.float32)
                logger.info("Initialized new NumPy fallback index (dim=%d)", self.dim)

    def _load_metadata(self):
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.metadata = [VectorRecord(**rec) for rec in data.get("records", [])]
            except Exception as e:
                logger.exception("Failed to load metadata: %s", e)
                self.metadata = []
        else:
            self.metadata = []

    def _save_metadata(self):
        data = {"records": [asdict(m) for m in self.metadata]}
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _persist_index(self):
        if self.use_faiss:
            try:
                import faiss  # type: ignore

                faiss.write_index(self.index, self.index_path)
            except Exception as e:  # pragma: no cover - env dependent
                logger.exception("Failed to save FAISS index: %s", e)
        else:
            np.save(self.fallback_index_path, self.embeddings)

    def add(self, embeddings: np.ndarray, metadatas: List[Dict[str, Any]]):
        assert embeddings.shape[1] == self.dim
        if self.use_faiss:
            self.index.add(embeddings)
        else:
            self.embeddings = (
                embeddings
                if self.embeddings is None or len(self.embeddings) == 0
                else np.vstack([self.embeddings, embeddings])
            )

        start_id = len(self.metadata)
        for i, meta in enumerate(metadatas):
            rec = VectorRecord(
                id=start_id + i,
                doc_id=str(meta.get("doc_id")),
                filename=str(meta.get("filename")),
                page_number=int(meta.get("page_number", 1)),
                line_start=int(meta.get("line_start", 1)),
                line_end=int(meta.get("line_end", 1)),
                text_hash=str(meta.get("text_hash")),
                text=str(meta.get("text", "")),
            )
            self.metadata.append(rec)

        self._persist_index()
        self._save_metadata()

    def search(self, query_embedding: np.ndarray, top_k: int = 5) -> List[Tuple[float, VectorRecord]]:
        if self.use_faiss:
            import faiss  # type: ignore

            query_embedding = query_embedding.astype(np.float32)
            D, I = self.index.search(query_embedding.reshape(1, -1), top_k)
            scores = D[0].tolist()
            indices = I[0].tolist()
        else:
            if self.embeddings is None or len(self.embeddings) == 0:
                return []
            # cosine = dot since vectors normalized
            sims = np.dot(self.embeddings, query_embedding.astype(np.float32))
            top_indices = np.argsort(-sims)[:top_k]
            scores = sims[top_indices].tolist()
            indices = top_indices.tolist()

        results: List[Tuple[float, VectorRecord]] = []
        for score, idx in zip(scores, indices):
            if idx is None or idx < 0 or idx >= len(self.metadata):
                continue
            results.append((float(score), self.metadata[idx]))
        return results

