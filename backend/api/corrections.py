"""api/corrections.py — Lanzar correcciones (dry-run / real) y consultar su estado."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from core.exceptions import ConfirmationRequiredError, MetadataAnalyzerError
from database.db import get_db
from schemas.models import CorrectionRequest, CorrectionStarted
from services import correction_service

router = APIRouter(prefix="/corrections", tags=["corrections"])


@router.post("", response_model=CorrectionStarted)
async def create_correction(req: CorrectionRequest):
    try:
        res = await correction_service.start_correction(
            req.session_id, req.subfolders, req.dry_run, req.confirm_real_write)
    except ConfirmationRequiredError as e:
        # 428: se requiere confirmación explícita para escritura real
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except MetadataAnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    return CorrectionStarted(**res)


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
