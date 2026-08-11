"""api/corrections.py — Correcciones (dry-run / real), estado y overrides de patrón."""

from __future__ import annotations

import bootstrap  # noqa: F401
import pattern_parser as pp
from fastapi import APIRouter, HTTPException, Query

from core.exceptions import ConfirmationRequiredError, MetadataAnalyzerError
from core.security import validate_subfolders
from database.db import get_db
from schemas.models import CorrectionRequest, CorrectionStarted, OverrideRequest
from services import correction_service
from services.correction_service import _under_folder, override_correction

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


# --- Patrones de override (deben ir ANTES de /{run_id}) ---------------------

@router.get("/pattern-presets")
async def pattern_presets():
    return {"presets": pp.PRESETS}


@router.post("/overrides")
async def create_override(req: OverrideRequest):
    db = get_db()
    session = db.get_session(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="sesión no encontrada")

    # resolver preset o patrón crudo
    preset = pp.preset_by_key(req.pattern)
    pattern = preset["pattern"] if preset else req.pattern
    source = preset["source"] if preset else req.source
    if pattern != pp.DAYMONTH_FOLDERYEAR:
        try:
            pp.compile_pattern(pattern)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"patrón inválido: {e}")

    # validar carpeta dentro de la raíz de la sesión
    try:
        real_folder = validate_subfolders(session["root"], [req.folder])[0]
    except MetadataAnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    override_id = db.add_override(req.session_id, real_folder, pattern, source)

    # previsualización: TODOS los archivos bajo la carpeta (incluye "rescatados"),
    # aplicando la misma lógica que en la corrección (idempotencia incluida).
    ov = {"folder": real_folder, "pattern": pattern, "source": source}
    files = db.get_files(req.session_id, limit=1_000_000)
    affected, rescued, preview = 0, 0, []
    for f in files:
        if not _under_folder(f["path"], real_folder):
            continue
        was_marked = bool(f.get("needs_correction"))
        old = f.get("exif_date") or f.get("recommended_date")
        if override_correction(f, ov):
            affected += 1
            if not was_marked:
                rescued += 1
            if len(preview) < 20:
                preview.append({
                    "path": f["path"], "old": old,
                    "new": f["recommended_date"],
                    "precision": f["recommended_precision"],
                    "rescued": not was_marked,
                })
    return {"id": override_id, "folder": real_folder, "pattern": pattern,
            "source": source, "affected": affected, "rescued": rescued,
            "preview": preview}


@router.get("/overrides")
async def list_overrides(session_id: int):
    return {"overrides": get_db().get_overrides(session_id)}


@router.delete("/overrides/{override_id}")
async def delete_override(override_id: int):
    get_db().delete_override(override_id)
    return {"deleted": override_id}


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
