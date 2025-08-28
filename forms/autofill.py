from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel
import re

from forms.extract_characteristics import Characteristic, Citation, extract_characteristics_from_docs
from forms.merge_measurements import Measurement, merge_cmm_with_characteristics
from ingest import Ingestor
from storage.doc_store import DocStore, DocumentInfo
from utils.hashing import sha1_hex
from utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class As9102Form1:
    part_number: Optional[str] = None
    part_name: Optional[str] = None
    part_revision: Optional[str] = None
    drawing_number: Optional[str] = None
    material: Optional[str] = None
    special_processes: Optional[str] = None


@dataclass
class As9102Form2:
    characteristics: List[Characteristic] = field(default_factory=list)


@dataclass
class As9102Form3:
    measurements: List[Measurement] = field(default_factory=list)


@dataclass
class EightD:
    D1_team: Optional[str] = None
    D2_problem: Optional[str] = None
    D3_containment: Optional[str] = None
    D4_root_cause: Optional[str] = None
    D5_corrective_action: Optional[str] = None
    D6_validate: Optional[str] = None
    D7_prevent_rec: Optional[str] = None
    D8_congratulate: Optional[str] = None


@dataclass
class DraftBundle:
    draft_id: str
    draft_type: str  # as9102|8d
    form_level: Optional[str] = None  # 1|2|3 for as9102
    form1: Optional[As9102Form1] = None
    form2: Optional[As9102Form2] = None
    form3: Optional[As9102Form3] = None
    eightd: Optional[EightD] = None
    completion_score: int = 0
    missing_fields: List[str] = field(default_factory=list)
    provenance: Dict[str, List[Citation]] = field(default_factory=dict)


def _find_field(lines: List[str], patterns: List[str]) -> Optional[Tuple[str, int]]:
    for idx, line in enumerate(lines, start=1):
        low = line.lower()
        for pat in patterns:
            pos = low.find(pat.lower())
            if pos >= 0:
                rest = line[pos + len(pat) :].strip()
                if rest.startswith(":"):
                    rest = rest[1:].strip()
                if not rest:
                    rest = line.strip()
                return rest, idx
    return None


def _search_doc_for_fields(doc_store: DocStore, doc: DocumentInfo) -> Dict[str, Tuple[str, Citation]]:
    fields: Dict[str, Tuple[str, Citation]] = {}
    pages = doc_store.load_doc_lines(doc.doc_id) or []
    key_map = {
        "part_number": ["part number", "pn", "drawing number"],
        "part_name": ["part name", "item name", "description"],
        "part_revision": ["rev", "revision"],
        "material": ["material"],
        "special_processes": ["special process", "plating", "heat treat"],
    }
    for p_idx, lines in enumerate(pages, start=1):
        for fname, patterns in key_map.items():
            if fname in fields:
                continue
            found = _find_field(lines[:60], patterns)
            if found:
                val, line_no = found
                citation = Citation(filename=doc.filename, page=p_idx, line=line_no, excerpt=lines[line_no - 1][:200])
                fields[fname] = (val, citation)
        if len(fields) == len(key_map):
            break
    return fields


def _score_and_missing(form1: Optional[As9102Form1], form2: Optional[As9102Form2], form3: Optional[As9102Form3]) -> Tuple[int, List[str]]:
    req_fields = []
    if form1:
        req_fields += [
            ("form1.part_number", bool(form1.part_number)),
            ("form1.part_name", bool(form1.part_name)),
            ("form1.part_revision", bool(form1.part_revision)),
        ]
    if form2:
        req_fields += [("form2.characteristics", len(form2.characteristics) >= 10)]
    if form3:
        has_pf = any(m.pass_fail is not None for m in form3.measurements)
        req_fields += [("form3.measurements", has_pf)]

    filled = sum(1 for _, ok in req_fields if ok)
    score = int(round(100 * filled / max(1, len(req_fields))))
    missing = [name for name, ok in req_fields if not ok]
    return score, missing


def _add_prov(prov: Dict[str, List[Citation]], key: str, cits: List[Citation]):
    if not cits:
        return
    prov.setdefault(key, [])
    prov[key].extend(cits)


def generate_as9102(doc_ids: List[str], cmm_files: List[str], form_levels: List[str]) -> DraftBundle:
    ingestor = Ingestor()
    doc_store = ingestor.doc_store
    docs = [doc_store.docs.get(did) for did in doc_ids if did in doc_store.docs]
    docs = [d for d in docs if d]
    if not docs:
        raise ValueError("No valid doc_ids provided")

    # Form 1: basic metadata from docs
    f1 = As9102Form1()
    provenance: Dict[str, List[Citation]] = {}
    for d in docs:
        hits = _search_doc_for_fields(doc_store, d)
        for k, (val, cit) in hits.items():
            if getattr(f1, k) is None:
                setattr(f1, k, val)
                _add_prov(provenance, f"form1.{k}", [cit])

    # Form 2: characteristics from docs
    chars: List[Characteristic] = extract_characteristics_from_docs(doc_store, docs)
    f2 = As9102Form2(characteristics=chars)
    for ch in chars:
        _add_prov(provenance, f"form2.characteristics[{ch.char_id}]", [ch.citation])

    # Form 3: merged measurements
    measurements: List[Measurement] = merge_cmm_with_characteristics(chars, cmm_files)
    f3 = As9102Form3(measurements=measurements)
    for m in measurements:
        if m.provenance.get("source_file"):
            _add_prov(
                provenance,
                f"form3.measurements[{m.char_id}]",
                [Citation(filename=m.provenance.get("source_file", ""), page=1, line=int(m.provenance.get("row_number") or 1), excerpt=m.description[:200])],
            )

    score, missing = _score_and_missing(f1, f2, f3)
    draft_id = str(uuid.uuid4())
    bundle = DraftBundle(
        draft_id=draft_id,
        draft_type="as9102",
        form_level=",".join(sorted(set(form_levels))) if form_levels else None,
        form1=f1,
        form2=f2,
        form3=f3,
        completion_score=score,
        missing_fields=missing,
        provenance=provenance,
    )

    _persist_draft(bundle, source_doc_ids=doc_ids, cmm_files=cmm_files)
    return bundle


