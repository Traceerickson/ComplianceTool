from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


CLAUSE_RE = re.compile(r"§\s*(\d+(?:\.\d+){0,3})")
TOL_RE = re.compile(r"(?:±|\+/-)\s*([0-9]*\.?[0-9]+)")
MATERIAL_RE = re.compile(r"\b(6061|7075|2024|17-4|15-5)[- ]?(?:T\d+)?\b", re.IGNORECASE)
PART_RE = re.compile(r"\bP-?\d{3,}\b", re.IGNORECASE)


@dataclass
class EcoChange:
    parts: List[str] = field(default_factory=list)
    clauses: List[str] = field(default_factory=list)
    deltas: List[str] = field(default_factory=list)  # textual changes (e.g., tolerance deltas)
    materials: List[str] = field(default_factory=list)
    notes: str = ""
    effective_date: Optional[str] = None


def parse_eco_text(text: str, effective_date: Optional[str] = None) -> EcoChange:
    """Best-effort parse of ECO/spec redlines into a normalized EcoChange."""
    clauses = [m.group(1) for m in CLAUSE_RE.finditer(text)]
    tolerances = [m.group(1) for m in TOL_RE.finditer(text)]
    materials = [m.group(0).upper() for m in MATERIAL_RE.finditer(text)]
    parts = [m.group(0).upper().replace(" ", "-") for m in PART_RE.finditer(text)]
    deltas = []
    if len(tolerances) >= 1:
        deltas.append(f"tolerance→{','.join(tolerances)}")

    return EcoChange(
        parts=list(dict.fromkeys(parts)),
        clauses=list(dict.fromkeys(clauses)),
        deltas=deltas,
        materials=list(dict.fromkeys(materials)),
        notes=text[:500],
        effective_date=effective_date,
    )

