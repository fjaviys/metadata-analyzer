"""
reorganize_engine.py — Fase 2: reorganiza archivos en carpetas por fecha, SIN
tocar metadatos (eso ya lo hace correction_engine.py).

Principios (mismo requisito crítico de seguridad que la corrección):
  1. Nunca se fabrica una fecha: un archivo sin fecha fiable (ni de sesión ni de
     EXIF en vivo) se OMITE y se reporta, nunca se mueve a ciegas.
  2. Mover con REGISTRO (tabla reorganize_moves) para poder deshacer un run real.
  3. Colisión de destino -> renombrado automático con sufijo (_1, _2…); nunca se
     sobrescribe ni se pierde un archivo.
  4. Cross-device (EXDEV, distinto filesystem): copia + verifica tamaño + borra
     el original, en vez de fallar.
  5. Modo DRY-RUN siempre disponible (no mueve nada, solo calcula el plan).
  6. Abort + deshacer si el ratio de errores supera el umbral (igual que la
     corrección).
"""

from __future__ import annotations

import errno
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import metadata_analyzer as ma
from date_detector import _detect_component

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _component_is_date_like(comp: str) -> bool:
    """True si un nombre de carpeta parece parte de una fecha (año/mes/día o
    fecha embebida compacta), para poder "pelarlo" al calcular la carpeta base."""
    if _YEAR_RE.match(comp):
        return True
    if re.fullmatch(r"\d{1,2}", comp):
        return 1 <= int(comp) <= 31
    return _detect_component(comp).is_valid


def compute_base_folder(path: str) -> str:
    """
    Pela automáticamente las subcarpetas de fecha desde la más profunda hacia
    arriba, deteniéndose en la primera carpeta que NO parezca fecha. P. ej.
    'fotos/2009/08/02/IMG.jpg' -> carpeta base 'fotos'.
    """
    directory = os.path.dirname(path).replace("\\", "/")
    is_abs = directory.startswith("/")
    parts = [p for p in directory.split("/") if p]
    while parts and _component_is_date_like(parts[-1]):
        parts.pop()
    result = "/".join(parts)
    return ("/" + result) if is_abs else result


# --------------------------- layout de carpetas destino ----------------------

_LAYOUT_TOKEN_RE = re.compile(r"AAAA|AA|MM|DD|hh|mm|ss")
_LAYOUT_FORMATTERS: dict[str, Callable[[datetime], str]] = {
    "AAAA": lambda dt: f"{dt.year:04d}",
    "AA": lambda dt: f"{dt.year % 100:02d}",
    "MM": lambda dt: f"{dt.month:02d}",
    "DD": lambda dt: f"{dt.day:02d}",
    "hh": lambda dt: f"{dt.hour:02d}",
    "mm": lambda dt: f"{dt.minute:02d}",
    "ss": lambda dt: f"{dt.second:02d}",
}

LAYOUT_PRESETS: list[dict] = [
    {"key": "y_m", "label": "AAAA/MM", "layout": "AAAA/MM"},
    {"key": "y_m_d", "label": "AAAA/MM/DD", "layout": "AAAA/MM/DD"},
    {"key": "ym_dash", "label": "AAAA-MM (una sola carpeta)", "layout": "AAAA-MM"},
    {"key": "y", "label": "AAAA (solo año)", "layout": "AAAA"},
]


def format_layout(layout: str, dt: datetime) -> str:
    """Sustituye los tokens del layout por los valores de `dt`. '/' crea subcarpetas."""
    return _LAYOUT_TOKEN_RE.sub(lambda m: _LAYOUT_FORMATTERS[m.group(0)](dt), layout)


def build_target_dir(base_folder: str, layout: str, dt: datetime) -> str:
    sub = format_layout(layout, dt)
    return os.path.join(base_folder, *[p for p in sub.split("/") if p])


def _unique_target(target_path: str, reserved: set[str]) -> str:
    """Si `target_path` colisiona (en disco o con otro movimiento de este run),
    añade un sufijo _1, _2… antes de la extensión (nunca sobrescribe)."""
    if not os.path.exists(target_path) and target_path not in reserved:
        return target_path
    root, ext = os.path.splitext(target_path)
    i = 1
    while True:
        cand = f"{root}_{i}{ext}"
        if not os.path.exists(cand) and cand not in reserved:
            return cand
        i += 1


# --------------------------- fuente de la fecha -------------------------------

