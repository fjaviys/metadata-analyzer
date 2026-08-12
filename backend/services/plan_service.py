"""
services/plan_service.py — Fase 3: árbol de asignación unificado.

Combina, por archivo, dos ejes INDEPENDIENTES:
  - metadatos:  ¿se corrige el EXIF?  cascada file_overrides > path_overrides >
                análisis, con `folder_decisions.metadata_mode == 'keep'` como
                interruptor adicional que excluye el archivo de la corrección
                (salvo que un file_override explícito lo fuerce).
  - estructura: ¿se mueve el archivo? cascada de `folder_decisions` por
                profundidad de carpeta (default 'keep' = no se mueve nada).
                Usa siempre `resolve_row_date(row, "session")` para decidir la
                carpeta destino — es la "mejor fecha conocida" según la sesión,
                se escriba o no en el EXIF (decisión confirmada con el usuario).

No reimplementa los motores: construye las listas de entrada para
`CorrectionEngine` y `ReorganizeEngine` (ya probados en Fases 1 y 2) y los
ejecuta en secuencia dentro del mismo run_id — metadatos primero, luego mover.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Optional

import bootstrap  # noqa: F401
from correction_engine import CorrectionEngine
from reorganize_engine import (
    ReorganizeEngine, ReorganizePlan, _unique_target, build_target_dir,
    compute_base_folder, resolve_row_date, undo_run,
)

from core.backup import BackupManager
from core.config import settings
from core.exceptions import ConfirmationRequiredError, MetadataAnalyzerError
from core.logger import get_logger
from core.security import validate_path, validate_subfolders
from database.db import get_db
from services.correction_service import (
    _override_for, _under_folder, file_override_result, override_correction,
)
from services.progress_hub import hub

log = get_logger("plan")

_DEFAULT_FOLDER_DECISION = {"metadata_mode": "update", "structure_mode": "keep",
                            "structure_layout": None}


def _folder_decision_for(path: str, decisions: list[dict]) -> dict:
    """Decisión efectiva: la carpeta más profunda que contiene `path` gana."""
    for d in decisions:  # ya vienen ordenadas por profundidad de carpeta desc
        if _under_folder(path, d["folder"]):
            return d
    return _DEFAULT_FOLDER_DECISION


def _resolve_base(root: str, base_mode: str, base_folder: Optional[str]) -> Optional[str]:
    """Valida y devuelve la carpeta base real según `base_mode` (auto/root/manual)."""
    if base_mode == "manual":
        if not base_folder:
            raise MetadataAnalyzerError("falta la carpeta base manual (base_folder)")
        return validate_subfolders(root, [base_folder])[0]
    if base_mode == "root":
        return validate_path(root, must_exist=True)
    if base_mode != "auto":
        raise MetadataAnalyzerError(f"base_mode inválido: {base_mode}")
    return None  # "auto": build_unified_plan calcula compute_base_folder por archivo


def build_unified_plan(session_id: int, subfolders: list[str], root: str,
                       base_mode: str, base_folder: Optional[str], default_layout: str,
                       ) -> tuple[list[dict], list[ReorganizePlan]]:
    """Construye las dos listas de trabajo (metadatos, estructura) para un ámbito."""
    db = get_db()
    path_overrides = db.get_overrides(session_id)            # detección, más profundas primero
    file_ovs = {fo["path"]: fo for fo in db.get_file_overrides(session_id)}
    folder_decisions = db.get_folder_decisions(session_id)   # más profundas primero
    all_rows = db.get_files(session_id, limit=1_000_000)
    real_subs = validate_subfolders(root, subfolders) if subfolders else None

    correction_rows: list[dict] = []
    reorganize_plans: list[ReorganizePlan] = []
    reserved: set[str] = set()

    for row in all_rows:
        path = row["path"]
        if real_subs is not None and not any(_under_folder(path, s) for s in real_subs):
            continue

        # --- cascada de la fecha "conocida" (independiente de si se escribe) ---
        fo = file_ovs.get(path)
        file_result = file_override_result(row, fo) if fo else None
        if file_result is None:
            ov = _override_for(path, path_overrides)
            if ov is not None:
                override_correction(row, ov)

        fdec = _folder_decision_for(path, folder_decisions)

        # --- eje metadatos: ¿se escribe? ---
        if file_result == "set":
            write_metadata = True
        elif file_result == "skip":
            write_metadata = False
        else:
            write_metadata = fdec["metadata_mode"] != "keep" and bool(row.get("needs_correction"))
        if write_metadata:
            correction_rows.append(row)

        # --- eje estructura: ¿se mueve? ---
        if fdec["structure_mode"] == "update":
            dt = resolve_row_date(row, "session")
            if dt is None:
                reorganize_plans.append(ReorganizePlan(
                    path, "skip", reason="sin fecha fiable (ni sesión ni EXIF)"))
                continue
            base = compute_base_folder(path) if base_mode == "auto" else base_folder
            if not base:
                reorganize_plans.append(ReorganizePlan(path, "skip", reason="carpeta base vacía"))
                continue
            layout = fdec["structure_layout"] or default_layout
            target_dir = build_target_dir(base, layout, dt)
            target = os.path.join(target_dir, os.path.basename(path))
            if os.path.abspath(target) == os.path.abspath(path):
                reorganize_plans.append(ReorganizePlan(
                    path, "skip", reason="ya está en la carpeta destino"))
                continue
            target = _unique_target(target, reserved)
            reserved.add(target)
            reorganize_plans.append(ReorganizePlan(
                path, "move", target=target,
                reason=f"fecha (session): {dt.date().isoformat()}"))

    return correction_rows, reorganize_plans


def build_preview(session_id: int, subfolders: list[str], base_mode: str,
                  base_folder: Optional[str], layout: str) -> dict:
    """
    Previsualización de solo lectura: reutiliza `build_unified_plan` (pura, no
    escribe nada) y la serializa para la UI. Nunca requiere confirmación —
    no mueve ni escribe ningún archivo.
    """
    db = get_db()
    session = db.get_session(session_id)
    if not session:
        raise MetadataAnalyzerError(f"sesión {session_id} no encontrada")

    root = session["root"]
    real_base = _resolve_base(root, base_mode, base_folder)
    correction_rows, reorganize_plans = build_unified_plan(
        session_id, subfolders, root, base_mode, real_base, layout)

    corrections = [
        {"path": r["path"], "before": r.get("exif_date"), "after": r.get("recommended_date")}
        for r in correction_rows
    ]
    moves = []
    for p in reorganize_plans:
        if p.action == "move":
            moves.append({"path": p.path, "before_dir": os.path.dirname(p.path),
                          "after_dir": os.path.dirname(p.target), "reason": p.reason})
        else:
            moves.append({"path": p.path, "skip_reason": p.reason})
    return {"corrections": corrections, "moves": moves}


async def start_unified_run(session_id: int, subfolders: list[str], dry_run: bool,
                            confirm_real_write: bool, base_mode: str,
                            base_folder: Optional[str], layout: str) -> dict:
    db = get_db()
    session = db.get_session(session_id)
    if not session:
        raise MetadataAnalyzerError(f"sesión {session_id} no encontrada")

    if not dry_run and not confirm_real_write:
        raise ConfirmationRequiredError(
            "Aplicar cambios REALES escribe metadatos y/o mueve tus archivos. Debes "
            "confirmar explícitamente (confirm_real_write=true). El modo dry-run está "
            "disponible para simular sin tocar nada."
        )

    root = session["root"]
    real_base = _resolve_base(root, base_mode, base_folder)

    correction_rows, reorganize_plans = build_unified_plan(
        session_id, subfolders, root, base_mode, real_base, layout)

    run_id = uuid.uuid4().hex[:12]
    to_correct = len(correction_rows)
    to_move = sum(1 for p in reorganize_plans if p.action == "move")

    log.info(f"plan {'DRY-RUN' if dry_run else 'REAL'} run={run_id} session={session_id} "
             f"metadatos={to_correct} estructura={to_move}")

    loop = asyncio.get_running_loop()
    asyncio.create_task(
        asyncio.to_thread(_run_unified_blocking, run_id, session_id,
                          correction_rows, reorganize_plans, dry_run, loop)
    )
    return {"run_id": run_id, "dry_run": dry_run,
            "total_candidates": to_correct + to_move,
            "metadata_candidates": to_correct, "structure_candidates": to_move}


def _run_unified_blocking(run_id: str, session_id: int, correction_rows: list[dict],
                          reorganize_plans: list, dry_run: bool, loop) -> None:
    db = get_db()
    channel = f"run:{run_id}"

    backup_fn = None
    if not dry_run and correction_rows:
        bm = BackupManager()
        run = bm.new_run(run_id)
        backup_fn = run.backup_fn

    correction_result = None
    if correction_rows:
        engine = CorrectionEngine(backup_fn=backup_fn, db=db, session_id=session_id,
                                  error_abort_ratio=settings.correction_error_abort_ratio)

        def corr_progress_cb(ev: dict) -> None:
            hub.publish_threadsafe(loop, channel, {
                **ev, "run_id": run_id, "phase": "correction", "dry_run": dry_run})

        try:
            correction_result = engine.run(correction_rows, dry_run=dry_run,
                                           progress_cb=corr_progress_cb, run_id=run_id)
        except Exception as e:  # noqa: BLE001
            log.error(f"fase metadatos fallida run={run_id}: {e}")
            hub.publish_threadsafe(loop, channel, {
                "run_id": run_id, "phase": "correction", "status": "failed", "error": str(e)})
            return

    reorganize_result = None
    if reorganize_plans:
        r_engine = ReorganizeEngine(db=db, session_id=session_id,
                                    error_abort_ratio=settings.correction_error_abort_ratio)

        def reorg_progress_cb(ev: dict) -> None:
            hub.publish_threadsafe(loop, channel, {
                **ev, "run_id": run_id, "phase": "reorganize", "dry_run": dry_run})

        try:
            reorganize_result = r_engine.run(reorganize_plans, dry_run=dry_run,
                                             progress_cb=reorg_progress_cb, run_id=run_id)
        except Exception as e:  # noqa: BLE001
            log.error(f"fase estructura fallida run={run_id}: {e}")
            hub.publish_threadsafe(loop, channel, {
                "run_id": run_id, "phase": "reorganize", "status": "failed", "error": str(e)})
            return

    total = (correction_result.total if correction_result else 0) + \
        (reorganize_result.total if reorganize_result else 0)
    aborted = bool((correction_result and correction_result.aborted) or
                   (reorganize_result and reorganize_result.aborted))
    hub.publish_threadsafe(loop, channel, {
        "run_id": run_id, "phase": "plan", "status": "completed", "dry_run": dry_run,
        "processed": total, "total": total, "percent": 100.0, "aborted": aborted,
        "verified": correction_result.verified if correction_result else 0,
        "applied": correction_result.applied if correction_result else 0,
        "metadata_failed": correction_result.failed if correction_result else 0,
        "moved": reorganize_result.moved if reorganize_result else 0,
        "structure_failed": reorganize_result.failed if reorganize_result else 0,
    })
    log.info(f"plan finalizado run={run_id} metadatos_verificados="
             f"{correction_result.verified if correction_result else 0} "
             f"movidos={reorganize_result.moved if reorganize_result else 0} "
             f"abortado={aborted}")


def undo(run_id: str) -> dict:
    return undo_run(get_db(), run_id)
