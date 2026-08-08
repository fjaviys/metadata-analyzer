"""schemas/models.py — Modelos Pydantic de la API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --------------------------- configuración / conexión -----------------------

class LocalConfig(BaseModel):
    type: Literal["local"] = "local"
    root_path: str = Field(..., description="Ruta absoluta a la carpeta de medios")


class ImmichConfig(BaseModel):
    type: Literal["immich"] = "immich"
    base_url: str
    api_key: str


class OMVConfig(BaseModel):
    type: Literal["omv"] = "omv"
    base_url: str
    username: str
    password: str


class ConnectionTestRequest(BaseModel):
    type: Literal["local", "immich", "omv"]
    root_path: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


class ConnectionTestResult(BaseModel):
    ok: bool
    message: str
    details: dict = {}


# --------------------------- análisis ---------------------------------------

class AnalysisRequest(BaseModel):
    root_path: str = Field(..., description="Carpeta a analizar (dentro de la allowlist)")
    connection_type: Literal["local", "immich", "omv"] = "local"
    max_depth: Optional[int] = None
    detect_duplicates: bool = True


class AnalysisStarted(BaseModel):
    session_id: int
    status: str = "running"
    root_path: str


class FolderStatModel(BaseModel):
    folder: str
    total: int = 0
    needs_correction: int = 0
    corrupt: int = 0
    no_exif_date: int = 0


class SessionSummary(BaseModel):
    id: int
    root: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    total_files: int = 0
    photos: int = 0
    videos: int = 0
    with_exif_date: int = 0
    without_exif_date: int = 0
    corrupt: int = 0
    inconsistent: int = 0
    needs_correction: int = 0
    duplicates_count: int = 0
    report_path: Optional[str] = None


# --------------------------- correcciones -----------------------------------

class CorrectionRequest(BaseModel):
    session_id: int
    subfolders: list[str] = Field(default_factory=list,
                                  description="Subcarpetas seleccionadas (vacío = todas)")
    dry_run: bool = True
    confirm_real_write: bool = Field(
        False, description="Debe ser True para ejecutar una corrección REAL")


class CorrectionStarted(BaseModel):
    run_id: str
    dry_run: bool
    total_candidates: int
    status: str = "running"


class ApiError(BaseModel):
    error: str
    detail: Optional[str] = None
