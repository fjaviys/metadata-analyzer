"""api/analysis.py — Lanzar y consultar análisis."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.exceptions import MetadataAnalyzerError
from database.db import get_db
from schemas.models import AnalysisRequest, AnalysisStarted
from services import analysis_service

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("", response_model=AnalysisStarted)
async def create_analysis(req: AnalysisRequest):
    try:
        session_id = await analysis_service.start_analysis(
            req.root_path, req.connection_type, req.max_depth, req.detect_duplicates,
            req.include_extensions, req.exclude_extensions)
    except MetadataAnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return AnalysisStarted(session_id=session_id, root_path=req.root_path)


@router.get("/sessions")
async def list_sessions(limit: int = 50):
    return {"sessions": get_db().list_sessions(limit=limit)}


@router.get("/sessions/{session_id}")
async def get_session(session_id: int):
    s = get_db().get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="sesión no encontrada")
    return s
