"""
services/correction_service.py — Orquesta la corrección de metadatos.

Seguridad:
- Solo actúa sobre ficheros marcados `needs_correction` de la sesión.
- Valida subcarpetas seleccionadas dentro de la raíz de la sesión.
- REAL requiere `confirm_real_write=True`; si no, se rechaza
  (ConfirmationRequiredError). El dry-run está siempre disponible.
- Backup previo por run (core/backup) y abort+restore si el ratio de errores
  supera el umbral (lo gestiona correction_engine).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import bootstrap  # noqa: F401
import pattern_parser as pp
from correction_engine import CorrectionEngine

from core.config import settings
from core.backup import BackupManager
from core.exceptions import ConfirmationRequiredError, MetadataAnalyzerError
from core.logger import get_logger, log_correction
from core.security import validate_subfolders
from database.db import get_db
from services.progress_hub import hub

log = get_logger("correction")


def _under_folder(path: str, folder: str) -> bool:
    """True si `path` (archivo) está dentro de `folder` a CUALQUIER nivel."""
    folder = folder.rstrip(os.sep)
    # el archivo está bajo la carpeta si su directorio es la carpeta o un descendiente
    return path == folder or path.startswith(folder + os.sep)


def _candidates(session_id: int, subfolders: list[str], root: str) -> list[dict]:
    """
    Candidatos a corregir. Una subcarpeta seleccionada incluye TODAS sus
    subcarpetas y archivos a cualquier nivel de profundidad (recursivo).
    Sin selección → todos los archivos de la sesión que requieren corrección.
    """
    db = get_db()
    all_rows = db.get_files(session_id, needs_correction=True, limit=1_000_000)
    if not subfolders:
        return all_rows
    real_subs = validate_subfolders(root, subfolders)
    seen: dict[str, dict] = {}
    for row in all_rows:
        if any(_under_folder(row["path"], sub) for sub in real_subs):
            seen[row["path"]] = row
    return list(seen.values())


def apply_overrides(session_id: int, rows: list[dict]) -> list[dict]:
    """
    Aplica los overrides de patrón de la sesión a las filas indicadas: recalcula
    la fecha propuesta de cada archivo bajo una carpeta con override (el override
    más profundo gana). Modifica y devuelve las filas.
    """
    overrides = get_db().get_overrides(session_id)   # más profundos primero
    if not overrides:
        return rows
    for row in rows:
        for ov in overrides:
            if _under_folder(row["path"], ov["folder"]):
                det = pp.resolve(row["path"], ov["pattern"], ov.get("source", "auto"))
                if det and det.is_valid:
                    row["recommended_date"] = det.to_exif_string()
                    row["recommended_precision"] = det.precision.label
                    row["recommended_source"] = "override"
                    row["needs_correction"] = True
                break
    return rows


async def start_correction(session_id: int, subfolders: list[str],
                           dry_run: bool, confirm_real_write: bool) -> dict:
    """
    Prepara y lanza la corrección. Devuelve {run_id, dry_run, total_candidates}.
    Lanza ConfirmationRequiredError si es REAL sin confirmación.
    """
    db = get_db()
    session = db.get_session(session_id)
    if not session:
        raise MetadataAnalyzerError(f"sesión {session_id} no encontrada")

    if not dry_run and not confirm_real_write:
        raise ConfirmationRequiredError(
            "Una corrección REAL escribe sobre tus archivos. Debes confirmar "
            "explícitamente (confirm_real_write=true). El modo dry-run está "
            "disponible para simular sin escribir."
        )

    root = session["root"]
    candidates = _candidates(session_id, subfolders, root)
    candidates = apply_overrides(session_id, candidates)
    run_id = uuid.uuid4().hex[:12]

    log.info(f"corrección {'DRY-RUN' if dry_run else 'REAL'} run={run_id} "
             f"session={session_id} candidatos={len(candidates)}")

    loop = asyncio.get_running_loop()
    asyncio.create_task(
        asyncio.to_thread(_run_correction_blocking, run_id, session_id,
                          candidates, dry_run, loop)
    )
    return {"run_id": run_id, "dry_run": dry_run, "total_candidates": len(candidates)}


def _run_correction_blocking(run_id: str, session_id: int, candidates: list[dict],
                             dry_run: bool, loop) -> None:
    db = get_db()
    channel = f"run:{run_id}"

    backup_fn = None
    if not dry_run:
        bm = BackupManager()
        run = bm.new_run(run_id)
        backup_fn = run.backup_fn

    engine = CorrectionEngine(
        backup_fn=backup_fn,
        db=db,
        session_id=session_id,
        error_abort_ratio=settings.correction_error_abort_ratio,
    )

    def progress_cb(ev: dict) -> None:
        ev = {**ev, "run_id": run_id, "phase": "correction", "dry_run": dry_run}
        hub.publish_threadsafe(loop, channel, ev)

    try:
        result = engine.run(candidates, dry_run=dry_run, progress_cb=progress_cb,
                            run_id=run_id)
        # log estructurado por archivo
        for d in result.details:
            log_correction(d.get("path", ""), d.get("action", ""),
                          d.get("original"), d.get("new"), d.get("status", ""),
                          dry_run, error=d.get("error"))
        hub.publish_threadsafe(loop, channel, {
            "run_id": run_id, "phase": "correction", "status": "completed",
            "dry_run": dry_run, "processed": result.total, "total": result.total,
            "percent": 100.0, "verified": result.verified, "failed": result.failed,
            "skipped": result.skipped, "reverted": result.reverted,
            "applied": result.applied, "planned": result.planned,
            "aborted": result.aborted, "abort_reason": result.abort_reason,
        })
        log.info(f"corrección finalizada run={run_id} verificados={result.verified} "
                 f"fallidos={result.failed} abortado={result.aborted}")
    except Exception as e:  # noqa: BLE001
        log.error(f"corrección fallida run={run_id}: {e}")
        hub.publish_threadsafe(loop, channel, {
            "run_id": run_id, "phase": "correction", "status": "failed",
            "error": str(e),
        })
