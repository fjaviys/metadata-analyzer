"""
core/config.py — Configuración del backend leída del entorno (.env).

Sin dependencias externas (os.getenv). Expone un singleton `settings`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _split_paths(value: str) -> list[str]:
    return [os.path.abspath(p.strip()) for p in value.split(",") if p.strip()]


@dataclass
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Raíces de medios permitidas (allowlist). Todo lo demás se rechaza.
    allowed_media_roots: list[str] = field(
        default_factory=lambda: _split_paths(os.getenv("ALLOWED_MEDIA_ROOTS", "/media"))
    )

    # Base de datos
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///data/db/metadata_analyzer.db")

    # Backups
    backup_dir: str = os.getenv("BACKUP_DIR", "data/backups")
    backup_keep_last: int = int(os.getenv("BACKUP_KEEP_LAST", "10"))

    # Correcciones
    correction_error_abort_ratio: float = float(os.getenv("CORRECTION_ERROR_ABORT_RATIO", "0.10"))

    # Logs / informes
    log_dir: str = os.getenv("LOG_DIR", "data/logs")
    report_dir: str = os.getenv("REPORT_DIR", "data/reports")

    # Validación de fechas
    date_min_year: int = int(os.getenv("DATE_MIN_YEAR", "1990"))
    date_max_year_offset: int = int(os.getenv("DATE_MAX_YEAR_OFFSET", "5"))

    # Límite de profundidad de recorrido (seguridad / rendimiento)
    max_walk_depth: int = int(os.getenv("MAX_WALK_DEPTH", "30"))

    # Immich / OMV (opcionales; se pueden pasar también desde la UI)
    immich_base_url: str = os.getenv("IMMICH_BASE_URL", "")
    immich_api_key: str = os.getenv("IMMICH_API_KEY", "")
    omv_base_url: str = os.getenv("OMV_BASE_URL", "")
    omv_username: str = os.getenv("OMV_USERNAME", "")
    omv_password: str = os.getenv("OMV_PASSWORD", "")

    @property
    def sqlite_path(self) -> str:
        url = self.database_url
        if url.startswith("sqlite:///"):
            return url[len("sqlite:///"):]
        return url

    def ensure_dirs(self) -> None:
        for d in (os.path.dirname(self.sqlite_path), self.backup_dir,
                  self.log_dir, self.report_dir):
            if d:
                os.makedirs(d, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s


settings = get_settings()
