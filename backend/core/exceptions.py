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
