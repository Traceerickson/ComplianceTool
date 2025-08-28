from __future__ import annotations

import os
from typing import Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Request, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from services.audit_pack import build_audit_pack
from ingest import Ingestor
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])
templates = Jinja2Templates(directory="templates")


@router.post("/pack")
async def create_pack(payload: Dict = Body(...)):
    try:
        car_id = payload.get("car_id")
        query = payload.get("query")
        filters = payload.get("filters") or {}
        include_forms = bool(payload.get("include_forms", True))
        include_compare = bool(payload.get("include_compare_results", False))
        redaction = payload.get("redaction") or {}
        max_items = int(payload.get("max_items", 30))

        result = build_audit_pack(
            created_by=payload.get("created_by", "dev"),
            car_id=car_id,
            query=query,
            filters=filters,
            include_forms=include_forms,
            include_compare_results=include_compare,
            redaction=redaction,
            max_items=max_items,
        )
        pack_id = result["pack_id"]
        return JSONResponse(
            {
                "pack_id": pack_id,
                "zip_url": f"/audit/pack/{pack_id}/download",
                "index_url": f"/packs/{pack_id}/index.html",
                "manifest_url": f"/audit/pack/{pack_id}/manifest",
                "counts": result.get("counts", {}),
            }
        )
    except Exception as e:
        logger.exception("Audit pack error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/pack/{pack_id}/download")
async def download_pack(pack_id: str):
    zip_path = os.path.join("packs", f"{pack_id}.zip")
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail="Pack not found")
    return FileResponse(zip_path, filename=f"audit_pack_{pack_id}.zip")


@router.get("/pack/{pack_id}/manifest")
async def get_manifest(pack_id: str):
    p = os.path.join("packs", pack_id, "manifest.json")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Manifest not found")
    return FileResponse(p, media_type="application/json")


@router.get("/ui", response_class=HTMLResponse)
async def audit_ui(request: Request):
    ing = Ingestor()
    files = [{"doc_id": di.doc_id, "filename": di.filename} for di in ing.doc_store.docs.values()]
    return templates.TemplateResponse("ui/audit.html", {"request": request, "docs": files})

