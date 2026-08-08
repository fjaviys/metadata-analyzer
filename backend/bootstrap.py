"""
bootstrap.py — Hace importable shared/python desde el backend.

Importar este módulo (o `import bootstrap`) antes de usar date_detector,
metadata_analyzer, etc. En Docker, shared/python también se añade a PYTHONPATH.
"""

from __future__ import annotations

import os
import sys

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_BACKEND_DIR)
SHARED_DIR = os.path.join(_PROJECT_ROOT, "shared", "python")

# Permite override en contenedor (p. ej. /app/shared/python).
SHARED_DIR = os.getenv("SHARED_PYTHON_DIR", SHARED_DIR)

if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)
