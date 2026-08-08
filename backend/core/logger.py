"""
core/logger.py — Logging con dos destinos: operaciones y errores.

- operations.log : cada acción relevante (análisis, correcciones, conexiones).
- errors.log     : solo WARNING/ERROR.
Formato legible + función `log_correction` que registra ruta, tipo, valor
original y nuevo por cada corrección.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Optional

from .config import settings

_FMT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    os.makedirs(settings.log_dir, exist_ok=True)

    ops_handler = RotatingFileHandler(
        os.path.join(settings.log_dir, "operations.log"),
        maxBytes=5_000_000, backupCount=5, encoding="utf-8",
    )
    ops_handler.setLevel(logging.INFO)
    ops_handler.setFormatter(logging.Formatter(_FMT))

    err_handler = RotatingFileHandler(
        os.path.join(settings.log_dir, "errors.log"),
        maxBytes=5_000_000, backupCount=5, encoding="utf-8",
    )
    err_handler.setLevel(logging.WARNING)
    err_handler.setFormatter(logging.Formatter(_FMT))

    console = logging.StreamHandler()
    console.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    console.setFormatter(logging.Formatter(_FMT))

    root = logging.getLogger("metadata_analyzer")
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(ops_handler)
    root.addHandler(err_handler)
    root.addHandler(console)
    root.propagate = False
    _configured = True


def get_logger(name: str = "metadata_analyzer") -> logging.Logger:
    setup_logging()
    if name == "metadata_analyzer":
        return logging.getLogger(name)
    return logging.getLogger(f"metadata_analyzer.{name}")


def log_correction(path: str, correction_type: str, original: Optional[str],
                   new: Optional[str], status: str, dry_run: bool,
                   error: Optional[str] = None) -> None:
    """Registro estructurado de una corrección (operations + errors si falla)."""
    log = get_logger("corrections")
    mode = "DRY-RUN" if dry_run else "REAL"
    msg = (f"[{mode}] {status.upper()} type={correction_type} path={path} "
           f"original={original!r} new={new!r}")
    if error:
        log.error(f"{msg} error={error}")
    else:
        log.info(msg)
