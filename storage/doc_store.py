from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from typing import Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RevisionInfo:
    value: str
    page_number: int
    line_number: int


@dataclass
class DocumentInfo:
    doc_id: str
    filename: str
    revisions: List[RevisionInfo]


class DocStore:
    """Simple JSON-based document metadata store."""

    def __init__(self, storage_dir: str = "storage"):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self.docs_index_path = os.path.join(self.storage_dir, "docs_index.json")
        self.doc_cache_dir = os.path.join(self.storage_dir, "doc_cache")
        os.makedirs(self.doc_cache_dir, exist_ok=True)
        self.docs: Dict[str, DocumentInfo] = {}
        self._load()

    def _load(self):
        if os.path.exists(self.docs_index_path):
            try:
                with open(self.docs_index_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for doc_id, info in data.items():
                    revisions = [RevisionInfo(**r) for r in info.get("revisions", [])]
                    self.docs[doc_id] = DocumentInfo(
                        doc_id=doc_id, filename=info["filename"], revisions=revisions
                    )
            except Exception:
                logger.exception("Failed to load docs index")

    def _save(self):
        data = {
            doc_id: {
                "doc_id": di.doc_id,
                "filename": di.filename,
                "revisions": [asdict(r) for r in di.revisions],
            }
            for doc_id, di in self.docs.items()
        }
        with open(self.docs_index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def upsert_document(self, doc: DocumentInfo):
        self.docs[doc.doc_id] = doc
        self._save()

    def get_document_by_filename(self, filename: str) -> Optional[DocumentInfo]:
        for di in self.docs.values():
            if os.path.basename(di.filename) == os.path.basename(filename):
                return di
        return None

    def save_doc_lines(self, doc_id: str, pages: List[List[str]]):
        path = os.path.join(self.doc_cache_dir, f"{doc_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"pages": pages}, f)

    def load_doc_lines(self, doc_id: str) -> Optional[List[List[str]]]:
        path = os.path.join(self.doc_cache_dir, f"{doc_id}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("pages")
        return None

