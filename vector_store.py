import json
import os
from typing import List, Dict, Tuple


class VectorStore:
    def __init__(self, dim: int):
        self.dim = dim
        self.vectors: List[List[float]] = []
        self.metadatas: List[Dict] = []

    def add(self, vector: List[float], metadata: Dict) -> None:
        self.vectors.append(vector)
        self.metadatas.append(metadata)

    def search(self, vector: List[float], top_n: int = 5) -> List[Tuple[float, Dict]]:
        results: List[Tuple[float, Dict]] = []
        for v, meta in zip(self.vectors, self.metadatas):
            score = sum(a * b for a, b in zip(v, vector))
            results.append((score, meta))
        results.sort(key=lambda x: x[0], reverse=True)
        return results[:top_n]

    def save(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)
        with open(os.path.join(path, 'vectors.json'), 'w', encoding='utf-8') as f:
            json.dump(self.vectors, f)
        with open(os.path.join(path, 'metadata.json'), 'w', encoding='utf-8') as f:
            json.dump(self.metadatas, f)

    @classmethod
    def load(cls, path: str) -> 'VectorStore':
        with open(os.path.join(path, 'vectors.json'), 'r', encoding='utf-8') as f:
            vectors = json.load(f)
        with open(os.path.join(path, 'metadata.json'), 'r', encoding='utf-8') as f:
            metadatas = json.load(f)
        dim = len(vectors[0]) if vectors else 0
        store = cls(dim)
        store.vectors = vectors
        store.metadatas = metadatas
        return store
