"""
pattern_parser.py — Patrones de fecha por tokens (override manual del usuario).

Sintaxis legible (español) de tokens:
    AAAA  año de 4 cifras      AA  año de 2 cifras
    MM    mes                  DD  día
    hh    hora                 mm  minutos        ss  segundos
Cualquier carácter que no sea token (–, /, ., _, espacio) se trata como separador
OPCIONAL, de modo que un mismo patrón vale con o sin separadores:
    'DDMMAAAA'  y  'DD-MM-AAAA'  reconocen  02102009  y  02-10-2009.

Se usa para que el usuario aplique manualmente un patrón a una carpeta y todos sus
archivos cuando la detección automática no acierta. Requiere, como mínimo, un año.
"""

from __future__ import annotations

import os
import re
from typing import Optional

from date_detector import (
    DetectedDate, Precision, _valid_day, _valid_month, _valid_ymd, _valid_year,
    _yy_to_year, detect_daymonth_from_filename, detect_from_path,
)

# Sentinela para el preset "día+mes del nombre + año de la carpeta".
DAYMONTH_FOLDERYEAR = "__DAYMONTH_FOLDERYEAR__"

_TOKEN_RE = re.compile(r"AAAA|AA|MM|DD|hh|mm|ss")
_TOKEN_MAP = {
    "AAAA": ("Y", 4), "AA": ("y", 2), "MM": ("mo", 2), "DD": ("d", 2),
    "hh": ("h", 2), "mm": ("mi", 2), "ss": ("s", 2),
}

# Patrones predefinidos ofrecidos en la UI.
PRESETS: list[dict] = [
    {"key": "iso", "label": "AAAA-MM-DD (ISO)", "pattern": "AAAA-MM-DD", "source": "auto"},
    {"key": "ymd_compact", "label": "AAAAMMDD", "pattern": "AAAAMMDD", "source": "auto"},
    {"key": "dmy", "label": "DD-MM-AAAA (europeo)", "pattern": "DD-MM-AAAA", "source": "auto"},
    {"key": "dmy_compact", "label": "DDMMAAAA", "pattern": "DDMMAAAA", "source": "auto"},
    {"key": "mdy", "label": "MM-DD-AAAA (americano)", "pattern": "MM-DD-AAAA", "source": "auto"},
    {"key": "yymmdd", "label": "AAMMDD (año 2 cifras)", "pattern": "AAMMDD", "source": "auto"},
    {"key": "ym", "label": "AAAA-MM (mes/año)", "pattern": "AAAA-MM", "source": "auto"},
    {"key": "year", "label": "AAAA (solo año)", "pattern": "AAAA", "source": "auto"},
    {"key": "daymonth_folderyear",
     "label": "Día+mes del nombre + año de la carpeta",
     "pattern": DAYMONTH_FOLDERYEAR, "source": "auto"},
]


def compile_pattern(pattern: str) -> tuple[re.Pattern, list[str]]:
    """Compila un patrón de tokens a una expresión regular con grupos nombrados."""
    parts: list[str] = []
    used: list[str] = []
    i = 0
    while i < len(pattern):
        m = _TOKEN_RE.match(pattern, i)
        if m:
            key, n = _TOKEN_MAP[m.group(0)]
            if key in used:
                raise ValueError(f"token repetido: {m.group(0)}")
            parts.append(rf"(?P<{key}>\d{{{n}}})")
            used.append(key)
            i = m.end()
        else:
            # una tirada de caracteres no-token => separador opcional
            j = i + 1
            while j < len(pattern) and not _TOKEN_RE.match(pattern, j):
                j += 1
            parts.append(r"[-._/ ]*")
            i = j
    if not used:
        raise ValueError("el patrón no contiene tokens de fecha")
    return re.compile(r"(?<!\d)" + "".join(parts) + r"(?!\d)"), used


def apply_pattern(text: str, pattern: str) -> Optional[DetectedDate]:
    """Aplica un patrón de tokens a un texto. Devuelve DetectedDate o None."""
    try:
        rx, _ = compile_pattern(pattern)
    except ValueError:
        return None
    m = rx.search(text)
    if not m:
        return None
    g = m.groupdict()

    if g.get("Y"):
        year = int(g["Y"])
    elif g.get("y"):
        year = _yy_to_year(int(g["y"]))
    else:
        year = None
    if year is None or not _valid_year(year):
        return None

    month = int(g["mo"]) if g.get("mo") else None
    day = int(g["d"]) if g.get("d") else None
    hour = int(g["h"]) if g.get("h") else None
    minute = int(g["mi"]) if g.get("mi") else None
    second = int(g["s"]) if g.get("s") else None

    if month is not None and not _valid_month(month):
        return None
    if day is not None:
        if not _valid_day(day) or not _valid_ymd(year, month or 1, day):
            return None
    if hour is not None and not (0 <= hour < 24):
        return None
    if minute is not None and not (0 <= minute < 60):
        return None
    if second is not None and not (0 <= second < 60):
        return None

    if day is not None and hour is not None:
        precision = Precision.DATETIME
    elif day is not None:
        precision = Precision.FULL_DATE
    elif month is not None:
        precision = Precision.YEAR_MONTH
    else:
        precision = Precision.YEAR

    return DetectedDate(
        precision=precision, confidence=0.95, matched_text=m.group(0),
        source="pattern", year=year, month=month, day=day,
        hour=hour, minute=minute, second=second,
        notes=[f"patrón manual '{pattern}'"],
    )


def _sources(path: str, source: str) -> list[str]:
    stem = os.path.splitext(os.path.basename(path))[0]
    comps = [c for c in os.path.dirname(path).replace("\\", "/").split("/") if c]
    folder = comps[-1] if comps else ""
    if source == "filename":
        return [stem]
    if source == "folder":
        return [folder]
    if source == "path":
        return comps[::-1] + [stem]
    # auto: nombre, carpeta contenedora, y ascendientes
    return [stem, folder] + comps[::-1][1:]


def resolve(path: str, pattern: str, source: str = "auto") -> Optional[DetectedDate]:
    """
    Resuelve la fecha de `path` según un patrón (o preset). Maneja el sentinela
    'día+mes del nombre + año de la carpeta'.
    """
    if pattern == DAYMONTH_FOLDERYEAR:
        dm = detect_daymonth_from_filename(path)
        by_path = detect_from_path(path)
        if dm and by_path.year:
            return DetectedDate(
                Precision.FULL_DATE, 0.9, dm["matched"], "pattern",
                by_path.year, dm["month"], dm["day"],
                notes=[f"día/mes del nombre ({dm['order']}) + año de carpeta (manual)"])
        return None

    for text in _sources(path, source):
        det = apply_pattern(text, pattern)
        if det:
            return det
    return None


def preset_by_key(key: str) -> Optional[dict]:
    for p in PRESETS:
        if p["key"] == key:
            return p
    return None


__all__ = [
    "PRESETS", "DAYMONTH_FOLDERYEAR", "compile_pattern", "apply_pattern",
    "resolve", "preset_by_key",
]
