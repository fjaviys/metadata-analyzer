"""api/corrections.py — Paso 1 (Metadatos): dry-run/real y decisión por archivo."""

from __future__ import annotations

import bootstrap  # noqa: F401
from fastapi import APIRouter, HTTPException, Query

from core.exceptions import ConfirmationRequiredError, MetadataAnalyzerError
from database.db import get_db
from schemas.models import CorrectionRequest, CorrectionStarted, FileOverrideRequest
from services import correction_service

router = APIRouter(prefix="/corrections", tags=["corrections"])


@router.post("", response_model=CorrectionStarted)
async def create_correction(req: CorrectionRequest):
    try:
        res = await correction_service.start_correction(
            req.session_id, req.subfolders, req.dry_run, req.confirm_real_write)
    except ConfirmationRequiredError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except MetadataAnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return CorrectionStarted(**res)


# --- Decisión por archivo (rutas literales ANTES de /{run_id}) --------------

@router.post("/file-overrides")
async def create_file_override(req: FileOverrideRequest):
    db = get_db()
    row = db.get_file(req.session_id, req.path)
    if not row:
        raise HTTPException(status_code=404, detail="archivo no encontrado en la sesión")

    if req.kind in ("filename", "folder"):
        column = "filename_date" if req.kind == "filename" else "path_date"
        if not row.get(column):
            raise HTTPException(
                status_code=400,
                detail=f"no hay fecha detectada en {'el nombre' if req.kind == 'filename' else 'la carpeta'} "
                       "para este archivo")

    oid = db.set_file_override(req.session_id, req.path, req.kind)
    return {"id": oid, "path": req.path, "kind": req.kind}


@router.get("/file-overrides")
async def list_file_overrides(session_id: int):
    return {"file_overrides": get_db().get_file_overrides(session_id)}


@router.delete("/file-overrides")
async def delete_file_override(session_id: int, path: str):
    get_db().delete_file_override(session_id, path)
    return {"deleted": path}


@router.get("/{run_id}")
async def get_run(run_id: str,
                  only_changes: bool = False,
                  limit: int = Query(500, le=5000),
                  offset: int = 0):
    db = get_db()
    corrs = db.get_corrections(run_id=run_id, only_changes=only_changes,
                               limit=limit, offset=offset)
    return {
        "run_id": run_id,
        "stats": db.correction_stats(run_id),
        "total": db.count_corrections(run_id, only_changes=only_changes),
        "count": len(corrs),
        "offset": offset,
        "corrections": corrs,
    }
