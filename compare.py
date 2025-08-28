from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ingest import extract_revision_from_lines, extract_tolerances_from_lines, Ingestor
from storage.doc_store import DocStore, DocumentInfo
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TolHit:
    value: float
    raw: str
    page: int
    line: int
    context: str


def _norm_tol_str(val: str) -> Optional[float]:
    try:
        return float(val)
    except Exception:
        # Try stripping commas or spaces
        try:
            return float(val.replace(",", "").strip())
        except Exception:
            return None


def extract_revision_for_doc(doc_store: DocStore, doc: DocumentInfo) -> Optional[Tuple[str, int, int]]:
    if doc.revisions:
        rv = doc.revisions[0]
        return rv.value, rv.page_number, rv.line_number
    # Attempt to derive from cache if not set
    pages = doc_store.load_doc_lines(doc.doc_id)
    if not pages:
        return None
    rev = extract_revision_from_lines(pages[0])
    if rev:
        return rev[0], 1, rev[1]
    return None


def extract_tolerances_for_doc(doc_store: DocStore, doc: DocumentInfo) -> List[TolHit]:
    pages = doc_store.load_doc_lines(doc.doc_id) or []
    hits: List[TolHit] = []
    for p_idx, lines in enumerate(pages, start=1):
        tups = extract_tolerances_from_lines(lines)
        for val_str, line_no in tups:
            norm = _norm_tol_str(val_str)
            if norm is None:
                continue
            context = lines[line_no - 1] if 0 <= line_no - 1 < len(lines) else ""
            # Heuristic: ignore unlikely tolerances > 1 (e.g., page counts)
            if norm > 1.0:
                continue
            hits.append(TolHit(value=norm, raw=val_str, page=p_idx, line=line_no, context=context))
    return hits


def compare_documents(filenames: List[str]) -> Dict:
    """
    Compare 2-3 documents for revision and tolerance mismatches.

    Returns a structured report suitable for JSON serialization.
    """
    if len(filenames) < 2:
        raise ValueError("Provide at least two documents to compare")

    ingestor = Ingestor()
    doc_store = ingestor.doc_store

    # Ensure docs are present (ingest if necessary)
    docs: List[DocumentInfo] = []
    for fname in filenames:
        di = doc_store.get_document_by_filename(os.path.basename(fname))
        if not di:
            # Try ingesting from data dir
            path = fname
            if not os.path.exists(path):
                candidate = os.path.join("data", os.path.basename(fname))
                if os.path.exists(candidate):
                    path = candidate
            if not os.path.exists(path):
                raise FileNotFoundError(f"Document not found: {fname}")
            ingestor.ingest_file(path)
            di = doc_store.get_document_by_filename(os.path.basename(path))
        if not di:
            raise RuntimeError(f"Failed to load document metadata: {fname}")
        docs.append(di)

    results: Dict = {"documents": [], "mismatches": []}

    # Collect revisions
    revs: List[Tuple[str, str, int, int]] = []  # (filename, rev, page, line)
    for di in docs:
        info = extract_revision_for_doc(doc_store, di)
        if info:
            rev, page, line = info
            revs.append((di.filename, rev, page, line))
        else:
            revs.append((di.filename, "UNKNOWN", 1, 1))
        results["documents"].append({"filename": di.filename, "doc_id": di.doc_id})

    # Compare all revisions pairwise
    unique_revs = {r[1] for r in revs}
    if len(unique_revs) > 1:
        # Report mismatch across all docs
        baseline = revs[0]
        for other in revs[1:]:
            if other[1] != baseline[1]:
                results["mismatches"].append(
                    {
                        "type": "revision",
                        "clause": "Document revision mismatch",
                        "a": {"filename": baseline[0], "value": baseline[1], "page": baseline[2], "line": baseline[3]},
                        "b": {"filename": other[0], "value": other[1], "page": other[2], "line": other[3]},
                    }
                )

    # Collect tolerance values
    tol_sets: Dict[str, List[TolHit]] = {}
    for di in docs:
        hits = extract_tolerances_for_doc(doc_store, di)
        tol_sets[di.filename] = hits

    # Simple heuristic: compare the minimum stated tolerance per doc
    mins: List[Tuple[str, Optional[TolHit]]] = []
    for fn, hits in tol_sets.items():
        mins.append((fn, min(hits, key=lambda h: h.value) if hits else None))

    baseline_fn, baseline_hit = mins[0]
    for other_fn, other_hit in mins[1:]:
        if baseline_hit and other_hit:
            if abs(baseline_hit.value - other_hit.value) > 1e-9:
                results["mismatches"].append(
                    {
                        "type": "tolerance",
                        "clause": "Minimum tolerance differs",
                        "a": {
                            "filename": baseline_fn,
                            "value": baseline_hit.raw,
                            "page": baseline_hit.page,
                            "line": baseline_hit.line,
                            "context": baseline_hit.context,
                        },
                        "b": {
                            "filename": other_fn,
                            "value": other_hit.raw,
                            "page": other_hit.page,
                            "line": other_hit.line,
                            "context": other_hit.context,
                        },
                    }
                )
        elif baseline_hit or other_hit:
            # One has tolerance info and the other doesn't
            present = baseline_hit if baseline_hit else other_hit
            missing_fn = other_fn if baseline_hit else baseline_fn
            results["mismatches"].append(
                {
                    "type": "tolerance",
                    "clause": "Tolerance present in one doc only",
                    "a": {
                        "filename": present and (baseline_fn if baseline_hit else other_fn),
                        "value": present.raw if present else None,
                        "page": present.page if present else None,
                        "line": present.line if present else None,
                        "context": present.context if present else None,
                    },
                    "b": {"filename": missing_fn, "value": None, "page": None, "line": None},
                }
            )

    logger.info(
        "Compare result: files=%s | doc_ids=%s | revs=%s | mismatches=%d",
        ",".join([d.filename for d in docs]),
        ",".join([d.doc_id for d in docs]),
        ",".join([f"{fn}:{rv}" for (fn, rv, _p, _l) in revs]),
        len(results["mismatches"]),
    )
    return results
