"""api/plan.py — Fase 3: árbol de asignación unificado (metadatos + estructura)."""

from __future__ import annotations

import bootstrap  # noqa: F401
from fastapi import APIRouter, HTTPException, Query

from core.exceptions import ConfirmationRequiredError, MetadataAnalyzerError
from database.db import get_db
from schemas.models import (
    FolderDecisionRequest, PlanPreviewRequest, UnifiedRunRequest, UnifiedRunStarted,
)
from services import plan_service

router = APIRouter(prefix="/plan", tags=["plan"])


@router.post("/run", response_model=UnifiedRunStarted)
async def create_run(req: UnifiedRunRequest):
    try:
        res = await plan_service.start_unified_run(
            req.session_id, req.subfolders, req.dry_run, req.confirm_real_write,
            req.base_mode, req.base_folder, req.layout)
    except ConfirmationRequiredError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except MetadataAnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return UnifiedRunStarted(**res)


@router.post("/preview")
async def preview_run(req: PlanPreviewRequest):
    """Previsualización de solo lectura (sin confirmación): nunca escribe ni mueve nada."""
    try:
        return plan_service.build_preview(
            req.session_id, req.subfolders, req.base_mode, req.base_folder, req.layout)
    except MetadataAnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))


# --- decisiones por carpeta (rutas literales ANTES de /run/{run_id}) --------

@router.get("/folder-decisions")
async def list_folder_decisions(session_id: int):
    return {"decisions": get_db().get_folder_decisions(session_id)}


@router.post("/folder-decision")
async def set_folder_decision(req: FolderDecisionRequest):
    db = get_db()
    if not db.get_session(req.session_id):
        raise HTTPException(status_code=404, detail="sesión no encontrada")
    fields: dict = {}
    if req.metadata_mode is not None:
        fields["metadata_mode"] = req.metadata_mode
    if req.structure_mode is not None:
        fields["structure_mode"] = req.structure_mode
    if req.clear_structure_layout:
        fields["structure_layout"] = None
    elif req.structure_layout is not None:
        fields["structure_layout"] = req.structure_layout
    did = db.set_folder_decision(req.session_id, req.folder, **fields)
    return {"id": did, **db.get_folder_decision(req.session_id, req.folder)}


@router.delete("/folder-decision")
async def delete_folder_decision(session_id: int, folder: str):
    get_db().delete_folder_decision(session_id, folder)
    return {"deleted": folder}


@router.get("/run/{run_id}")
async def get_run(run_id: str,
                  only_changes: bool = False,
                  limit: int = Query(500, le=5000),
                  offset: int = 0):
    db = get_db()
    corrections = db.get_corrections(run_id=run_id, only_changes=only_changes,
                                     limit=limit, offset=offset)
    moves = db.get_reorganize_moves(run_id=run_id, only_changes=only_changes,
                                    limit=limit, offset=offset)
    return {
        "run_id": run_id,
        "metadata": {
            "stats": db.correction_stats(run_id),
            "total": db.count_corrections(run_id, only_changes=only_changes),
            "count": len(corrections),
            "rows": corrections,
        },
        "structure": {
            "stats": db.reorganize_stats(run_id),
            "total": db.count_reorganize_moves(run_id, only_changes=only_changes),
            "count": len(moves),
            "rows": moves,
        },
        "offset": offset,
    }


@router.post("/run/{run_id}/undo")
async def undo_run(run_id: str):
    return plan_service.undo(run_id)