def _default_live_reader(path: str) -> Optional[str]:
    """Re-lee el EXIF del archivo AHORA (por si ya se corrigió)."""
    try:
        batch = ma.run_exiftool([path])
    except RuntimeError:
        return None
    tags = batch[0] if batch else {}
    for tag in ("DateTimeOriginal", "CreateDate", "CreationDate", "MediaCreateDate"):
        if tags.get(tag):
            return tags[tag]
    return None


def resolve_row_date(row: dict, date_source: str,
                     live_reader: Optional[Callable[[str], Optional[str]]] = None) -> Optional[datetime]:
    """
    Resuelve la fecha a usar para reorganizar según `date_source`:
      - "session":   la recomendada de la sesión (si needs_correction) o el
                     EXIF ya registrado en el análisis.
      - "exif_live": re-lee el EXIF del archivo AHORA.
    Nunca fabrica una fecha: si no hay ninguna fiable, devuelve None (se omite).
    """
    exif_str = None
    if date_source == "exif_live":
        reader = live_reader or _default_live_reader
        exif_str = reader(row["path"])
    else:
        if row.get("needs_correction") and row.get("recommended_date"):
            exif_str = row["recommended_date"]
        elif row.get("has_exif_date") and row.get("exif_date"):
            exif_str = row["exif_date"]
    if not exif_str:
        return None
    return ma.parse_exif_datetime(exif_str)


# --------------------------- plan ---------------------------------------------

@dataclass
class ReorganizePlan:
    path: str
    action: str                     # "move" | "skip"
    target: Optional[str] = None
    reason: str = ""


def plan_reorganize(rows: list[dict], base_mode: str, base_folder: Optional[str],
                    layout: str, date_source: str,
                    live_reader: Optional[Callable[[str], Optional[str]]] = None,
                    ) -> list[ReorganizePlan]:
    """
    Construye el plan de movimiento para `rows`.
      - base_mode "auto":   carpeta base calculada por archivo (compute_base_folder).
      - base_mode "root"/"manual": usa `base_folder` para todos los archivos.
    """
    plans: list[ReorganizePlan] = []
    reserved: set[str] = set()
    for row in rows:
        path = row["path"]
        dt = resolve_row_date(row, date_source, live_reader)
        if dt is None:
            plans.append(ReorganizePlan(
                path, "skip", reason="sin fecha fiable (ni sesión ni EXIF en vivo)"))
            continue

        base = compute_base_folder(path) if base_mode == "auto" else base_folder
        if not base:
            plans.append(ReorganizePlan(path, "skip", reason="carpeta base vacía"))
            continue

        target_dir = build_target_dir(base, layout, dt)
        target = os.path.join(target_dir, os.path.basename(path))
        if os.path.abspath(target) == os.path.abspath(path):
            plans.append(ReorganizePlan(path, "skip", reason="ya está en la carpeta destino"))
            continue

        target = _unique_target(target, reserved)
        reserved.add(target)
        plans.append(ReorganizePlan(path, "move", target=target,
                                    reason=f"fecha ({date_source}): {dt.date().isoformat()}"))
    return plans


# --------------------------- mover con fallback EXDEV -------------------------

