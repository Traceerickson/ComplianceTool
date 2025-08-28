from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from storage.doc_store import DocStore
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Node:
    id: str
    doc_id: Optional[str]
    filename: str
    type: str
    owner: Optional[str] = None


@dataclass
class Edge:
    src: str
    dst: str
    type: str


TYPE_PATTERNS = [
    (re.compile(r"\bSOP[-_ ]?\d+", re.IGNORECASE), "SOP"),
    (re.compile(r"\bNCP[-_ ]?\d+|\bNC[-_ ]?\d+", re.IGNORECASE), "NC_PROGRAM"),
    (re.compile(r"\bFX[-_ ]?\d+|\bFixture\b", re.IGNORECASE), "FIXTURE"),
    (re.compile(r"\bChecklist\b", re.IGNORECASE), "CHECKLIST"),
    (re.compile(r"\bTraining\b", re.IGNORECASE), "TRAINING"),
]

CLAUSE_RE = re.compile(r"§\s*(\d+(?:\.\d+){0,3})")


def infer_type(filename: str) -> str:
    for pat, t in TYPE_PATTERNS:
        if pat.search(filename):
            return t
    return "SPEC"


def infer_owner(doc_type: str, filename: str) -> str:
    if doc_type == "SOP" or "checklist" in filename.lower():
        return "QA"
    if doc_type == "NC_PROGRAM":
        return "MFG Eng"
    if doc_type == "FIXTURE":
        return "Tooling"
    if doc_type == "TRAINING":
        return "HR/QA"
    return "Eng"


def build_graph(doc_store: DocStore, out_path: str = "data/graph.json") -> Dict:
    nodes: Dict[str, Node] = {}
    edges: List[Edge] = []
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    for di in doc_store.docs.values():
        t = infer_type(di.filename)
        node_id = di.doc_id
        nodes[node_id] = Node(id=node_id, doc_id=di.doc_id, filename=di.filename, type=t, owner=infer_owner(t, di.filename))
        # Parse references within document lines
        pages = doc_store.load_doc_lines(di.doc_id) or []
        for lines in pages:
            text = "\n".join(lines)
            # explicit references
            for pat, ref_type in TYPE_PATTERNS:
                for m in pat.finditer(text):
                    ref = m.group(0)
                    ref_id = f"ref:{ref.upper()}"
                    if ref_id not in nodes:
                        nodes[ref_id] = Node(id=ref_id, doc_id=None, filename=ref.upper(), type=ref_type)
                    edges.append(Edge(src=node_id, dst=ref_id, type="references"))
            # clause anchors
            for m in CLAUSE_RE.finditer(text):
                clause_id = f"clause:{m.group(1)}"
                if clause_id not in nodes:
                    nodes[clause_id] = Node(id=clause_id, doc_id=None, filename=m.group(1), type="CLAUSE")
                edges.append(Edge(src=node_id, dst=clause_id, type="references"))

    data = {
        "nodes": [asdict(n) for n in nodes.values()],
        "edges": [asdict(e) for e in edges],
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.info("Graph built: %d nodes, %d edges", len(nodes), len(edges))
    return data


def load_graph(path: str = "data/graph.json") -> Dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"nodes": [], "edges": []}

