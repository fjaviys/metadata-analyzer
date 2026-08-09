"""
app.py — Punto de entrada FastAPI del Metadata Analyzer.

Monta los routers REST y el WebSocket de progreso, configura logging y CORS,
inicializa la BD y expone /health. Todas las rutas van bajo /api excepto el
WebSocket (/ws/...), tal como espera el proxy Nginx.
"""

from __future__ import annotations

import bootstrap  # noqa: F401  (añade shared/python al path)
import metadata_analyzer as ma
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request

from api import analysis, config as config_api, corrections, progress, results
from core.config import settings
from core.exceptions import MetadataAnalyzerError
from core.logger import get_logger
from database.db import get_db

log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    get_db()  # inicializa esquema
    log.info(f"backend iniciado env={settings.app_env} "
             f"exiftool={'ok' if ma.exiftool_available() else 'NO DISPONIBLE'} "
             f"roots={settings.allowed_media_roots}")
    yield


app = FastAPI(
    title="Metadata Analyzer API",
    version="0.1.0-beta",
    description="Análisis y corrección segura de metadatos de fecha (Immich/OMV).",
    docs_url="/docs", openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_env != "production" else [],
    allow_origin_regex=r"https?://.*" if settings.app_env == "production" else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(MetadataAnalyzerError)
async def _domain_error_handler(request: Request, exc: MetadataAnalyzerError):
    return JSONResponse(status_code=exc.status_code,
                        content={"error": exc.__class__.__name__, "detail": str(exc)})


@app.get("/health", tags=["health"])
async def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "exiftool": ma.exiftool_available(),
        "allowed_media_roots": settings.allowed_media_roots,
    }


# --- Routers REST bajo /api ---
app.include_router(config_api.router, prefix="/api")
app.include_router(analysis.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(corrections.router, prefix="/api")

# --- WebSocket de progreso (sin prefijo /api) ---
app.include_router(progress.router)
