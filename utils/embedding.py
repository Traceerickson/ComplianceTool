import hashlib
import random
from typing import List

EMBED_DIM = 64


def embed_text(text: str) -> List[float]:
    """Return deterministic embedding vector for text."""
    seed = int(hashlib.sha256(text.encode('utf-8')).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    vec = [rng.random() for _ in range(EMBED_DIM)]
    norm = sum(x * x for x in vec) ** 0.5
    if norm:
        vec = [x / norm for x in vec]
    return vec
