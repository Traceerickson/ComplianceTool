from __future__ import annotations

import json
import os
import random
from collections import Counter
from typing import Any, Dict, List, Tuple

import numpy as np

from lessons.search import LessonsStore, ingest_lessons
from utils.embeddings import deterministic_embedding
from utils.logger import get_logger

logger = get_logger(__name__)


def _tokenize(text: str) -> List[str]:
    toks = [t.lower() for t in text.replace("/", " ").replace("-", " ").split()]
    stop = set(["the", "and", "of", "in", "to", "a", "for", "on", "with", "per", "mm", "inch", "owner:"])
    return [t.strip(".,:;()[]{}") for t in toks if t not in stop and len(t) > 2]


def _kmeans(X: np.ndarray, k: int, max_iter: int = 50) -> Tuple[np.ndarray, np.ndarray]:
    n, d = X.shape
    rng = np.random.default_rng(42)
    centroids = X[rng.choice(n, size=min(k, n), replace=False)]
    labels = np.zeros(n, dtype=int)
    for _ in range(max_iter):
        # Assign
        dists = np.linalg.norm(X[:, None, :] - centroids[None, :, :], axis=2)
        labels = np.argmin(dists, axis=1)
        # Update
        new_centroids = np.array([X[labels == i].mean(axis=0) if np.any(labels == i) else centroids[i] for i in range(centroids.shape[0])])
        if np.allclose(new_centroids, centroids):
            break
        centroids = new_centroids
    return labels, centroids


def compute_clusters(num_clusters: int = 5, out_path: str = "storage/lessons_clusters.json") -> Dict[str, Any]:
    store = LessonsStore()
    if not store.ncr and not store.capa:
        store = ingest_lessons()
    # Build vectors for NCR text
    texts: List[str] = []
    ids: List[str] = []
    for n in store.ncr.values():
        t = " \n".join([x for x in [n.defect, n.description, n.outcome] if x])
        if not t:
            continue
        texts.append(t)
        ids.append(n.id)
    if not texts:
        data = {"clusters": []}
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        json.dump(data, open(out_path, "w", encoding="utf-8"), indent=2)
        return data
    X = np.stack([deterministic_embedding(t, dim=384) for t in texts], axis=0)
    k = min(num_clusters, len(texts))
    labels, _ = _kmeans(X, k=k)

    # Keywords per cluster
    clusters: Dict[int, Dict[str, Any]] = {i: {"ids": [], "keywords": []} for i in range(k)}
    for idx, cid in enumerate(labels):
        clusters[cid]["ids"].append(ids[idx])
    for cid, info in clusters.items():
        toks = []
        for nid in info["ids"]:
            n = store.ncr.get(nid)
            if not n:
                continue
            toks.extend(_tokenize(" ".join([x for x in [n.defect, n.description, n.outcome] if x])))
        common = [w for w, c in Counter(toks).most_common(5)]
        info["keywords"] = common

    data = {
        "clusters": [
            {"id": i, "count": len(info["ids"]), "ncr_ids": info["ids"], "keywords": info["keywords"]}
            for i, info in clusters.items()
        ]
    }
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logger.info("Computed lessons clusters: k=%d", k)
    return data


def get_clusters(out_path: str = "storage/lessons_clusters.json") -> Dict[str, Any]:
    if os.path.exists(out_path):
        return json.load(open(out_path, "r", encoding="utf-8"))
    return compute_clusters()

