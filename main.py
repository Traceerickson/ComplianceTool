from __future__ import annotations

import os
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, Form, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from compare import compare_documents
from ingest import Ingestor
from search import SearchEngine
from utils.logger import get_logger
from routes.forms import router as forms_router
from routes.audit import router as audit_router

logger = get_logger(__name__)

app = FastAPI(title="AI Compliance Copilot")

templates = Jinja2Templates(directory="templates")
os.makedirs("data/uploads", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("packs", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="data/uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/packs", StaticFiles(directory="packs", check_dir=False), name="packs")
app.include_router(forms_router)
app.include_router(audit_router)

_ingestor = Ingestor()
_search = SearchEngine()


@app.get("/")
async def index(request: Request):
    files = []
    for root, _dirs, fnames in os.walk("data"):
        for fn in fnames:
            if os.path.splitext(fn)[1].lower() in (".pdf", ".docx", ".doc", ".txt", ".text"):
                files.append(fn)
    files = sorted(set(files))
    return templates.TemplateResponse("index.html", {"request": request, "files": files})

@app.get("/ui/forms")
async def ui_forms(request: Request):
    # Delegate to forms router template for consistency
    from ingest import Ingestor
    ingestor = Ingestor()
    files = []
    for di in ingestor.doc_store.docs.values():
        files.append({"doc_id": di.doc_id, "filename": di.filename})
    return templates.TemplateResponse("ui/forms.html", {"request": request, "docs": files})

@app.get("/ui/audit")
async def ui_audit(request: Request):
    ingestor = Ingestor()
    files = []
    for di in ingestor.doc_store.docs.values():
        files.append({"doc_id": di.doc_id, "filename": di.filename})
    return templates.TemplateResponse("ui/audit.html", {"request": request, "docs": files})


@app.post("/upload")
async def upload(files: List[UploadFile] = File(...)):
    saved = []
    for uf in files:
        ext = os.path.splitext(uf.filename)[1].lower()
        if ext not in (".pdf", ".docx", ".doc", ".txt", ".text"):
            continue
        dest = os.path.join("data/uploads", os.path.basename(uf.filename))
        with open(dest, "wb") as f:
            f.write(await uf.read())
        saved.append(dest)
        # Ingest immediately
        try:
            _ingestor.ingest_file(dest)
        except Exception as e:
            logger.exception("Failed to ingest %s: %s", dest, e)
    return JSONResponse({"saved": [os.path.basename(p) for p in saved]})


@app.get("/search")
async def search(query: str, top_k: int = 5):
    results = _search.search(query, top_k=top_k)
    return JSONResponse({"query": query, "results": results})


@app.post("/compare")
async def compare(filenames: List[str] = Form(...)):
    report = compare_documents(filenames)
    return JSONResponse(report)


@app.post("/compare_ui")
async def compare_ui(request: Request, filenames: List[str] = Form(...)):
    report = compare_documents(filenames)
    files = []
    for root, _dirs, fnames in os.walk("data"):
        for fn in fnames:
            if os.path.splitext(fn)[1].lower() in (".pdf", ".docx", ".doc", ".txt", ".text"):
                files.append(fn)
    files = sorted(set(files))
    return templates.TemplateResponse(
        "index.html", {"request": request, "files": files, "report": report, "selected": filenames}
    )
