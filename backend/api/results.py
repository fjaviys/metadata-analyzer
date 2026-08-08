"""api/results.py — Resultados del análisis: resumen, ficheros, árbol, duplicados, PDF."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from database.db import get_db

router = APIRouter(prefix="/results", tags=["results"])


@router.get("/{session_id}/summary")
async def summary(session_id: int):
    s = get_db().get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="sesión no encontrada")
    return s


@router.get("/{session_id}/files")
async def files(session_id: int,
                needs_correction: bool | None = None,
                folder: str | None = None,
                limit: int = Query(500, le=5000),
                offset: int = 0):
    db = get_db()
    rows = db.get_files(session_id, needs_correction=needs_correction,
                        folder_prefix=folder, limit=limit, offset=offset)
    return {
        "total": db.count_files(session_id, needs_correction=needs_correction),
        "count": len(rows),
        "offset": offset,
        "files": rows,
    }


@router.get("/{session_id}/tree")
async def folder_tree(session_id: int):
    return {"tree": get_db().folder_tree(session_id)}


@router.get("/{session_id}/duplicates")
async def duplicates(session_id: int):
    return {"duplicates": get_db().get_duplicates(session_id)}


@router.get("/{session_id}/report")
async def report(session_id: int):
    s = get_db().get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="sesión no encontrada")
    path = s.get("report_path")
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="informe no disponible todavía")
    return FileResponse(path, media_type="application/pdf",
                        filename=os.path.basename(path))
