"""
services/reorganize_service.py — Paso 2: reestructurar carpetas por fecha.

Independiente del paso de metadatos. UN ÚNICO patrón (`layout`) para todo el
análisis: cada archivo se agrupa por fecha dentro de su *raíz*, entendida como
la carpeta más profunda que lo contiene y que NO es íntegramente una fecha
(p. ej. 'vacaciones 2009' es raíz y se conserva; '2009/08/02' se pela). La
raíz analizada nunca se sobrepasa hacia arriba.

Seguridad:
- Solo mueve ficheros con una fecha FIABLE (sesión o EXIF en vivo); nunca
  fabrica una fecha (un archivo sin fecha se omite y se reporta).
- La carpeta base "manual" y las subcarpetas seleccionadas se validan dentro
  de la raíz de la sesión (misma allowlist que la corrección).
- REAL requiere `confirm_real_write=True`; si falta, se rechaza
  (ConfirmationRequiredError). El dry-run está siempre disponible.
- **Bloqueo por re-análisis**: si la sesión tiene alguna corrección REAL de
  metadatos aplicada, este paso se rechaza (NeedsReanalysisError) — hay que
  volver a analizar la carpeta antes de reestructurarla, porque los datos de
  la sesión pueden no reflejar ya lo que hay en disco.
- Movimiento con REGISTRO (tabla reorganize_moves) para poder deshacer un run.
- Abort + deshacer si el ratio de errores supera el umbral (igual que la
  corrección).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Optional

import bootstrap  # noqa: F401
from reorganize_engine import (
    ReorganizeEngine, ReorganizePlan, _unique_target, build_target_dir,
    compute_base_folder, resolve_row_date, undo_run,
)

from core.config import settings
from core.exceptions import ConfirmationRequiredError, MetadataAnalyzerError, NeedsReanalysisError
from core.logger import get_logger
from core.security import validate_path, validate_subfolders
from database.db import get_db
from services.correction_service import _under_folder
from services.progress_hub import hub

log = get_logger("reorganize")

def _resolve_base(root: str, base_mode: str, base_folder: Optional[str]) -> Optional[str]:
    if base_mode == "manual":
        if not base_folder:
            raise MetadataAnalyzerError("falta la carpeta base manual (base_folder)")
        return validate_subfolders(root, [base_folder])[0]
    if base_mode == "root":
        return validate_path(root, must_exist=True)
    if base_mode != "auto":
        raise MetadataAnalyzerError(f"base_mode inválido: {base_mode}")
    return None  # "auto": compute_base_folder calcula por archivo


def build_structure_plan(session_id: int, subfolders: list[str], root: str,
                         base_mode: str, base_folder: Optional[str],
                         layout: str, date_source: str = "session",
                         ) -> list[ReorganizePlan]:
    """
    Plan de movimiento con UN ÚNICO patrón para todo el análisis.

    La carpeta destino de cada archivo se cuelga de su *raíz*: la carpeta más
    profunda que lo contiene y que no es íntegramente una fecha (p. ej.
    'vacaciones 2009' sí es raíz; '2009/08/02' se pela). El pelado nunca sube
    por encima de la raíz analizada. Un archivo sin fecha fiable se omite y se
    reporta — nunca se fabrica una fecha.
    """
    db = get_db()
    all_rows = db.get_files(session_id, limit=1_000_000)
    real_subs = validate_subfolders(root, subfolders) if subfolders else None
    real_base = _resolve_base(root, base_mode, base_folder)

    plans: list[ReorganizePlan] = []
    reserved: set[str] = set()

    for row in all_rows:
        path = row["path"]
        if real_subs is not None and not any(_under_folder(path, s) for s in real_subs):
            continue

        base = compute_base_folder(path, stop_at=root) if base_mode == "auto" else real_base
        dt = resolve_row_date(row, date_source)
        if dt is None:
            plans.append(ReorganizePlan(path, "skip", reason="sin fecha fiable", base=base))
            continue
        if not base:
            plans.append(ReorganizePlan(path, "skip", reason="carpeta base vacía"))
            continue
        target_dir = build_target_dir(base, layout, dt)
        target = os.path.join(target_dir, os.path.basename(path))
        if os.path.abspath(target) == os.path.abspath(path):
            plans.append(ReorganizePlan(path, "skip", reason="ya está en la carpeta destino",
                                        base=base))
            continue
        target = _unique_target(target, reserved)
        reserved.add(target)
        plans.append(ReorganizePlan(
            path, "move", target=target, base=base,
            reason=f"fecha ({date_source}): {dt.date().isoformat()}"))

    return plans


async def start_reorganize(session_id: int, subfolders: list[str], dry_run: bool,
                           confirm_real_write: bool, base_mode: str,
                           base_folder: Optional[str], layout: str,
                           date_source: str) -> dict:
    db = get_db()
    session = db.get_session(session_id)
    if not session:
        raise MetadataAnalyzerError(f"sesión {session_id} no encontrada")

    if db.has_real_corrections(session_id):
        raise NeedsReanalysisError(
            "Esta sesión tiene correcciones reales de metadatos aplicadas. "
            "Vuelve a analizar la carpeta antes de reestructurarla: los datos "
            "de esta sesión pueden no reflejar ya lo que hay en disco."
        )

    if not dry_run and not confirm_real_write:
        raise ConfirmationRequiredError(
            "Una reorganización REAL mueve tus archivos. Debes confirmar "
            "explícitamente (confirm_real_write=true). El modo dry-run está "
            "disponible para simular sin mover nada."
        )

    root = session["root"]
    plans = build_structure_plan(session_id, subfolders, root, base_mode,
                                 base_folder, layout, date_source)
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


def preview(session_id: int, subfolders: list[str], base_mode: str,
           base_folder: Optional[str], layout: str, date_source: str = "session") -> dict:
    """Previsualización de solo lectura: nunca escribe ni mueve nada."""
    db = get_db()
    session = db.get_session(session_id)
    if not session:
        raise MetadataAnalyzerError(f"sesión {session_id} no encontrada")
    plans = build_structure_plan(session_id, subfolders, session["root"], base_mode,
                                 base_folder, layout, date_source)
    moves = []
    for p in plans:
        entry = {"path": p.path, "before_dir": os.path.dirname(p.path), "base_dir": p.base}
        if p.action == "move":
            entry.update({"after_dir": os.path.dirname(p.target), "reason": p.reason})
        else:
            entry["skip_reason"] = p.reason
        moves.append(entry)
    return {"moves": moves}
