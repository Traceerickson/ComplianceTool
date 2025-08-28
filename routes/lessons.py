from __future__ import annotations

from typing import Dict

from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from lessons.search import search_lessons, ingest_lessons
from lessons.cluster_lessons import compute_clusters, get_clusters
from utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/lessons", tags=["lessons"])
templates = Jinja2Templates(directory="templates")


@router.post("/search")
async def lessons_search(payload: Dict = Body(...)):
    try:
        query = payload.get("query")
        top_k = int(payload.get("top_k", 10))
        if not query:
            raise ValueError("Missing 'query'")
        # Ensure lessons are indexed at least once
        ingest_lessons()
        results = search_lessons(query, top_k=top_k)
        logger.info("lessons_search query='%s' results=%d", query, len(results))
        return JSONResponse({"results": results})
    except Exception as e:
        logger.exception("lessons_search error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/clusters")
async def lessons_clusters():
    try:
        data = get_clusters()
        return JSONResponse(data)
    except Exception as e:
        logger.exception("lessons_clusters error: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/ui", response_class=HTMLResponse)
async def lessons_ui(request: Request):
    return templates.TemplateResponse("ui/lessons.html", {"request": request})

