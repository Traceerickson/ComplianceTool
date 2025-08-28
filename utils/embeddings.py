from __future__ import annotations

import math
import random
from typing import Iterable, List

import numpy as np

from utils.hashing import sha256_hex


def deterministic_embedding(text: str, dim: int = 384) -> np.ndarray:
    """
    Produce a deterministic pseudo-embedding for text using a hash-seeded RNG.
    This is a stub to avoid external model dependencies while enabling testing.
    """
    seed_hex = sha256_hex(text)[:16]
    seed_int = int(seed_hex, 16) % (2**32)
    rng = random.Random(seed_int)
    vec = np.array([rng.uniform(-1.0, 1.0) for _ in range(dim)], dtype=np.float32)
    # Normalize to unit length for cosine similarity
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def batch_embeddings(texts: Iterable[str], dim: int = 384) -> np.ndarray:
    arr = np.stack([deterministic_embedding(t, dim=dim) for t in texts], axis=0)
    return arr.astype(np.float32)

