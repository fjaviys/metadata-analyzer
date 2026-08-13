"""core/exceptions.py — Excepciones de dominio del backend."""

from __future__ import annotations


class MetadataAnalyzerError(Exception):
    """Base para errores controlados del dominio."""
    status_code = 400


class SecurityValidationError(MetadataAnalyzerError):
    """Ruta o entrada rechazada por las reglas de seguridad."""
    status_code = 403


class PathNotFoundError(MetadataAnalyzerError):
    status_code = 404


class PermissionErrorMA(MetadataAnalyzerError):
    status_code = 403


class ExiftoolNotAvailableError(MetadataAnalyzerError):
    status_code = 503


class ConfirmationRequiredError(MetadataAnalyzerError):
    """La operación escribe sobre archivos reales y requiere confirmación explícita."""
    status_code = 428  # Precondition Required


class ConnectionTestError(MetadataAnalyzerError):
    status_code = 502


class NeedsReanalysisError(MetadataAnalyzerError):
    """Hay correcciones reales aplicadas a esta sesión; hay que volver a
    analizar antes de reestructurar carpetas (los datos de la sesión pueden
    estar desactualizados)."""
    status_code = 409  # Conflict
