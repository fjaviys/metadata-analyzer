"""
services/analysis_service.py — Orquesta el análisis de una carpeta.

- Valida la ruta (core/security).
- Ejecuta metadata_analyzer.analyze_folder en un hilo, emitiendo progreso al
  ProgressHub (canal session:<id>).
- Detecta duplicados por hash.
- Persiste sesión + ficheros + duplicados en SQLite.
- Genera el informe PDF (report_generator).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections import defaultdict
from datetime import datetime

import bootstrap  # noqa: F401
import date_detector as dd
import metadata_analyzer as ma
import report_generator as rg

from core.config import settings
from core.logger import get_logger
from core.security import check_walk_depth, validate_path
from database.db import get_db
from services.progress_hub import hub

log = get_logger("analysis")


def _hash_file(path: str, chunk: int = 1 << 20, limit: int = 64 << 20) -> str | None:
    """Hash rápido (SHA-256 de hasta `limit` bytes + tamaño) para duplicados."""
    try:
        h = hashlib.sha256()
        size = os.path.getsize(path)
        h.update(str(size).encode())
        read = 0
        with open(path, "rb") as f:
            while read < limit:
                b = f.read(chunk)
                if not b:
                    break
                h.update(b)
                read += len(b)
        return h.hexdigest()
    except OSError:
        return None


def _folder_levels(root: str, path: str) -> tuple[str, str]:
    return ma._folder_levels(root, path)


async def start_analysis(root_path: str, connection_type: str = "local",
                         max_depth: int | None = None,
                         detect_duplicates: bool = True,
                         include_extensions: list[str] | None = None,
                         exclude_extensions: list[str] | None = None) -> int:
    """Valida, crea la sesión y lanza el análisis en background. Devuelve session_id."""
    real_root = validate_path(root_path, require_write=False, must_exist=True)
    allowed_exts = ma.resolve_extensions(include_extensions, exclude_extensions)
    db = get_db()
    session_id = db.create_session(real_root, connection_type,
                                   detector_version=dd.DETECTOR_VERSION)
    log.info(f"análisis iniciado session={session_id} root={real_root} "
             f"formatos={len(allowed_exts)}")

    loop = asyncio.get_running_loop()
    asyncio.create_task(
        asyncio.to_thread(_run_analysis_blocking, session_id, real_root,
                          max_depth, detect_duplicates, allowed_exts, loop)
    )
    return session_id


def _run_analysis_blocking(session_id: int, root: str, max_depth: int | None,
                           detect_duplicates: bool, allowed_exts, loop) -> None:
    """Se ejecuta en un hilo (to_thread). Publica progreso de forma thread-safe."""
    db = get_db()
    channel = f"session:{session_id}"
    hashes: dict[str, list[tuple[str, int]]] = defaultdict(list)

    def progress_cb(ev: dict) -> None:
        ev = {**ev, "session_id": session_id, "phase": "analysis"}
        hub.publish_threadsafe(loop, channel, ev)

    try:
        max_depth = max_depth if max_depth is not None else settings.max_walk_depth
        result = ma.analyze_folder(root, max_depth=max_depth,
                                   progress_cb=progress_cb, keep_files=True,
                                   allowed_exts=allowed_exts)

        # persistir ficheros + preparar duplicados
        rows = []
        for fm in result.files:
            l1, l2 = _folder_levels(root, fm.path)
            content_hash = _hash_file(fm.path) if detect_duplicates else None
            if content_hash:
                hashes[content_hash].append((fm.path, fm.size_bytes))
            rows.append((fm, l1, l2, content_hash))
        db.insert_files_bulk(session_id, rows)

        # duplicados
        dup_count = 0
        if detect_duplicates:
            for h, items in hashes.items():
                if len(items) > 1:
                    db.insert_duplicate_group(session_id, h, items, keep_index=0)
                    dup_count += len(items)
            db.update_session_duplicates(session_id, dup_count)

        # informe PDF
        summary = result.summary_dict()
        report_path = os.path.join(
            settings.report_dir, f"informe_session_{session_id}.pdf")
        try:
            rg.generate_report(
                summary, result.level1_folders, result.level2_folders,
                report_path, root=root,
                precision_breakdown=result.precision_breakdown,
                duplicates_count=dup_count,
            )
        except Exception as e:  # noqa: BLE001
            log.error(f"fallo generando PDF session={session_id}: {e}")
            report_path = None

        db.finish_session(session_id, summary, status="completed",
                          report_path=report_path)
        hub.publish_threadsafe(loop, channel, {
            "session_id": session_id, "phase": "analysis", "status": "completed",
            "processed": result.total_files, "total": result.total_files,
            "percent": 100.0, "needs_correction": result.needs_correction,
            "duplicates": dup_count, "report_path": report_path,
        })
        log.info(f"análisis completado session={session_id} "
                 f"total={result.total_files} corregir={result.needs_correction}")

    except Exception as e:  # noqa: BLE001
        log.error(f"análisis fallido session={session_id}: {e}")
        db.finish_session(session_id, {}, status="failed", error=str(e))
        hub.publish_threadsafe(loop, channel, {
            "session_id": session_id, "phase": "analysis", "status": "failed",
            "error": str(e),
        })
