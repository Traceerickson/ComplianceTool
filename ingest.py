from __future__ import annotations

import os
import re
import uuid
from typing import Dict, List, Optional, Tuple

from docx import Document as DocxDocument  # type: ignore
from pdfminer.high_level import extract_text  # type: ignore

from storage.doc_store import DocStore, DocumentInfo, RevisionInfo
from storage.vector_store import VectorStore
from utils.chunking import chunk_text, split_into_lines
from utils.embeddings import batch_embeddings
from utils.hashing import sha256_hex, sha1_hex
from utils.logger import get_logger

logger = get_logger(__name__)


REV_PATTERN = re.compile(r"\bRev\s*([A-Za-z0-9][A-Za-z0-9\.]*)\b", re.IGNORECASE)
TOL_PATTERN = re.compile(
    r"(?:(?:\u00B1|±|\+/-)\s*([0-9]*\.?[0-9]+))|(?:tolerances?:?\s*([0-9]*\.?[0-9]+))",
    re.IGNORECASE,
)


def ensure_data_dirs():
    os.makedirs("data", exist_ok=True)
    os.makedirs("data/uploads", exist_ok=True)


def _extract_pdf_pages_lines(path: str) -> List[List[str]]:
    pages: List[List[str]] = []
    # Use extract_text per page_number to approximate line structure.
    # We attempt to extract until it returns empty for next page index.
    page_idx = 0
    while True:
        try:
            txt = extract_text(path, page_numbers=[page_idx])
        except Exception:
            # pdfminer may raise when page index out of range
            break
        if not txt:
            if page_idx == 0:
                break
            else:
                # No more pages
                break
        pages.append(split_into_lines(txt))
        page_idx += 1
        # Guard to prevent infinite loops on malformed pdfs
        if page_idx > 5000:
            break
    if not pages:
        # Fallback: whole document at once
        txt = extract_text(path)
        pages = [split_into_lines(txt or "")]
    return pages


def _extract_docx_pages_lines(path: str) -> List[List[str]]:
    doc = DocxDocument(path)
    # DOCX has no pages; treat as single page split by paragraphs
    lines: List[str] = []
    for p in doc.paragraphs:
        lines.append(p.text)
    return [lines or [""]]


def _extract_txt_pages_lines(path: str) -> List[List[str]]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    return [split_into_lines(text)]


def extract_revision_from_lines(lines: List[str]) -> Optional[Tuple[str, int]]:
    # Scan the first 60 lines for a Rev pattern
    for idx, line in enumerate(lines[:60], start=1):
        m = REV_PATTERN.search(line)
        if m:
            return m.group(1).upper(), idx
    return None


def extract_tolerances_from_lines(lines: List[str]) -> List[Tuple[str, int]]:
    values: List[Tuple[str, int]] = []
    for idx, line in enumerate(lines, start=1):
        for m in TOL_PATTERN.finditer(line):
            val = m.group(1) or m.group(2)
            if val:
                values.append((val, idx))
    return values


class Ingestor:
    def __init__(self, dim: int = 384):
        ensure_data_dirs()
        self.doc_store = DocStore()
        self.vstore = VectorStore(dim=dim)

    def _parse_file(self, path: str) -> List[List[str]]:
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            return _extract_pdf_pages_lines(path)
        elif ext in (".docx", ".doc"):
            return _extract_docx_pages_lines(path)
        elif ext in (".txt", ".text"):
            return _extract_txt_pages_lines(path)
        else:
            raise ValueError(f"Unsupported file type: {ext}")

    def ingest_file(self, path: str) -> Dict[str, any]:
        if not os.path.exists(path):
            raise FileNotFoundError(path)

        logger.info("Ingesting file: %s", path)
        pages = self._parse_file(path)
        filename = os.path.basename(path)
        doc_id = sha1_hex(os.path.abspath(path))

        # Extract document-level revision(s)
        revisions: List[RevisionInfo] = []
        if pages:
            head_lines = pages[0]
            rev = extract_revision_from_lines(head_lines)
            if rev:
                revisions.append(RevisionInfo(value=rev[0], page_number=1, line_number=rev[1]))

        self.doc_store.save_doc_lines(doc_id, pages)
        self.doc_store.upsert_document(DocumentInfo(doc_id=doc_id, filename=filename, revisions=revisions))

        # Build chunks with metadata
        metadatas: List[Dict] = []
        texts: List[str] = []
        for p_idx, lines in enumerate(pages, start=1):
            page_text = "\n".join(lines)
            chunks = chunk_text(page_text, max_tokens=500, preserve_lines=True)
            for c_text, (l_start, l_end) in chunks:
                texts.append(c_text)
                metadatas.append(
                    {
                        "doc_id": doc_id,
                        "filename": filename,
                        "page_number": p_idx,
                        "line_start": l_start,
                        "line_end": l_end,
                        "text_hash": sha256_hex(c_text),
                        "text": c_text,
                    }
                )

        if texts:
            from utils.embeddings import batch_embeddings

            embs = batch_embeddings(texts, dim=self.vstore.dim)
            self.vstore.add(embs, metadatas)

        logger.info(
            "Ingested %s: %d pages, %d chunks", filename, len(pages), len(texts)
        )
        return {"doc_id": doc_id, "filename": filename, "pages": len(pages), "chunks": len(texts)}

    def ingest_directory(self, data_dir: str = "data") -> List[Dict[str, any]]:
        results: List[Dict[str, any]] = []
        for root, _dirs, files in os.walk(data_dir):
            for fname in files:
                if os.path.splitext(fname)[1].lower() in (".pdf", ".docx", ".doc", ".txt", ".text"):
                    path = os.path.join(root, fname)
                    try:
                        results.append(self.ingest_file(path))
                    except Exception as e:
                        logger.exception("Failed to ingest %s: %s", fname, e)
        return results

