from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from storage.doc_store import DocStore, DocumentInfo


@dataclass
class Citation:
    filename: str
    page: int
    line: int
    excerpt: str


@dataclass
class Characteristic:
    char_id: str
    description: str
    nominal: Optional[float]
    tolerance: Optional[float]
    unit: Optional[str]
    citation: Citation


TABLE_ROW_RE = re.compile(
    r"^(?P<id>[A-Za-z0-9_.-]+)\s*[|,\t]\s*(?P<desc>[^|,\t]+)[|,\t]\s*(?P<nom>-?\d+(?:\.\d+)?)(?:\s*(?P<unit>[a-zA-Z%/]+))?\s*[|,\t]\s*(?:±|\+/-)?\s*(?P<tol>\d+(?:\.\d+)?)",
    re.IGNORECASE,
)

LINE_DIM_RE = re.compile(
    r"^(?:Dim\s*)?(?P<id>[#\dA-Za-z_.-]+):?\s*(?P<desc>[^;]+?)(?:;|\s{2,}|$).*?(?:(?:Nom|Nominal)\s*:?\s*(?P<nom>-?\d+(?:\.\d+)?))?.*?(?:±|\+/-)\s*(?P<tol>\d+(?:\.\d+)?)(?:\s*(?P<unit>[a-zA-Z%/]+))?",
    re.IGNORECASE,
)


def _to_float(s: Optional[str]) -> Optional[float]:
    if s is None:
        return None
    try:
        return float(s)
    except Exception:
        try:
            return float(s.replace(",", "").strip())
        except Exception:
            return None


def extract_characteristics_from_docs(doc_store: DocStore, docs: List[DocumentInfo]) -> List[Characteristic]:
    """
    Heuristics:
    - Prefer pipe/comma/TSV-like table rows: id | desc | nominal [unit] | ±tol
    - Fallback to line patterns: "#12: Widget hole; Nominal: 5.00 ±0.05 mm"
    Returns a list with at least id/desc and citations.
    """
    results: List[Characteristic] = []
    for di in docs:
        pages = doc_store.load_doc_lines(di.doc_id) or []
        for p_idx, lines in enumerate(pages, start=1):
            for l_idx, line in enumerate(lines, start=1):
                m = TABLE_ROW_RE.search(line)
                if not m:
                    m = LINE_DIM_RE.search(line)
                if m:
                    char_id = m.group("id").strip().lstrip("#")
                    desc = (m.group("desc") or "").strip()
                    nom = _to_float(m.group("nom"))
                    tol = _to_float(m.group("tol"))
                    unit = m.group("unit")
                    excerpt = line.strip()[:200]
                    results.append(
                        Characteristic(
                            char_id=char_id,
                            description=desc,
                            nominal=nom,
                            tolerance=tol,
                            unit=unit,
                            citation=Citation(
                                filename=di.filename, page=p_idx, line=l_idx, excerpt=excerpt
                            ),
                        )
                    )
    # Deduplicate by (id, desc) keeping first occurrence
    seen = set()
    deduped: List[Characteristic] = []
    for ch in results:
        key = (ch.char_id.lower(), ch.description.lower())
        if key in seen:
            continue
        deduped.append(ch)
        seen.add(key)
    return deduped

