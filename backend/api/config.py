"""api/config.py — Configuración y prueba de conexiones (local / Immich / OMV)."""

from __future__ import annotations

import bootstrap  # noqa: F401
import metadata_analyzer as ma
from fastapi import APIRouter

from core.config import settings
from core.exceptions import MetadataAnalyzerError
from core.logger import get_logger
from core.security import validate_path
from schemas.models import ConnectionTestRequest, ConnectionTestResult
from services import immich_service, omv_service

router = APIRouter(prefix="/config", tags=["config"])
log = get_logger("api.config")


@router.get("/roots", response_model=dict)
async def allowed_roots():
    """Devuelve las raíces permitidas (allowlist) para orientar al usuario."""
    return {
        "allowed_media_roots": settings.allowed_media_roots,
        "exiftool_available": ma.exiftool_available(),
    }


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
        # contar rápido algunos archivos multimedia
        sample = 0
        for _ in ma.iter_media_files(real, max_depth=2):
            sample += 1
            if sample >= 25:
                break
        return ConnectionTestResult(
            ok=True, message=f"Carpeta accesible: {real}",
            details={"sample_media_found": sample})

    if req.type == "immich":
        res = await immich_service.test_connection(req.base_url or "", req.api_key or "")
        return ConnectionTestResult(**res)

    if req.type == "omv":
        res = await omv_service.test_connection(
            req.base_url or "", req.username or "", req.password or "")
        return ConnectionTestResult(**res)

    return ConnectionTestResult(ok=False, message="tipo de conexión no soportado")
