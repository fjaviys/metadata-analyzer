"""
core/backup.py — Backups automáticos ANTES de cualquier corrección.

- Cada ejecución de corrección crea un "run" de backup:
      data/backups/<timestamp>_<run_id>/
  preservando la ruta relativa original de cada archivo.
- Rotación: se conservan los últimos N runs (BACKUP_KEEP_LAST).
- Restauración: por archivo o de un run completo (para el abort del motor).
- Manifiesto JSON por run con {original -> backup}.

Se apoya en shutil.copy2 (preserva mtime/metadata de fichero). El motor de
corrección recibe `backup_fn` y `restore_fn` desde aquí.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from typing import Optional

from .config import settings
from .logger import get_logger

log = get_logger("backup")


class BackupRun:
    """Una sesión de backup para una ejecución de corrección."""

    def __init__(self, base_dir: str, run_id: str):
        self.run_id = run_id
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.dir = os.path.join(base_dir, f"{ts}_{run_id}")
        os.makedirs(self.dir, exist_ok=True)
        self.manifest_path = os.path.join(self.dir, "manifest.json")
        self.manifest: dict[str, str] = {}

    def backup_fn(self, path: str) -> str:
        """Copia `path` al run preservando su ruta relativa. Devuelve backup_path."""
        rel = os.path.abspath(path).lstrip(os.sep)
        dest = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(path, dest)
        self.manifest[os.path.abspath(path)] = dest
        self._flush_manifest()
        return dest

    def _flush_manifest(self) -> None:
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump({"run_id": self.run_id, "files": self.manifest}, f,
                      ensure_ascii=False, indent=2)

    def restore_all(self) -> int:
        """Restaura todos los archivos del run. Devuelve nº restaurados."""
        restored = 0
        for original, backup in self.manifest.items():
            try:
                shutil.copy2(backup, original)
                restored += 1
            except OSError as e:
                log.error(f"restore falló para {original}: {e}")
        log.info(f"run {self.run_id}: restaurados {restored} archivos")
        return restored


class BackupManager:
    def __init__(self, base_dir: Optional[str] = None, keep_last: Optional[int] = None):
        self.base_dir = base_dir or settings.backup_dir
        self.keep_last = keep_last if keep_last is not None else settings.backup_keep_last
        os.makedirs(self.base_dir, exist_ok=True)

    def new_run(self, run_id: str) -> BackupRun:
        self.rotate()
        run = BackupRun(self.base_dir, run_id)
        log.info(f"backup run creado: {run.dir}")
        return run

    def restore_file(self, backup_path: str, original_path: str) -> None:
        shutil.copy2(backup_path, original_path)

    def list_runs(self) -> list[str]:
        if not os.path.isdir(self.base_dir):
            return []
        runs = [d for d in os.listdir(self.base_dir)
                if os.path.isdir(os.path.join(self.base_dir, d))]
        return sorted(runs)

    def rotate(self) -> None:
        """Conserva solo los últimos keep_last runs; elimina los más antiguos."""
        runs = self.list_runs()
        excess = len(runs) - self.keep_last + 1  # +1 porque vamos a crear uno
        if excess <= 0:
            return
        for old in runs[:excess]:
            path = os.path.join(self.base_dir, old)
            try:
                shutil.rmtree(path)
                log.info(f"backup rotado (eliminado): {path}")
            except OSError as e:
                log.error(f"no se pudo rotar backup {path}: {e}")

    def restore_run_from_manifest(self, run_dir_name: str) -> int:
        """Restaura un run a partir de su manifest.json (para recuperación manual)."""
        manifest_path = os.path.join(self.base_dir, run_dir_name, "manifest.json")
        if not os.path.isfile(manifest_path):
            raise FileNotFoundError(manifest_path)
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        restored = 0
        for original, backup in data.get("files", {}).items():
            try:
                shutil.copy2(backup, original)
                restored += 1
            except OSError as e:
                log.error(f"restore falló para {original}: {e}")
        return restored


__all__ = ["BackupManager", "BackupRun"]
