from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from storage.vector_store import VectorStore
from utils.embeddings import deterministic_embedding
from utils.hashing import sha256_hex
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EvidenceRef:
    doc_id: Optional[str]
    filename: str
    page: int
    line: Optional[int] = None
    excerpt: Optional[str] = None


@dataclass
class NCRRecord:
    id: str
    part_number: Optional[str]
    defect: Optional[str]
    description: Optional[str]
    date: Optional[str]
    owner: Optional[str]
    outcome: Optional[str]
    cycle_time: Optional[int]
    evidence_refs: List[EvidenceRef]


@dataclass
class CAPARecord:
    id: str
    ncr_id: str
    root_cause: Optional[str]
    corrective_action: Optional[str]
    containment: Optional[str]
    verification: Optional[str]
    owner: Optional[str]
    completed_at: Optional[str]


class LessonsStore:
    """JSON-backed store for NCR/CAPA records."""

    def __init__(self, path: str = "storage/lessons_store.json"):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        self.ncr: Dict[str, NCRRecord] = {}
        self.capa: Dict[str, CAPARecord] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                data = json.load(open(self.path, "r", encoding="utf-8"))
                self.ncr = {k: NCRRecord(**v) for k, v in data.get("ncr", {}).items()}
                self.capa = {k: CAPARecord(**v) for k, v in data.get("capa", {}).items()}
            except Exception:
                logger.exception("Failed to load lessons store")

    def save(self):
        data = {
            "ncr": {k: asdict(v) for k, v in self.ncr.items()},
            "capa": {k: asdict(v) for k, v in self.capa.items()},
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def _load_json_dir(path: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return rows
    for fn in os.listdir(path):
        if not fn.lower().endswith(".json"):
            continue
        try:
            with open(os.path.join(path, fn), "r", encoding="utf-8") as f:
                rows.append(json.load(f))
        except Exception:
            logger.exception("Failed to load %s", fn)
    return rows


def _to_ncr(rec: Dict[str, Any]) -> NCRRecord:
    e_refs = [EvidenceRef(**e) for e in rec.get("evidence_refs", [])]
    return NCRRecord(
        id=str(rec.get("id")),
        part_number=rec.get("part_number"),
        defect=rec.get("defect"),
        description=rec.get("description"),
        date=rec.get("date"),
        owner=rec.get("owner"),
        outcome=rec.get("outcome"),
        cycle_time=rec.get("cycle_time"),
        evidence_refs=e_refs,
    )


def _to_capa(rec: Dict[str, Any]) -> CAPARecord:
    return CAPARecord(
        id=str(rec.get("id")),
        ncr_id=str(rec.get("ncr_id")),
        root_cause=rec.get("root_cause"),
        corrective_action=rec.get("corrective_action"),
        containment=rec.get("containment"),
        verification=rec.get("verification"),
        owner=rec.get("owner"),
        completed_at=rec.get("completed_at"),
    )


def ingest_lessons(ncr_dir: str = "data/ncr", capa_dir: str = "data/capa") -> LessonsStore:
    os.makedirs(ncr_dir, exist_ok=True)
    os.makedirs(capa_dir, exist_ok=True)
    store = LessonsStore()
    # Load JSON files
    for rec in _load_json_dir(ncr_dir):
        n = _to_ncr(rec)
        store.ncr[n.id] = n
    for rec in _load_json_dir(capa_dir):
        c = _to_capa(rec)
        store.capa[c.id] = c
    store.save()

    # Index into vector store
    vstore = VectorStore()
    texts: List[str] = []
    metas: List[Dict[str, Any]] = []
    for ncr in store.ncr.values():
        text = " \n".join(
            t for t in [ncr.defect, ncr.description, ncr.outcome, f"owner: {ncr.owner}"] if t
        )
        if not text:
            continue
        texts.append(text)
        metas.append(
            {
                "doc_id": f"ncr:{ncr.id}",
                "filename": f"NCR_{ncr.id}.json",
                "page_number": 1,
                "line_start": 1,
                "line_end": 1,
                "text_hash": sha256_hex(text),
                "text": text,
            }
        )
    for capa in store.capa.values():
        text = " \n".join(
            t for t in [capa.root_cause, capa.corrective_action, capa.containment, capa.verification] if t
        )
        if not text:
            continue
        texts.append(text)
        metas.append(
            {
                "doc_id": f"capa:{capa.id}",
                "filename": f"CAPA_{capa.id}.json",
                "page_number": 1,
                "line_start": 1,
                "line_end": 1,
                "text_hash": sha256_hex(text),
                "text": text,
            }
        )
    if texts:
        from utils.embeddings import batch_embeddings

        embs = batch_embeddings(texts, dim=vstore.dim)
        vstore.add(embs, metas)
        logger.info("Indexed lessons: %d items", len(texts))
    return store


def search_lessons(query: str, top_k: int = 10) -> List[Dict[str, Any]]:
    store = LessonsStore()
    vstore = VectorStore()
    q = deterministic_embedding(query, dim=vstore.dim)
    raw = vstore.search(q, top_k=top_k * 4)
    results: List[Dict[str, Any]] = []
    seen_ncr = set()

    # Helper: fetch CAPA by NCR
    capa_by_ncr: Dict[str, CAPARecord] = {}
    for c in store.capa.values():
        capa_by_ncr.setdefault(c.ncr_id, c)

    for score, rec in raw:
        if not (rec.doc_id.startswith("ncr:") or rec.doc_id.startswith("capa:")):
            continue
        ncr_id: Optional[str] = None
        if rec.doc_id.startswith("ncr:"):
            ncr_id = rec.doc_id.split(":", 1)[1]
        else:
            # Map CAPA -> NCR for dedupe
            capa_id = rec.doc_id.split(":", 1)[1]
            capa = store.capa.get(capa_id)
            ncr_id = capa.ncr_id if capa else None
        if not ncr_id or ncr_id in seen_ncr:
            continue
        seen_ncr.add(ncr_id)
        n = store.ncr.get(ncr_id)
        c = capa_by_ncr.get(ncr_id)
        if not n:
            continue
        citations: List[Dict[str, Any]] = []
        for e in n.evidence_refs or []:
            citations.append(
                {
                    "filename": e.filename,
                    "page": e.page,
                    "line": e.line,
                    "doc_id": e.doc_id,
                }
            )
        if not citations:
            citations.append(
                {
                    "filename": rec.filename,
                    "page": rec.page_number,
                    "line": rec.line_start,
                    "doc_id": rec.doc_id,
                }
            )
        results.append(
            {
                "ncr_id": n.id,
                "defect": n.defect,
                "corrective_action": c.corrective_action if c else None,
                "outcome": n.outcome,
                "cycle_time_days": n.cycle_time,
                "owner": n.owner,
                "citations": citations,
            }
        )
        if len(results) >= top_k:
            break
    logger.info("Lessons search query='%s' results=%d", query, len(results))
    return results

