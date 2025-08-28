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

Endpoints
- GET `/` — Minimal UI (Jinja2) for upload + compare
- POST `/upload` — Upload 1–many files (PDF/DOCX/TXT), immediate ingest
- GET `/search?query=...&top_k=5` — Semantic search (JSON)
- POST `/compare` — Form field `filenames`=list of filenames; returns JSON report

Testing
- Run: `pytest -q`
- Includes unit test for revision/tolerance mismatch detection (DOCX-based)

Minimal Deps
- fastapi, uvicorn[standard], pdfminer.six, python-docx, numpy, jinja2
- Optional: faiss-cpu (if available). Falls back to NumPy search when missing.

Notes
- Tolerance extraction uses simple regex heuristics for `±x` or `+/- x` and may require tuning for your documents.
- PDF text extraction quality depends on the source file’s text layer.

