from __future__ import annotations

from typing import Dict, List

from storage.vector_store import VectorStore
from utils.embeddings import deterministic_embedding
from utils.logger import get_logger

logger = get_logger(__name__)


class SearchEngine:
    def __init__(self, dim: int = 384):
        self.vstore = VectorStore(dim=dim)

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        q_emb = deterministic_embedding(query, dim=self.vstore.dim)
        results = self.vstore.search(q_emb, top_k=top_k)
        payload: List[Dict] = []
        for score, rec in results:
            payload.append(
                {
                    "score": score,
                    "text": rec.text,
                    "citation": {
                        "filename": rec.filename,
                        "page_number": rec.page_number,
                        "line_start": rec.line_start,
                        "line_end": rec.line_end,
                    },
                }
            )
        logger.info("Search query='%s' top_k=%d results=%d", query, top_k, len(payload))
        return payload

