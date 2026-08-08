"""
correction_engine.py — Corrección segura y transaccional de metadatos.

Principios (requisito crítico de seguridad):
  1. BACKUP antes de cualquier escritura.
  2. Escribir con exiftool y RE-LEER para VERIFICAR el resultado.
  3. Modo DRY-RUN: simula sin tocar el archivo.
  4. Registro por archivo (valor original y nuevo) en la BD.
  5. Si un archivo falla, continuar y registrar; si el ratio de errores supera un
     umbral (p. ej. 10%), ABORTAR y RESTAURAR lo ya aplicado desde backup.

Corrección "hasta donde se pueda llegar" según la precisión detectada:
  - Solo año        → YYYY-01-01 00:00:00
  - Año + mes       → YYYY-MM-01 00:00:00
  - Fecha sin hora  → YYYY-MM-DD 00:00:00
  - Con hora        → respeta la hora
Metadatos corruptos sin otra referencia → limpieza (borrar la fecha corrupta) para
no confundir a Immich; nunca se inventa una fecha.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import metadata_analyzer as ma

EXIFTOOL_BIN = os.getenv("EXIFTOOL_BIN", "exiftool")
DEFAULT_ERROR_ABORT_RATIO = float(os.getenv("CORRECTION_ERROR_ABORT_RATIO", "0.10"))

# tags de fecha que se escriben / limpian
PHOTO_DATE_TAGS = ["DateTimeOriginal", "CreateDate", "ModifyDate"]
VIDEO_DATE_TAGS = [
    "QuickTime:CreateDate", "QuickTime:ModifyDate",
    "TrackCreateDate", "TrackModifyDate",
    "MediaCreateDate", "MediaModifyDate",
]

BackupFn = Callable[[str], str]          # path -> backup_path
RestoreFn = Callable[[str, str], None]   # (backup_path, path) -> None
ProgressCb = Callable[[dict], None]


# --------------------------- backup por defecto -----------------------------

def make_backup_fn(backup_root: str) -> BackupFn:
    """Backup por copia preservando la ruta relativa bajo backup_root."""
    os.makedirs(backup_root, exist_ok=True)

    def _bk(path: str) -> str:
        rel = os.path.abspath(path).lstrip(os.sep)
        dest = os.path.join(backup_root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)
        return dest

    return _bk


def default_restore_fn(backup_path: str, path: str) -> None:
    shutil.copy2(backup_path, path)


# --------------------------- plan de corrección -----------------------------

@dataclass
class CorrectionPlan:
    path: str
    action: str                      # "set_date" | "cleanup" | "skip"
    media_type: str = "photo"
    target: Optional[str] = None     # string EXIF 'YYYY:MM:DD HH:MM:SS'
    precision: str = "NONE"
    source: Optional[str] = None
    original_value: Optional[str] = None
    original_tag: Optional[str] = None
    reason: str = ""

    @property
    def tags(self) -> list[str]:
        base = PHOTO_DATE_TAGS.copy()
        if self.media_type == "video":
            base = base + VIDEO_DATE_TAGS
        return base


def plan_from_file(row: dict) -> CorrectionPlan:
    """
    Construye el plan a partir de una fila de análisis (dict con las claves de
    FileMetadata.as_dict() o de analyzed_files).
    """
    path = row.get("path")
    media_type = row.get("media_type") or "photo"
    original_value = row.get("exif_date")
    original_tag = row.get("exif_date_tag")

    if not row.get("needs_correction"):
        return CorrectionPlan(path, "skip", media_type,
                              original_value=original_value, original_tag=original_tag,
                              reason="no requiere corrección")

    source = row.get("recommended_source")
    target = row.get("recommended_date")
    precision = row.get("recommended_precision") or "NONE"

    if source == "cleanup" or (row.get("is_corrupt") and not target):
        return CorrectionPlan(path, "cleanup", media_type,
                              original_value=original_value, original_tag=original_tag,
                              reason="fecha corrupta sin referencia fiable")

    if target:
        return CorrectionPlan(path, "set_date", media_type, target=target,
                              precision=precision, source=source,
                              original_value=original_value, original_tag=original_tag,
                              reason=f"fecha recomendada por {source}")

    return CorrectionPlan(path, "skip", media_type,
                          original_value=original_value, original_tag=original_tag,
                          reason="sin fecha recomendada")


# --------------------------- escritura + verificación -----------------------

def _exiftool_write(path: str, plan: CorrectionPlan) -> tuple[bool, str]:
    """Ejecuta exiftool. Devuelve (ok, mensaje). No hace backup ni verifica."""
    if plan.action == "set_date":
        args = [f"-{t}={plan.target}" for t in plan.tags]
    elif plan.action == "cleanup":
        args = [f"-{t}=" for t in plan.tags]
    else:
        return True, "skip"
    cmd = [EXIFTOOL_BIN, "-overwrite_original", "-P", *args, path]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout).strip()[:300]
    return True, proc.stdout.strip()


def _verify(path: str, plan: CorrectionPlan) -> tuple[bool, str]:
    """Re-lee el archivo y comprueba que el cambio se aplicó."""
    try:
        batch = ma.run_exiftool([path])
    except RuntimeError as e:
        return False, f"verificación: no se pudo releer ({e})"
    tags = batch[0] if batch else {}

    if plan.action == "set_date":
        got = tags.get("DateTimeOriginal") or tags.get("CreateDate")
        got_dt = ma.parse_exif_datetime(got)
        want_dt = ma.parse_exif_datetime(plan.target)
        if got_dt is not None and want_dt is not None and got_dt == want_dt:
            return True, f"verificado: {got}"
        return False, f"verificación fallida: esperado {plan.target}, leído {got}"

    if plan.action == "cleanup":
        remaining = tags.get("DateTimeOriginal") or tags.get("CreateDate")
        rem_dt = ma.parse_exif_datetime(remaining)
        # limpieza correcta si ya no hay fecha o dejó de estar fuera de rango
        if rem_dt is None or ma._date_in_range(rem_dt):
            return True, "verificado: fecha corrupta eliminada"
        return False, f"verificación fallida: aún hay fecha corrupta {remaining}"

    return True, "skip"


# --------------------------- resultado de la ejecución ----------------------

@dataclass
class CorrectionRunResult:
    run_id: str
    dry_run: bool
    total: int = 0
    planned: int = 0        # con acción real (no skip)
    applied: int = 0
    verified: int = 0
    failed: int = 0
    skipped: int = 0
    reverted: int = 0
    aborted: bool = False
    abort_reason: Optional[str] = None
    details: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


# --------------------------- motor ------------------------------------------

class CorrectionEngine:
    def __init__(
        self,
        backup_fn: Optional[BackupFn] = None,
        restore_fn: RestoreFn = default_restore_fn,
        db=None,
        session_id: Optional[int] = None,
        error_abort_ratio: float = DEFAULT_ERROR_ABORT_RATIO,
        min_files_for_ratio: int = 5,
    ):
        self.backup_fn = backup_fn
        self.restore_fn = restore_fn
        self.db = db
        self.session_id = session_id
        self.error_abort_ratio = error_abort_ratio
        self.min_files_for_ratio = min_files_for_ratio

    def _record(self, run_id: str, plan: CorrectionPlan, dry_run: bool,
                status: str, new_value: Optional[str], backup_path: Optional[str],
                error: Optional[str], verified: bool) -> None:
        if self.db is None:
            return
        self.db.insert_correction({
            "session_id": self.session_id,
            "run_id": run_id,
            "path": plan.path,
            "dry_run": 1 if dry_run else 0,
            "correction_type": plan.action,
            "tag": plan.original_tag or "DateTimeOriginal",
            "original_value": plan.original_value,
            "new_value": new_value,
            "precision": plan.precision,
            "source": plan.source,
            "status": status,
            "verified": 1 if verified else 0,
            "backup_path": backup_path,
            "error": error,
        })

    def run(
        self,
        files: list[dict],
        dry_run: bool = True,
        progress_cb: Optional[ProgressCb] = None,
        run_id: Optional[str] = None,
    ) -> CorrectionRunResult:
        run_id = run_id or uuid.uuid4().hex[:12]
        res = CorrectionRunResult(run_id=run_id, dry_run=dry_run, total=len(files))
        applied_backups: list[tuple[str, str]] = []   # (backup_path, path) para restore

        if not dry_run and self.backup_fn is None:
            raise ValueError("backup_fn es obligatorio para correcciones reales (no dry-run)")

        for idx, row in enumerate(files, start=1):
            plan = plan_from_file(row)

            if plan.action == "skip":
                res.skipped += 1
                self._record(run_id, plan, dry_run, "skipped", None, None, None, False)
                res.details.append({"path": plan.path, "action": "skip",
                                    "status": "skipped", "reason": plan.reason})
                self._emit(progress_cb, res, idx, plan, "skipped")
                continue

            res.planned += 1

            # ---- DRY-RUN: simular, no escribir ----
            if dry_run:
                res.applied += 1  # "aplicado en simulación"
                new_value = plan.target if plan.action == "set_date" else "(eliminar fecha)"
                self._record(run_id, plan, True, "dry-run", new_value, None, None, False)
                res.details.append({
                    "path": plan.path, "action": plan.action, "status": "dry-run",
                    "original": plan.original_value, "new": new_value,
                    "precision": plan.precision, "source": plan.source,
                    "reason": plan.reason,
                })
                self._emit(progress_cb, res, idx, plan, "dry-run")
                continue

            # ---- REAL: backup -> escribir -> verificar ----
            backup_path = None
            try:
                backup_path = self.backup_fn(plan.path)
            except Exception as e:  # noqa: BLE001
                res.failed += 1
                self._record(run_id, plan, False, "failed", None, None,
                             f"backup: {e}", False)
                res.details.append({"path": plan.path, "action": plan.action,
                                    "status": "failed", "error": f"backup: {e}"})
                self._emit(progress_cb, res, idx, plan, "failed")
                if self._should_abort(res):
                    self._abort_and_restore(res, applied_backups, run_id)
                    break
                continue

            ok, msg = _exiftool_write(plan.path, plan)
            if not ok:
                res.failed += 1
                self._record(run_id, plan, False, "failed", None, backup_path, msg, False)
                res.details.append({"path": plan.path, "action": plan.action,
                                    "status": "failed", "error": msg})
                self._emit(progress_cb, res, idx, plan, "failed")
                if self._should_abort(res):
                    self._abort_and_restore(res, applied_backups, run_id)
                    break
                continue

            # escrito: candidato a restaurar si luego abortamos
            applied_backups.append((backup_path, plan.path))
            res.applied += 1

            vok, vmsg = _verify(plan.path, plan)
            new_value = plan.target if plan.action == "set_date" else "(eliminada)"
            if vok:
                res.verified += 1
                self._record(run_id, plan, False, "verified", new_value, backup_path,
                             None, True)
                res.details.append({"path": plan.path, "action": plan.action,
                                    "status": "verified", "original": plan.original_value,
                                    "new": new_value, "message": vmsg})
                self._emit(progress_cb, res, idx, plan, "verified")
            else:
                # escribió pero no verifica: restaurar ESTE archivo de inmediato
                res.failed += 1
                try:
                    self.restore_fn(backup_path, plan.path)
                    applied_backups.pop()  # ya restaurado
                    status = "reverted"
                    res.reverted += 1
                except Exception as e:  # noqa: BLE001
                    status = "failed"
                    vmsg = f"{vmsg}; restore falló: {e}"
                self._record(run_id, plan, False, status, new_value, backup_path,
                             vmsg, False)
                res.details.append({"path": plan.path, "action": plan.action,
                                    "status": status, "error": vmsg})
                self._emit(progress_cb, res, idx, plan, status)
                if self._should_abort(res):
                    self._abort_and_restore(res, applied_backups, run_id)
                    break

        return res

    # ---- ayudas ----
    def _should_abort(self, res: CorrectionRunResult) -> bool:
        done = res.applied + res.failed
        if done < self.min_files_for_ratio:
            return False
        return (res.failed / max(done, 1)) > self.error_abort_ratio

    def _abort_and_restore(self, res: CorrectionRunResult,
                           applied_backups: list[tuple[str, str]], run_id: str) -> None:
        res.aborted = True
        res.abort_reason = (
            f"ratio de errores {res.failed}/{res.applied + res.failed} supera el "
            f"umbral {self.error_abort_ratio:.0%}; restaurando cambios aplicados"
        )
        for backup_path, path in reversed(applied_backups):
            try:
                self.restore_fn(backup_path, path)
                res.reverted += 1
                if self.db is not None:
                    for c in self.db.get_corrections(run_id=run_id):
                        if c["path"] == path and c["status"] == "verified":
                            self.db.update_correction(c["id"], status="reverted")
            except Exception:  # noqa: BLE001
                pass

    def _emit(self, cb, res, idx, plan, status):
        if cb is None:
            return
        cb({
            "current_file": plan.path,
            "processed": idx,
            "total": res.total,
            "action": plan.action,
            "status": status,
            "verified": res.verified,
            "failed": res.failed,
            "aborted": res.aborted,
            "percent": round(idx / res.total * 100, 1) if res.total else 100.0,
        })


__all__ = [
    "CorrectionEngine", "CorrectionPlan", "CorrectionRunResult",
    "plan_from_file", "make_backup_fn", "default_restore_fn",
]
