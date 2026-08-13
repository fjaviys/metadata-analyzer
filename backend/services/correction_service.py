"""
services/correction_service.py — Orquesta la corrección de metadatos (Paso 1).

Modelo (simplificado, Fase 4): por archivo, una decisión explícita
(`file_overrides.kind`):
  - 'keep'      -> no se toca (comportamiento por defecto si no hay decisión;
                   nunca se corrige nada sin que el usuario lo pida).
  - 'filename'  -> fecha detectada en el NOMBRE de archivo.
  - 'folder'    -> fecha detectada en la CARPETA contenedora.
En ambos casos se re-detecta con `date_detector` (mismo cálculo que hizo el
análisis para `filename_date`/`path_date`) para tener la precisión exacta. Si
esa fuente no tiene fecha para el archivo, se omite: nunca se fabrica una.

Seguridad: REAL requiere `confirm_real_write=True` (si no,
ConfirmationRequiredError); el dry-run está siempre disponible. Backup previo
por run y abort+restore por ratio de error (lo gestiona correction_engine).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import bootstrap  # noqa: F401
import date_detector as dd
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


_DETECTORS = {"filename": dd.detect_from_filename, "folder": dd.detect_from_path}


def build_metadata_candidates(session_id: int, subfolders: list[str], root: str) -> list[dict]:
    """
    Candidatos a corregir según la decisión explícita de cada archivo. Sin
    decisión (o 'keep') no se toca. 'filename'/'folder' re-detectan la fecha
    con `date_detector` sobre esa fuente; si no hay fecha, se omite.
    """
    db = get_db()
    file_ovs = {fo["path"]: fo for fo in db.get_file_overrides(session_id)}
    all_rows = db.get_files(session_id, limit=1_000_000)
    real_subs = validate_subfolders(root, subfolders) if subfolders else None

    out: list[dict] = []
    for row in all_rows:
        path = row["path"]
        if real_subs is not None and not any(_under_folder(path, s) for s in real_subs):
            continue
        fo = file_ovs.get(path)
        if fo is None or fo["kind"] == "keep":
            continue
        detector = _DETECTORS.get(fo["kind"])
        det = detector(path) if detector else None
        if det is None or not det.is_valid:
            continue  # esa fuente no tiene fecha para este archivo: se omite
        new_value = det.to_exif_string()
        if row.get("has_exif_date") and row.get("exif_date") == new_value:
            continue  # idempotente: ya coincide
        row["recommended_date"] = new_value
        row["recommended_precision"] = det.precision.label
        row["recommended_source"] = fo["kind"]
        row["needs_correction"] = 1
        out.append(row)
    return out


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
    candidates = build_metadata_candidates(session_id, subfolders, root)
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
