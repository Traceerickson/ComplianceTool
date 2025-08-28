from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import socket
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from dateutil import tz
from jinja2 import Environment, FileSystemLoader, select_autoescape
# Heavy/optional deps (reportlab, PyPDF2, pdf2image, PIL) are imported lazily

from ingest import Ingestor
from search import SearchEngine
from storage.doc_store import DocStore, DocumentInfo
from storage.vector_store import VectorStore, VectorRecord
from utils.logger import get_logger
from utils.hashing import sha256_hex


logger = get_logger(__name__)


@dataclass
class EvidenceItem:
    evidence_id: str
    doc_id: str
    filename: str
    page: int
    start_line: int
    end_line: int
    excerpt: str
    citation: str
    source_hash: str
    collected_at: str
    redaction_applied: bool = False


def _load_redaction_config(path: str = "config/redaction.yaml") -> Dict[str, Any]:
    try:
        import yaml  # local dep present

        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Failed loading redaction config: %s", e)
    return {"patterns": [], "regions": []}


def _now_iso() -> str:
    return datetime.now(tz.tzlocal()).isoformat()


def _find_source_path(filename: str) -> Optional[str]:
    # Search typical locations where uploads or data live
    candidates = [
        os.path.join("data", "uploads", filename),
        os.path.join("data", filename),
        filename,
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _source_sha256(filename: str) -> str:
    path = _find_source_path(filename)
    if path and os.path.exists(path) and os.path.isfile(path):
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    return sha256_hex(filename)


def _dedup_key(rec: VectorRecord) -> Tuple[str, int, int]:
    return (rec.doc_id, rec.page_number, rec.line_start)


def _collect_from_search(query: str, max_items: int, filters: Dict[str, Any]) -> List[EvidenceItem]:
    search = SearchEngine()
    results = search.search(query, top_k=max_items * 4)
    ingestor = Ingestor()
    vstore = search.vstore
    items: List[EvidenceItem] = []
    seen = set()
    for score_item in vstore.search.__self__ if False else []:  # placeholder to silence linter
        pass
    # Re-run via vstore to get raw records to dedupe; use deterministic embedding path already in SearchEngine
    from utils.embeddings import deterministic_embedding

    q_emb = deterministic_embedding(query, dim=vstore.dim)
    raw = vstore.search(q_emb, top_k=max_items * 4)
    for score, rec in raw:
        k = _dedup_key(rec)
        if k in seen:
            continue
        if filters.get("doc_ids") and rec.doc_id not in set(filters["doc_ids"]):
            continue
        seen.add(k)
        items.append(
            EvidenceItem(
                evidence_id=str(uuid.uuid4()),
                doc_id=rec.doc_id,
                filename=rec.filename,
                page=rec.page_number,
                start_line=rec.line_start,
                end_line=rec.line_end,
                excerpt=(rec.text or "")[:300],
                citation=f"{rec.filename} p{rec.page_number} l{rec.line_start}-{rec.line_end}",
                source_hash=_source_sha256(rec.filename),
                collected_at=_now_iso(),
            )
        )
        if len(items) >= max_items:
            break
    return items


def _collect_from_provenance(car_id: str, max_items: int, filters: Dict[str, Any]) -> List[EvidenceItem]:
    items: List[EvidenceItem] = []
    drafts_dir = os.path.join("storage", "drafts")
    if not os.path.exists(drafts_dir):
        return items
    for fn in os.listdir(drafts_dir):
        if not fn.endswith('.json'):
            continue
        try:
            data = json.load(open(os.path.join(drafts_dir, fn), 'r', encoding='utf-8'))
        except Exception:
            continue
        bundle = data.get('bundle') or {}
        prov = bundle.get('provenance', {})
        for field_path, cits in prov.items():
            for c in cits:
                filename = c.get('filename') or ''
                if not filename:
                    continue
                # Allow filter by doc_ids if provided
                if filters.get('doc_ids'):
                    # Need to map filename -> doc_id via DocStore
                    pass
                items.append(
                    EvidenceItem(
                        evidence_id=str(uuid.uuid4()),
                        doc_id='',
                        filename=filename,
                        page=int(c.get('page') or 1),
                        start_line=int(c.get('line') or 1),
                        end_line=int(c.get('line') or 1),
                        excerpt=(c.get('excerpt') or '')[:300],
                        citation=f"{filename} p{c.get('page')} l{c.get('line')}",
                        source_hash=_source_sha256(filename),
                        collected_at=_now_iso(),
                    )
                )
                if len(items) >= max_items:
                    return items
    return items


def _apply_redactions_text(content: str, patterns: List[str]) -> Tuple[str, Dict[str, int]]:
    matches: Dict[str, int] = {}
    redacted = content
    for pat in patterns:
        try:
            cnt = len(re.findall(pat, redacted))
            if cnt:
                redacted = re.sub(pat, "████", redacted)
                matches[pat] = cnt
        except re.error:
            continue
    return redacted, matches


def _write_index_html(build_dir: str, context: Dict[str, Any]):
    env = Environment(loader=FileSystemLoader('templates'), autoescape=select_autoescape(['html']))
    tpl = env.get_template('audit/index.html.jinja')
    html = tpl.render(**context)
    with open(os.path.join(build_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(html)


def _write_index_pdf(build_dir: str, context: Dict[str, Any]):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from reportlab.lib import colors
    except Exception as e:  # pragma: no cover
        # Gracefully skip PDF generation when reportlab is missing
        logger.warning("ReportLab not available; skipping PDF index: %s", e)
        with open(os.path.join(build_dir, 'index.pdf.missing.txt'), 'w', encoding='utf-8') as f:
            f.write('index.pdf not generated. Install reportlab to enable PDF output.')
        return

    pdf_path = os.path.join(build_dir, 'index.pdf')
    doc = SimpleDocTemplate(pdf_path, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []
    story.append(Paragraph(f"Audit Pack — {context['pack_id']}", styles['Title']))
    story.append(Paragraph(context.get('header_summary', ''), styles['Normal']))
    story.append(Spacer(1, 0.2*inch))
    data = [["#", "Filename", "Page", "Excerpt", "Citation", "Redaction"]]
    for i, ev in enumerate(context['evidence'], start=1):
        data.append([str(i), ev['filename'], str(ev['page']), ev['excerpt'][:120], ev['citation'], 'Yes' if ev.get('redaction_applied') else 'No'])
    table = Table(data, repeatRows=1, colWidths=[0.4*inch, 1.6*inch, 0.5*inch, 3.0*inch, 1.8*inch, 0.7*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ]))
    story.append(table)
    doc.build(story)


def _write_manifest(build_dir: str, evidence_files: List[Tuple[str, EvidenceItem]]):
    # manifest.json
    man_rows: List[Dict[str, Any]] = []
    for path, ev in evidence_files:
        with open(path, 'rb') as f:
            b = f.read()
        sha = hashlib.sha256(b).hexdigest()
        man_rows.append({
            'evidence_id': ev.evidence_id,
            'filename': ev.filename,
            'page': ev.page,
            'start_line': ev.start_line,
            'end_line': ev.end_line,
            'sha256': sha,
            'bytes': len(b),
            'citation': ev.citation,
            'source_path': path,
        })
    with open(os.path.join(build_dir, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump({'rows': man_rows}, f, ensure_ascii=False, indent=2)
    # manifest.csv
    csv_path = os.path.join(build_dir, 'manifest.csv')
    with open(csv_path, 'w', encoding='utf-8', newline='') as cf:
        w = csv.DictWriter(cf, fieldnames=list(man_rows[0].keys()) if man_rows else ['evidence_id'])
        w.writeheader()
        for r in man_rows:
            w.writerow(r)
    # hashes.json
    with open(os.path.join(build_dir, 'hashes.json'), 'w', encoding='utf-8') as f:
        json.dump({r['evidence_id']: r['sha256'] for r in man_rows}, f, indent=2)


def _zip_pack(build_dir: str, pack_id: str) -> str:
    import zipfile
    zip_path = os.path.join('packs', f'{pack_id}.zip')
    os.makedirs('packs', exist_ok=True)
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for root, _dirs, files in os.walk(build_dir):
            for fn in sorted(files):
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, build_dir)
                z.write(full, arcname=rel)
    return zip_path


def build_audit_pack(
    *,
    created_by: str = "dev",
    car_id: Optional[str] = None,
    query: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
    include_forms: bool = True,
    include_compare_results: bool = False,  # placeholder for future use
    redaction: Optional[Dict[str, Any]] = None,
    max_items: int = 30,
) -> Dict[str, Any]:
    """
    Build an audit pack by assembling evidence items and packaging into a ZIP with
    index, manifest, hashes, and chain-of-custody.
    """
    if not car_id and not query:
        raise ValueError("Provide either car_id or query")
    t0 = time.time()
    filters = filters or {}
    pack_id = str(uuid.uuid4())
    build_dir = os.path.join('packs', pack_id)
    ev_dir = os.path.join(build_dir, 'evidence')
    red_dir = os.path.join(build_dir, 'redactions')
    os.makedirs(ev_dir, exist_ok=True)
    os.makedirs(red_dir, exist_ok=True)

    # Collect evidence
    evidence: List[EvidenceItem] = []
    if car_id and include_forms:
        evidence.extend(_collect_from_provenance(car_id, max_items=max_items, filters=filters))
    if query:
        evidence.extend(_collect_from_search(query, max_items=max_items, filters=filters))
    # Deduplicate by (filename, page, start_line)
    dedup = {}
    for ev in evidence:
        key = (ev.filename, ev.page, ev.start_line)
        dedup[key] = ev
    evidence = list(dedup.values())[:max_items]

    # Redaction config
    merged_redaction = _load_redaction_config()
    if redaction:
        merged_redaction['patterns'] = list(set((merged_redaction.get('patterns') or []) + (redaction.get('patterns') or [])))
        merged_redaction['regions'] = (merged_redaction.get('regions') or []) + (redaction.get('regions') or [])
    mode = (redaction or {}).get('mode', 'overlay') if redaction else 'overlay'

    # Write evidence files (txt snippet per item) and apply text redactions
    evidence_files: List[Tuple[str, EvidenceItem]] = []
    for idx, ev in enumerate(evidence, start=1):
        content = ev.excerpt
        redaction_log = {'filename': ev.filename, 'page': ev.page, 'matches': [], 'regions_count': 0}
        if merged_redaction.get('patterns'):
            content_red, matches = _apply_redactions_text(content, merged_redaction['patterns'])
            ev.redaction_applied = any(matches.values())
            redaction_log['matches'] = [{'pattern': k, 'count': v} for k, v in matches.items()]
            content = content_red
        # Save snippet
        out_path = os.path.join(ev_dir, f"{idx:03d}_{os.path.basename(ev.filename)}.txt")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(content)
        with open(os.path.join(red_dir, f"{idx:03d}_{os.path.basename(ev.filename)}.redaction.json"), 'w', encoding='utf-8') as f:
            json.dump(redaction_log, f, ensure_ascii=False, indent=2)
        evidence_files.append((out_path, ev))

    # Build index.html and index.pdf
    header_summary = f"Created by {created_by} on {datetime.now().isoformat()} | items: {len(evidence)} | mode: {mode}"
    context = {
        'pack_id': pack_id,
        'created_by': created_by,
        'created_at': _now_iso(),
        'query_or_car': car_id or query,
        'filters': filters,
        'evidence': [asdict(e) for e in evidence],
        'header_summary': header_summary,
    }
    _write_index_html(build_dir, context)
    _write_index_pdf(build_dir, context)

    # Manifest and hashes
    _write_manifest(build_dir, evidence_files)

    # Chain of custody (sha is filled after zipping)
    chain_path = os.path.join(build_dir, 'chain_of_custody.json')
    chain = {
        'pack_id': pack_id,
        'created_by': created_by,
        'created_at': _now_iso(),
        'query_or_car_id': car_id or query,
        'filters': filters,
        'evidence_ids': [e.evidence_id for e in evidence],
        'redaction_mode': mode,
        'tool_versions': {
            'reportlab': getattr(__import__('reportlab'), '__version__', ''),
            'PyPDF2': getattr(__import__('PyPDF2'), '__version__', ''),
        },
        'host_info': {'hostname': socket.gethostname()},
        'sha256_of_zip': None,
    }
    with open(chain_path, 'w', encoding='utf-8') as f:
        json.dump(chain, f, indent=2)

    # Zip build dir
    zip_path = _zip_pack(build_dir, pack_id)
    # Update chain with zip sha
    with open(zip_path, 'rb') as zf:
        sha_zip = hashlib.sha256(zf.read()).hexdigest()
    chain['sha256_of_zip'] = sha_zip
    with open(chain_path, 'w', encoding='utf-8') as f:
        json.dump(chain, f, indent=2)

    dt_ms = int((time.time() - t0) * 1000)
    logger.info("build_audit_pack pack_id=%s items=%d duration_ms=%d", pack_id, len(evidence), dt_ms)

    return {
        'pack_id': pack_id,
        'zip_path': zip_path,
        'index_path': os.path.join(build_dir, 'index.html'),
        'manifest_path': os.path.join(build_dir, 'manifest.json'),
        'counts': {'items': len(evidence)},
    }
