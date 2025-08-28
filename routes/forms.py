from __future__ import annotations

import os
from typing import Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from forms.autofill import DraftBundle, generate_as9102, generate_8d
from forms.exporter import export_draft
from ingest import Ingestor
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/forms", tags=["forms"])
templates = Jinja2Templates(directory="templates")


@router.post("/as9102/draft")
async def create_as9102_draft(payload: Dict = Body(...)):
    doc_ids: List[str] = payload.get("doc_ids", [])
    cmm_files: List[str] = payload.get("cmm_files", [])
    form_levels: List[str] = payload.get("form_levels", ["1", "2", "3"])
    try:
        bundle = generate_as9102(doc_ids=doc_ids, cmm_files=cmm_files, form_levels=form_levels)
        return JSONResponse(bundle.__dict__, media_type="application/json")
    except Exception as e:
        logger.exception("AS9102 draft error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/8d/draft")
async def create_8d_draft(payload: Dict = Body(...)):
    ncr = payload.get("ncr_json", {})
    doc_ids: List[str] = payload.get("doc_ids", [])
    lessons_ids = payload.get("lessons_from") or []
    lessons_query = payload.get("lessons_query")
    if payload.get("lessons") and not (lessons_ids or lessons_query):
        # Derive a query from NCR JSON if present
        parts = []
        if isinstance(ncr, dict):
            for k in ("symptom", "defect", "part", "lot"):
                v = ncr.get(k)
                if v:
                    parts.append(str(v))
        lessons_query = " ".join(parts) or None
    try:
        bundle = generate_8d(ncr_json=ncr, evidence_doc_ids=doc_ids, lessons_from=lessons_ids, lessons_query=lessons_query)
        return JSONResponse(bundle.__dict__, media_type="application/json")
    except Exception as e:
        logger.exception("8D draft error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/export")
async def export(payload: Dict = Body(...)):
    draft = payload.get("draft") or payload.get("bundle")
    fmt = payload.get("format", "docx")
    if not draft or not isinstance(draft, dict):
        raise HTTPException(status_code=400, detail="Expected 'draft' object in body")
    # Re-hydrate a minimal DraftBundle-like object for export
    from forms.autofill import DraftBundle as DB

    bundle = DB(**draft)
    outs = export_draft(bundle, out_dir="exports", fmt=fmt)
    return {"exported": [os.path.basename(p) for p in outs]}


@router.get("/ui", response_class=HTMLResponse)
async def forms_ui(request: Request):
    # Provide HTML page with upload and draft generator using JS
    ingestor = Ingestor()
    files = []
    for di in ingestor.doc_store.docs.values():
        files.append({"doc_id": di.doc_id, "filename": di.filename})
    return templates.TemplateResponse("ui/forms.html", {"request": request, "docs": files})


@router.post("/upload_cmm")
async def upload_cmm(files: List[UploadFile] = File(...)):
    saved = []
    os.makedirs("data/cmm", exist_ok=True)
    for uf in files:
        ext = os.path.splitext(uf.filename)[1].lower()
        if ext not in (".csv", ".xlsx", ".xlsm", ".xltx", ".xltm"):
            continue
        dest = os.path.join("data/cmm", os.path.basename(uf.filename))
        with open(dest, "wb") as f:
            f.write(await uf.read())
        saved.append(dest)
    return {"saved": [os.path.basename(p) for p in saved]}