def generate_8d(ncr_json: Dict, evidence_doc_ids: List[str], lessons_from: Optional[List[str]] = None, lessons_query: Optional[str] = None) -> DraftBundle:
    ingestor = Ingestor()
    doc_store = ingestor.doc_store
    docs = [doc_store.docs.get(did) for did in evidence_doc_ids if did in doc_store.docs]
    docs = [d for d in docs if d]

    e = EightD()
    prov: Dict[str, List[Citation]] = {}
    # Seed from NCR JSON
    if ncr_json:
        e.D1_team = ncr_json.get("owner")
        e.D2_problem = ncr_json.get("symptom") or ncr_json.get("defect")
        e.D3_containment = f"Date: {ncr_json.get('date', '')}; Immediate containment initiated."
        _add_prov(prov, "eightd.D1_team", [])
        _add_prov(prov, "eightd.D2_problem", [])
        _add_prov(prov, "eightd.D3_containment", [])

    # Link a few evidence citations from docs (first page lines)
    for d in docs:
        pages = doc_store.load_doc_lines(d.doc_id) or []
        if pages and pages[0]:
            cit = Citation(filename=d.filename, page=1, line=1, excerpt=pages[0][0][:200])
            _add_prov(prov, "eightd.D2_problem", [cit])

    # Optionally enrich from lessons-learned
    try:
        from lessons.search import search_lessons, LessonsStore
    except Exception:
        search_lessons = None
        LessonsStore = None  # type: ignore

    selected_ids: List[str] = lessons_from or []
    if (not selected_ids) and lessons_query and search_lessons:
        res = search_lessons(lessons_query, top_k=3)
        selected_ids = [r.get("ncr_id") for r in res if r.get("ncr_id")]

    if selected_ids and LessonsStore:
        store = LessonsStore()
        # Merge top prior actions into D4/D5
        roots = []
        actions = []
        for nid in selected_ids:
            capa = next((c for c in store.capa.values() if c.ncr_id == nid), None)
            if capa and capa.root_cause:
                roots.append(f"NCR {nid}: {capa.root_cause}")
            if capa and capa.corrective_action:
                actions.append(f"NCR {nid}: {capa.corrective_action}")
            # Add provenance tagged to NCR
            _add_prov(prov, "eightd.D4_root_cause", [Citation(filename=f"NCR_{nid}.json", page=1, line=1, excerpt="from lessons")])
            _add_prov(prov, "eightd.D5_corrective_action", [Citation(filename=f"NCR_{nid}.json", page=1, line=1, excerpt="from lessons")])
        if roots and not e.D4_root_cause:
            e.D4_root_cause = "\n".join(roots)
        if actions and not e.D5_corrective_action:
            e.D5_corrective_action = "\n".join(actions)

    # Score: basic presence of D1, D2, D3
    present = sum(int(bool(x)) for x in [e.D1_team, e.D2_problem, e.D3_containment])
    score = int(round(100 * present / 3))

    draft_id = str(uuid.uuid4())
    bundle = DraftBundle(
        draft_id=draft_id,
        draft_type="8d",
        eightd=e,
        completion_score=score,
        missing_fields=[k for k, v in {"eightd.D1_team": e.D1_team, "eightd.D2_problem": e.D2_problem, "eightd.D3_containment": e.D3_containment}.items() if not v],
        provenance=prov,
    )

    _persist_draft(bundle, source_doc_ids=evidence_doc_ids, cmm_files=[])
    return bundle


def _persist_draft(bundle: DraftBundle, source_doc_ids: List[str], cmm_files: List[str]):
    os.makedirs("storage/drafts", exist_ok=True)
    path = os.path.join("storage/drafts", f"draft_{bundle.draft_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "bundle": _bundle_to_dict(bundle),
                "source_doc_ids": source_doc_ids,
                "cmm_files": cmm_files,
                "timestamp": time.time(),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    logger.info(
        "Draft saved id=%s type=%s score=%d docs=%s cmm=%s",
        bundle.draft_id,
        bundle.draft_type,
        bundle.completion_score,
        ",".join(source_doc_ids),
        ",".join([os.path.basename(x) for x in cmm_files]),
    )


def _bundle_to_dict(bundle: DraftBundle) -> Dict:
    def ser(obj):
        if hasattr(obj, "__dict__"):
            return {k: ser(v) for k, v in obj.__dict__.items()}
        if isinstance(obj, list):
            return [ser(x) for x in obj]
        return obj

    data = ser(bundle)
    # Convert citations (dataclass) to dicts
    prov: Dict[str, List[Dict]] = {}
    for k, lst in bundle.provenance.items():
        prov[k] = [asdict(c) for c in lst]
    data["provenance"] = prov
    return data
