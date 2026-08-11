"""
services/reorganize_service.py — Orquesta la Fase 2: reorganizar carpetas por fecha.

Seguridad:
- Solo mueve ficheros con una fecha FIABLE (sesión o EXIF en vivo); nunca fabrica
  una fecha (un archivo sin fecha se omite y se reporta).
- La carpeta base "manual" y las subcarpetas seleccionadas se validan dentro de
  la raíz de la sesión (misma allowlist que la corrección).
- REAL requiere `confirm_real_write=True`; si falta, se rechaza
  (ConfirmationRequiredError). El dry-run está siempre disponible.
- Movimiento con REGISTRO (tabla reorganize_moves) para poder deshacer un run.
- Abort + deshacer si el ratio de errores supera el umbral (igual que la corrección).
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Optional

import bootstrap  # noqa: F401
from reorganize_engine import ReorganizeEngine, plan_reorganize, undo_run

from core.config import settings
from core.exceptions import ConfirmationRequiredError, MetadataAnalyzerError
from core.logger import get_logger
from core.security import validate_path, validate_subfolders
from database.db import get_db
from services.correction_service import _under_folder
from services.progress_hub import hub

log = get_logger("reorganize")


async def start_reorganize(session_id: int, subfolders: list[str], dry_run: bool,
                           confirm_real_write: bool, base_mode: str,
                           base_folder: Optional[str], layout: str,
                           date_source: str) -> dict:
    db = get_db()
    session = db.get_session(session_id)
    if not session:
        raise MetadataAnalyzerError(f"sesión {session_id} no encontrada")

    if not dry_run and not confirm_real_write:
        raise ConfirmationRequiredError(
            "Una reorganización REAL mueve tus archivos. Debes confirmar "
            "explícitamente (confirm_real_write=true). El modo dry-run está "
            "disponible para simular sin mover nada."
        )

    root = session["root"]
    real_base: Optional[str] = None
    if base_mode == "manual":
        if not base_folder:
            raise MetadataAnalyzerError("falta la carpeta base manual (base_folder)")
        real_base = validate_subfolders(root, [base_folder])[0]
    elif base_mode == "root":
        real_base = validate_path(root, must_exist=True)
    elif base_mode != "auto":
        raise MetadataAnalyzerError(f"base_mode inválido: {base_mode}")

    real_subs = validate_subfolders(root, subfolders) if subfolders else None
    rows = db.get_files(session_id, limit=1_000_000)
    if real_subs is not None:
        rows = [r for r in rows if any(_under_folder(r["path"], s) for s in real_subs)]

    plans = plan_reorganize(rows, base_mode, real_base, layout, date_source)
    run_id = uuid.uuid4().hex[:12]
    to_move = sum(1 for p in plans if p.action == "move")

    log.info(f"reorganización {'DRY-RUN' if dry_run else 'REAL'} run={run_id} "
             f"session={session_id} candidatos={to_move}")

    loop = asyncio.get_running_loop()
    asyncio.create_task(
        asyncio.to_thread(_run_reorganize_blocking, run_id, session_id, plans, dry_run, loop)
    )
    return {"run_id": run_id, "dry_run": dry_run, "total_candidates": to_move}


def _run_reorganize_blocking(run_id: str, session_id: int, plans, dry_run: bool, loop) -> None:
    db = get_db()
    channel = f"run:{run_id}"

    engine = ReorganizeEngine(
        db=db, session_id=session_id,
        error_abort_ratio=settings.correction_error_abort_ratio,
    )

    def progress_cb(ev: dict) -> None:
        ev = {**ev, "run_id": run_id, "phase": "reorganize", "dry_run": dry_run}
        hub.publish_threadsafe(loop, channel, ev)

    try:
        result = engine.run(plans, dry_run=dry_run, progress_cb=progress_cb, run_id=run_id)
        hub.publish_threadsafe(loop, channel, {
            "run_id": run_id, "phase": "reorganize", "status": "completed",
            "dry_run": dry_run, "processed": result.total, "total": result.total,
            "percent": 100.0, "moved": result.moved, "failed": result.failed,
            "skipped": result.skipped, "reverted": result.reverted,
            "planned": result.planned, "aborted": result.aborted,
            "abort_reason": result.abort_reason,
        })
        log.info(f"reorganización finalizada run={run_id} movidos={result.moved} "
                 f"fallidos={result.failed} abortado={result.aborted}")
    except Exception as e:  # noqa: BLE001
        log.error(f"reorganización fallida run={run_id}: {e}")
        hub.publish_threadsafe(loop, channel, {
            "run_id": run_id, "phase": "reorganize", "status": "failed", "error": str(e),
        })


def undo(run_id: str) -> dict:
    return undo_run(get_db(), run_id)
