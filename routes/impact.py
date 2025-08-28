from __future__ import annotations

import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from impact.infer import build_brief, export_brief_docx, ImpactBrief
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/impact", tags=["impact"])
templates = Jinja2Templates(directory="templates")


@router.post("/brief")
async def impact_brief(payload: Dict[str, Any] = Body(None), eco_file: UploadFile | None = None):
    try:
        eco_text = ""
        if eco_file is not None:
            eco_text = (await eco_file.read()).decode("utf-8", errors="ignore")
        if payload and payload.get("eco_text"):
            eco_text = payload.get("eco_text") + ("\n" + eco_text if eco_text else "")
        if not eco_text:
            raise ValueError("Provide eco_text or upload a file")
        brief = build_brief(
            eco_text=eco_text,
            linked_docs=payload.get("linked_docs") if payload else None,
            effective_date=payload.get("effective_date") if payload else None,
            filters=payload.get("filters") if payload else None,
            max_items=int(payload.get("max_items", 50)) if payload else 50,
        )
        return JSONResponse(brief.__dict__)
    except Exception as e:
        logger.exception("impact_brief error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/brief/{brief_id}")
async def get_brief(brief_id: str):
    p = os.path.join("storage", "impact", f"brief_{brief_id}.json")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Brief not found")
    return FileResponse(p, media_type="application/json")


@router.post("/export/{brief_id}")
async def export_brief(brief_id: str, payload: Dict[str, Any] = Body(...)):
    p = os.path.join("storage", "impact", f"brief_{brief_id}.json")
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Brief not found")
    data = __import__('json').load(open(p, 'r', encoding='utf-8'))
    brief_dict = data.get('brief')
    if not brief_dict:
        raise HTTPException(status_code=400, detail="Malformed brief file")
    from impact.infer import ImpactItem, Citation

    # Rehydrate brief
    items = []
    for it in brief_dict.get('items', []):
        cits = [Citation(**c) for c in it.get('citations', [])]
        items.append(ImpactItem(
            asset_type=it['asset_type'], id=it['id'], title=it['title'], owner=it['owner'],
            impact_score=int(it['impact_score']), rationale=it['rationale'], suggested_action=it['suggested_action'], citations=cits
        ))
    brief = ImpactBrief(
        id=brief_dict['id'], created_at=brief_dict['created_at'], eco_summary=brief_dict['eco_summary'],
        effective_date=brief_dict.get('effective_date'), items=items,
        citations=[Citation(**c) for c in brief_dict.get('citations', [])], risk_note=brief_dict.get('risk_note',''),
        reviewer_list=brief_dict.get('reviewer_list', []), next_actions=brief_dict.get('next_actions','')
    )
    fmt = (payload or {}).get('format', 'docx')
    if fmt in ('docx','all'):
        out = export_brief_docx(brief, out_dir='exports')
        return JSONResponse({'exported': [os.path.basename(out)]})
    raise HTTPException(status_code=400, detail="Unsupported format in prototype")


@router.get("/ui", response_class=HTMLResponse)
async def impact_ui(request: Request):
    return templates.TemplateResponse("ui/impact.html", {"request": request})