def _do_move(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.rename(src, dst)
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
        shutil.copy2(src, dst)
        if os.path.getsize(dst) != os.path.getsize(src):
            os.remove(dst)
            raise OSError("verificación de tamaño falló tras copiar entre dispositivos (EXDEV)")
        os.remove(src)


MoveFn = Callable[[str, str], None]
ProgressCb = Callable[[dict], None]


@dataclass
class ReorganizeRunResult:
    run_id: str
    dry_run: bool
    total: int = 0
    planned: int = 0     # con acción "move" (no skip)
    moved: int = 0
    failed: int = 0
    skipped: int = 0
    reverted: int = 0
    aborted: bool = False
    abort_reason: Optional[str] = None
    details: list[dict] = field(default_factory=list)


class ReorganizeEngine:
    def __init__(
        self,
        db=None,
        session_id: Optional[int] = None,
        error_abort_ratio: float = 0.10,
        min_files_for_ratio: int = 5,
        move_fn: MoveFn = _do_move,
    ):
        self.db = db
        self.session_id = session_id
        self.error_abort_ratio = error_abort_ratio
        self.min_files_for_ratio = min_files_for_ratio
        self.move_fn = move_fn

    def _record(self, run_id: str, path: str, new_path: Optional[str], dry_run: bool,
                status: str, reason: str, error: Optional[str]) -> None:
        if self.db is None:
            return
        self.db.insert_reorganize_move({
            "session_id": self.session_id, "run_id": run_id, "original_path": path,
            "new_path": new_path, "dry_run": 1 if dry_run else 0, "status": status,
            "reason": reason, "error": error,
        })

    def run(
        self,
        plans: list[ReorganizePlan],
        dry_run: bool = True,
        progress_cb: Optional[ProgressCb] = None,
        run_id: Optional[str] = None,
    ) -> ReorganizeRunResult:
        run_id = run_id or uuid.uuid4().hex[:12]
        res = ReorganizeRunResult(run_id=run_id, dry_run=dry_run, total=len(plans))
        done_moves: list[tuple[str, str]] = []   # (new_path, original_path) para deshacer

        for idx, plan in enumerate(plans, start=1):
            if plan.action == "skip":
                res.skipped += 1
                self._record(run_id, plan.path, None, dry_run, "skipped", plan.reason, None)
                res.details.append({"path": plan.path, "status": "skipped", "reason": plan.reason})
                self._emit(progress_cb, res, idx, plan, "skipped")
                continue

            res.planned += 1

            if dry_run:
                res.moved += 1
                self._record(run_id, plan.path, plan.target, True, "dry-run", plan.reason, None)
                res.details.append({"path": plan.path, "new_path": plan.target,
                                    "status": "dry-run", "reason": plan.reason})
                self._emit(progress_cb, res, idx, plan, "dry-run")
                continue

            try:
                self.move_fn(plan.path, plan.target)
                res.moved += 1
                done_moves.append((plan.target, plan.path))
                self._record(run_id, plan.path, plan.target, False, "moved", plan.reason, None)
                res.details.append({"path": plan.path, "new_path": plan.target, "status": "moved"})
                self._emit(progress_cb, res, idx, plan, "moved")
            except OSError as e:
                res.failed += 1
                self._record(run_id, plan.path, plan.target, False, "failed", plan.reason, str(e))
                res.details.append({"path": plan.path, "new_path": plan.target,
                                    "status": "failed", "error": str(e)})
                self._emit(progress_cb, res, idx, plan, "failed")
                if self._should_abort(res):
                    self._abort_and_restore(res, done_moves, run_id)
                    break

        return res

    # ---- ayudas ----
    def _should_abort(self, res: ReorganizeRunResult) -> bool:
        done = res.moved + res.failed
        if done < self.min_files_for_ratio:
            return False
        return (res.failed / max(done, 1)) > self.error_abort_ratio

    def _abort_and_restore(self, res: ReorganizeRunResult,
                           done_moves: list[tuple[str, str]], run_id: str) -> None:
        res.aborted = True
        res.abort_reason = (
            f"ratio de errores {res.failed}/{res.moved + res.failed} supera el "
            f"umbral {self.error_abort_ratio:.0%}; deshaciendo movimientos aplicados"
        )
        for new_path, original_path in reversed(done_moves):
            try:
                self.move_fn(new_path, original_path)
                res.reverted += 1
                if self.db is not None:
                    for m in self.db.get_reorganize_moves(run_id=run_id):
                        if m["original_path"] == original_path and m["status"] == "moved":
                            self.db.update_reorganize_move(m["id"], status="reverted")
            except OSError:
                pass

    def _emit(self, cb, res, idx, plan, status):
        if cb is None:
            return
        cb({
            "current_file": plan.path,
            "processed": idx,
            "total": res.total,
            "status": status,
            "moved": res.moved,
            "failed": res.failed,
            "aborted": res.aborted,
            "percent": round(idx / res.total * 100, 1) if res.total else 100.0,
        })


def undo_run(db, run_id: str, move_fn: MoveFn = _do_move) -> dict:
    """Deshace un run REAL: mueve cada archivo movido de vuelta a su ruta original."""
    moves = [m for m in db.get_reorganize_moves(run_id=run_id) if m["status"] == "moved"]
    undone, failed = 0, []
    for m in reversed(moves):
        try:
            move_fn(m["new_path"], m["original_path"])
            db.update_reorganize_move(m["id"], status="reverted")
            undone += 1
        except OSError as e:
            failed.append({"path": m["new_path"], "error": str(e)})
    return {"undone": undone, "failed": failed}


__all__ = [
    "ReorganizeEngine", "ReorganizePlan", "ReorganizeRunResult",
    "compute_base_folder", "build_target_dir", "format_layout", "plan_reorganize",
    "resolve_row_date", "undo_run", "LAYOUT_PRESETS",
]
