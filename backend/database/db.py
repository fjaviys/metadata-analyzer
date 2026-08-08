"""database/db.py — Proveedor del DatabaseManager (shared/python) para el backend."""

from __future__ import annotations

import bootstrap  # noqa: F401  (añade shared/python al path)
from database_manager import DatabaseManager

from core.config import settings

_db: DatabaseManager | None = None


def get_db() -> DatabaseManager:
    global _db
    if _db is None:
        _db = DatabaseManager(settings.sqlite_path)
        _db.init_db()
    return _db
