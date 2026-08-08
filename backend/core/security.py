"""
core/security.py — Validación estricta de entradas (requisito crítico).

- Rechaza rutas del sistema (/etc, /sys, /proc, /root, /boot, /dev, /bin, /sbin,
  /lib, /usr, /var, /run, ...).
- Exige que las rutas estén dentro de la allowlist ALLOWED_MEDIA_ROOTS.
- Comprueba existencia y permisos (lectura; escritura cuando aplica).
- Bloquea path traversal (.., symlinks que escapan de la raíz permitida).
- Limita la profundidad de recorrido.
- Sanitiza API keys y hostnames para logs.

Diseño "fail-closed": ante la duda, se rechaza (opción más segura).
"""

from __future__ import annotations

import os
import re
from typing import Iterable

from .config import settings
from .exceptions import (
    PathNotFoundError, PermissionErrorMA, SecurityValidationError,
)

# Prefijos de sistema prohibidos siempre (aunque estuvieran en la allowlist).
FORBIDDEN_PREFIXES = (
    "/etc", "/sys", "/proc", "/root", "/boot", "/dev", "/bin", "/sbin",
    "/lib", "/lib64", "/usr", "/var", "/run", "/opt", "/srv/pillar",
    "/snap", "/.ssh",
)

# Nombres de componente prohibidos en cualquier parte de la ruta.
FORBIDDEN_COMPONENTS = {".ssh", ".git", ".gnupg", "node_modules"}

_HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-.]{0,253}[a-zA-Z0-9])?$")


def _normalize(path: str) -> str:
    if not path or not isinstance(path, str):
        raise SecurityValidationError("ruta vacía o inválida")
    # resolvemos symlinks y '..' para evitar escapes
    real = os.path.realpath(os.path.abspath(path))
    return real


def _is_within(child: str, parent: str) -> bool:
    parent = os.path.realpath(parent)
    child = os.path.realpath(child)
    try:
        return os.path.commonpath([child, parent]) == parent
    except ValueError:
        return False


def is_forbidden_system_path(path: str) -> bool:
    real = _normalize(path)
    for pref in FORBIDDEN_PREFIXES:
        if real == pref or real.startswith(pref + os.sep):
            return True
    parts = set(real.split(os.sep))
    if parts & FORBIDDEN_COMPONENTS:
        return True
    return False


def in_allowlist(path: str) -> bool:
    real = _normalize(path)
    roots = settings.allowed_media_roots
    if not roots:
        return False
    return any(_is_within(real, root) for root in roots)


def validate_path(path: str, require_write: bool = False,
                  must_exist: bool = True) -> str:
    """
    Valida una ruta de análisis/corrección y devuelve la ruta real normalizada.
    Lanza SecurityValidationError / PathNotFoundError / PermissionErrorMA.
    """
    real = _normalize(path)

    if is_forbidden_system_path(real):
        raise SecurityValidationError(
            f"ruta del sistema no permitida: {real}"
        )

    if not in_allowlist(real):
        raise SecurityValidationError(
            f"ruta fuera de las raíces permitidas (ALLOWED_MEDIA_ROOTS): {real}"
        )

    if must_exist and not os.path.exists(real):
        raise PathNotFoundError(f"la ruta no existe: {real}")

    if os.path.exists(real):
        if not os.access(real, os.R_OK):
            raise PermissionErrorMA(f"sin permiso de lectura: {real}")
        if require_write and not os.access(real, os.W_OK):
            raise PermissionErrorMA(f"sin permiso de escritura: {real}")

    return real


def check_walk_depth(root: str, path: str, max_depth: int | None = None) -> None:
    """Rechaza rutas más profundas que max_depth respecto a root."""
    max_depth = settings.max_walk_depth if max_depth is None else max_depth
    root_r = os.path.realpath(root)
    path_r = os.path.realpath(path)
    depth = path_r.rstrip(os.sep).count(os.sep) - root_r.rstrip(os.sep).count(os.sep)
    if depth > max_depth:
        raise SecurityValidationError(
            f"profundidad {depth} supera el máximo permitido ({max_depth})"
        )


def validate_subfolders(root: str, subfolders: Iterable[str]) -> list[str]:
    """
    Valida que cada subcarpeta seleccionada esté dentro de `root` (ya validado) y
    devuelve rutas reales. Bloquea traversal fuera de root.
    """
    root_real = validate_path(root, must_exist=True)
    out: list[str] = []
    for sub in subfolders:
        # se permite pasar rutas relativas a root o absolutas dentro de root
        candidate = sub if os.path.isabs(sub) else os.path.join(root_real, sub)
        real = _normalize(candidate)
        if not _is_within(real, root_real):
            raise SecurityValidationError(
                f"la subcarpeta '{sub}' está fuera de la carpeta analizada"
            )
        if is_forbidden_system_path(real):
            raise SecurityValidationError(f"subcarpeta no permitida: {real}")
        out.append(real)
    return out


# --------------------------- sanitización -----------------------------------

def sanitize_api_key(key: str | None) -> str:
    """Enmascara una API key para logs: muestra solo los últimos 4 caracteres."""
    if not key:
        return "(vacía)"
    key = key.strip()
    if len(key) <= 4:
        return "****"
    return "*" * (len(key) - 4) + key[-4:]


def sanitize_hostname(host: str | None) -> str:
    """
    Valida/sanitiza un hostname o URL base. Devuelve el hostname limpio o lanza
    SecurityValidationError si es claramente inválido.
    """
    if not host:
        raise SecurityValidationError("hostname vacío")
    h = host.strip()
    # quitar esquema y ruta si viene como URL
    h = re.sub(r"^https?://", "", h, flags=re.IGNORECASE)
    h = h.split("/")[0]
    h = h.split(":")[0]  # quitar puerto para validar el host
    if not _HOSTNAME_RE.match(h):
        # permitir IPs simples
        if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", h):
            raise SecurityValidationError(f"hostname inválido: {host!r}")
    return h


def safe_repr_config(cfg: dict) -> dict:
    """Devuelve una copia del dict de config con secretos enmascarados (para logs)."""
    out = dict(cfg)
    for k in list(out.keys()):
        if re.search(r"(key|token|password|secret)", k, re.IGNORECASE):
            out[k] = sanitize_api_key(str(out[k]))
    return out


__all__ = [
    "validate_path", "validate_subfolders", "check_walk_depth",
    "is_forbidden_system_path", "in_allowlist",
    "sanitize_api_key", "sanitize_hostname", "safe_repr_config",
    "FORBIDDEN_PREFIXES",
]
