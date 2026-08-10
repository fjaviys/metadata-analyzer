"""
formats.py — Catálogo de formatos multimedia soportados (basado en Immich).

Fuente: https://docs.immich.app/features/supported-formats/ (imagen y vídeo) más un
conjunto amplio de formatos RAW de cámara (libraw), ya que la doc de Immich remite al
código para la lista RAW completa.

Expone conjuntos por grupo (imagen/vídeo) y utilidades para:
- normalizar extensiones,
- resolver el tipo de medio de un archivo,
- construir el conjunto de extensiones a procesar a partir de una selección de
  formatos incluidos y una lista de extensiones a omitir.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

# --- Imagen (no RAW) — lista de Immich ---
IMAGE_EXTS_STANDARD = {
    ".avif", ".bmp", ".gif", ".heic", ".heif", ".jp2", ".jpeg", ".jpg", ".jpe",
    ".insp", ".jxl", ".mpo", ".png", ".psd", ".svg", ".tif", ".tiff", ".webp",
}

# --- RAW de cámara (libraw) ---
RAW_EXTS = {
    ".raw", ".dng", ".rw2", ".arw", ".sr2", ".srf", ".srw",   # genérico, Adobe, Panasonic, Sony
    ".cr2", ".cr3", ".crw",                                     # Canon
    ".nef", ".nrw",                                             # Nikon
    ".orf",                                                     # Olympus
    ".raf",                                                     # Fujifilm
    ".pef", ".ptx",                                             # Pentax
    ".rwl",                                                     # Leica
    ".erf",                                                     # Epson
    ".mrw",                                                     # Minolta
    ".dcr", ".kdc",                                             # Kodak
    ".3fr", ".fff",                                             # Hasselblad
    ".iiq",                                                     # Phase One
    ".mef",                                                     # Mamiya
    ".mos",                                                     # Leaf
    ".x3f",                                                     # Sigma
    ".gpr",                                                     # GoPro RAW
}

IMAGE_EXTS = IMAGE_EXTS_STANDARD | RAW_EXTS

# --- Vídeo — lista de Immich ---
VIDEO_EXTS = {
    ".3gp", ".3gpp", ".avi", ".flv", ".m4v", ".mkv", ".mts", ".m2ts", ".m2t",
    ".ts", ".mp4", ".insv", ".mpg", ".mpe", ".mpeg", ".mxf", ".mov", ".webm",
    ".wmv",
}

MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS


def normalize_ext(ext: str) -> str:
    """'.JPG' / 'jpg' -> '.jpg'."""
    e = ext.strip().lower()
    if not e:
        return ""
    if not e.startswith("."):
        e = "." + e
    return e


def normalize_exts(exts: Optional[Iterable[str]]) -> set[str]:
    if not exts:
        return set()
    return {normalize_ext(e) for e in exts if e and e.strip()}


def media_type_for(path_or_ext: str) -> str:
    """Devuelve 'photo' | 'video' | 'unknown'."""
    ext = normalize_ext(os.path.splitext(path_or_ext)[1] or path_or_ext)
    if ext in IMAGE_EXTS:
        return "photo"
    if ext in VIDEO_EXTS:
        return "video"
    return "unknown"


def catalog() -> dict:
    """Catálogo agrupado para la UI (selector de formatos)."""
    return {
        "image": sorted(IMAGE_EXTS_STANDARD),
        "raw": sorted(RAW_EXTS),
        "video": sorted(VIDEO_EXTS),
    }


def resolve_extensions(
    include: Optional[Iterable[str]] = None,
    exclude: Optional[Iterable[str]] = None,
) -> set[str]:
    """
    Conjunto final de extensiones a procesar.
    - `include`: si se indica, se parte SOLO de esas extensiones (deben ser
      multimedia conocidas); si no, se parte de todas las MEDIA_EXTS.
    - `exclude`: extensiones a omitir del resultado.
    Siempre se intersecta con MEDIA_EXTS para no procesar formatos no soportados.
    """
    inc = normalize_exts(include)
    exc = normalize_exts(exclude)
    base = (inc & MEDIA_EXTS) if inc else set(MEDIA_EXTS)
    return base - exc


__all__ = [
    "IMAGE_EXTS", "IMAGE_EXTS_STANDARD", "RAW_EXTS", "VIDEO_EXTS", "MEDIA_EXTS",
    "normalize_ext", "normalize_exts", "media_type_for", "catalog",
    "resolve_extensions",
]
