AI Compliance Copilot — Prototype

Overview
- P0: Document ingestion + semantic search with citations
- Spec/Rev Guard: Compare controlled docs for revision/tolerance mismatches

Quickstart
- Install deps: `pip install -r requirements.txt` (or see Minimal Deps below)
- Put files under `data/` or upload via the UI
- Run API/UI: `uvicorn main:app --reload`
- Open: http://127.0.0.1:8000/

Features
- Ingests PDF/DOCX/TXT, chunks ~500 tokens, stores metadata and deterministic embeddings
- Semantic search at `/search?query=...`
- Compare 2–3 docs at `/compare` (used by UI) to flag:
  - Revision mismatches (e.g., Rev E vs Rev F)
  - Tolerance mismatches (e.g., ±0.002 vs ±0.0015)
- Forms Auto-Fill: Generate AS9102 (Forms 1–3) and 8D/CAPA drafts with per-field provenance
 - Audit Pack Builder: Compile objective evidence for a CAR/NCR or query into a ZIP with index (HTML/PDF), manifest, hashes, and chain-of-custody.

Endpoints
- GET `/` — Minimal UI (Jinja2) for upload + compare
- POST `/upload` — Upload 1–many files (PDF/DOCX/TXT), immediate ingest
- GET `/search?query=...&top_k=5` — Semantic search (JSON)
- POST `/compare` — Form field `filenames`=list of filenames; returns JSON report
- GET `/ui/forms` — Dev UI to create drafts from ingested docs and CMM files
- GET `/ui/audit` — Dev UI to build audit evidence packs
- POST `/forms/as9102/draft` — body: `{doc_ids[], cmm_files[], form_levels[]}`
- POST `/forms/8d/draft` — body: `{ncr_json, doc_ids[]}`
- POST `/forms/export` — body: `{draft: <DraftBundle>, format: "docx"|"xlsx"|"all"}`
- POST `/audit/pack` — body: `{car_id|query, filters?, redaction?, max_items?}` → returns pack id + links
- GET `/audit/pack/{pack_id}/download` — download the ZIP
- GET `/audit/pack/{pack_id}/manifest` — manifest.json
 - POST `/lessons/search` — body: `{query, top_k}` → prior NCR/CAPA with actions + citations
 - GET `/lessons/clusters` — returns clusters with keyword labels
 - GET `/ui/lessons` — Dev UI to search lessons and apply to new 8D

Testing
- Run: `pytest -q`
- Includes unit test for revision/tolerance mismatch detection (DOCX-based)
 - Auto-Fill tests for extraction/merge/export and Audit Pack build test

Minimal Deps
- fastapi, uvicorn[standard], pdfminer.six, python-docx, numpy, jinja2
- openpyxl, pyyaml, rapidfuzz, pydantic
- Optional: faiss-cpu (if available). Falls back to NumPy search when missing.

Notes
- Tolerance extraction uses simple regex heuristics for `±x` or `+/- x` and may require tuning for your documents.
- PDF text extraction quality depends on the source file’s text layer.
