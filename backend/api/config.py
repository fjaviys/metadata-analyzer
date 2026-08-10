"""api/config.py — Configuración, prueba de conexiones, navegación de carpetas y formatos."""

from __future__ import annotations

import os

import bootstrap  # noqa: F401
import formats as fmts
import metadata_analyzer as ma
from fastapi import APIRouter, HTTPException, Query

from core.config import settings
from core.exceptions import MetadataAnalyzerError
from core.logger import get_logger
from core.security import in_allowlist, validate_path
from schemas.models import (
    BrowseEntry, BrowseResult, ConnectionTestRequest, ConnectionTestResult,
)
from services import immich_service, omv_service

router = APIRouter(prefix="/config", tags=["config"])
log = get_logger("api.config")


@router.get("/roots", response_model=dict)
async def allowed_roots():
    """Raíces permitidas (allowlist) y disponibilidad de exiftool."""
    return {
        "allowed_media_roots": settings.allowed_media_roots,
        "exiftool_available": ma.exiftool_available(),
    }


@router.get("/formats", response_model=dict)
async def formats_catalog():
    """Catálogo de formatos soportados, agrupado (image / raw / video)."""
    return fmts.catalog()


@router.get("/browse", response_model=BrowseResult)
async def browse(path: str = Query("", description="Ruta a explorar; vacío = raíces permitidas")):
    """
    Lista las subcarpetas inmediatas de `path` para el selector de carpetas.
    Sin `path` devuelve las raíces permitidas. Valida contra la allowlist y
    rechaza rutas de sistema.
    """
    if not path:
        return BrowseResult(
            path="", parent=None,
            dirs=[BrowseEntry(name=os.path.basename(r) or r, path=r)
                  for r in settings.allowed_media_roots],
        )
    try:
        real = validate_path(path, require_write=False, must_exist=True)
    except MetadataAnalyzerError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    if not os.path.isdir(real):
        raise HTTPException(status_code=400, detail="la ruta no es una carpeta")

    dirs: list[BrowseEntry] = []
    try:
        with os.scandir(real) as it:
            for entry in it:
                try:
                    if entry.is_dir(follow_symlinks=False) and not entry.name.startswith("."):
                        dirs.append(BrowseEntry(name=entry.name,
                                                path=os.path.join(real, entry.name)))
                except OSError:
                    continue
    except PermissionError:
        raise HTTPException(status_code=403, detail=f"sin permiso para listar {real}")

    dirs.sort(key=lambda d: d.name.lower())
    parent = os.path.dirname(real)
    parent = parent if (parent != real and in_allowlist(parent)) else None
    return BrowseResult(path=real, parent=parent, dirs=dirs)


@router.post("/test", response_model=ConnectionTestResult)
async def test_connection(req: ConnectionTestRequest):
    if req.type == "local":
        try:
            real = validate_path(req.root_path or "", must_exist=True)
        except MetadataAnalyzerError as e:
            return ConnectionTestResult(ok=False, message=str(e))
        if not ma.exiftool_available():
            return ConnectionTestResult(
                ok=False, message="exiftool no está disponible en el backend")
        # COMPROBACIÓN: estimar PRIMERO el total de archivos multimedia (rápido).
        est = ma.count_media_files_approx(real, max_depth=settings.max_walk_depth)
        total = est["total"]
        prefix = "~" if est["approximate"] else ""
        approx_txt = " (aprox.)" if est["approximate"] else ""
        return ConnectionTestResult(
            ok=True,
            message=(f"Carpeta accesible: {real} · {prefix}{total} archivos "
                     f"multimedia detectados{approx_txt}"),
            details={"root": real, "total_media_files": total,
                     "approximate": est["approximate"]},
        )

    if req.type == "immich":
        res = await immich_service.test_connection(req.base_url or "", req.api_key or "")
        return ConnectionTestResult(**res)

    if req.type == "omv":
        res = await omv_service.test_connection(
            req.base_url or "", req.username or "", req.password or "")
        return ConnectionTestResult(**res)

    return ConnectionTestResult(ok=False, message="tipo de conexión no soportado")
