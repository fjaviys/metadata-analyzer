"""api/reorganize.py — Paso 2 (Estructura): reestructurar carpetas por fecha."""

from __future__ import annotations

import bootstrap  # noqa: F401
from reorganize_engine import LAYOUT_PRESETS
from fastapi import APIRouter, HTTPException, Query

from core.exceptions import ConfirmationRequiredError, MetadataAnalyzerError, NeedsReanalysisError
from database.db import get_db
from schemas.models import (
    ReorganizePreviewRequest, ReorganizeRequest, ReorganizeStarted,
)
from services import reorganize_service

router = APIRouter(prefix="/reorganize", tags=["reorganize"])


@router.post("", response_model=ReorganizeStarted)
async def create_reorganize(req: ReorganizeRequest):
    try:
        res = await reorganize_service.start_reorganize(
            req.session_id, req.subfolders, req.dry_run, req.confirm_real_write,
            req.base_mode, req.base_folder, req.layout, req.date_source)
    except ConfirmationRequiredError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except NeedsReanalysisError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except MetadataAnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return ReorganizeStarted(**res)


@router.post("/preview")
async def preview_reorganize(req: ReorganizePreviewRequest):
    """Previsualización de solo lectura (sin gate ni confirmación): nunca mueve nada."""
    try:
        return reorganize_service.preview(
            req.session_id, req.subfolders, req.base_mode, req.base_folder,
            req.layout, req.date_source)
    except MetadataAnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


# --- rutas literales ANTES de /{run_id} ---

@router.get("/layout-presets")
async def layout_presets():
    return {"presets": LAYOUT_PRESETS}


@router.get("/runs")
async def list_runs(session_id: int):
    return {"runs": get_db().list_reorganize_runs(session_id)}


@router.get("/gate")
async def gate(session_id: int):
    """¿Puede reestructurarse esta sesión, o hace falta volver a analizar antes?"""
    db = get_db()
    if not db.get_session(session_id):
        raise HTTPException(status_code=404, detail="sesión no encontrada")
    blocked = db.has_real_corrections(session_id)
    return {"blocked": blocked,
            "reason": ("Esta sesión tiene correcciones reales de metadatos aplicadas; "
                      "vuelve a analizar la carpeta antes de reestructurarla.")
                     if blocked else None}


@router.get("/{run_id}")
async def get_run(run_id: str,
                  only_changes: bool = False,
                  limit: int = Query(500, le=5000),
                  offset: int = 0):
    db = get_db()
    moves = db.get_reorganize_moves(run_id=run_id, only_changes=only_changes,
                                    limit=limit, offset=offset)
    return {
        "run_id": run_id,
        "stats": db.reorganize_stats(run_id),
        "total": db.count_reorganize_moves(run_id, only_changes=only_changes),
        "count": len(moves),
        "offset": offset,
        "moves": moves,
    }


@router.post("/{run_id}/undo")
async def undo_run(run_id: str):
    return reorganize_service.undo(run_id)
