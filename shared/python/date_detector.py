"""
date_detector.py — Detección de fechas en nombres de archivo y rutas de carpetas.

Clasifica la fecha detectada por precisión (NONE, YEAR, YEAR_MONTH, FULL_DATE,
DATETIME), asigna una confianza (0..1) y devuelve el texto detectado. Detecta
tanto en el nombre del archivo como en la ESTRUCTURA de carpetas que lo contiene
(p. ej. /2020/07/02/, /2020/07/, /2020/).

Diseño defensivo: rangos validados (año 1990..actual+5, mes 1-12, día 1-31),
sin dependencias externas. Pensado para ser importado por metadata_analyzer.py y
correction_engine.py.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Optional


class Precision(IntEnum):
    """Precisión de la fecha detectada (orden = riqueza de información)."""
    NONE = 0
    YEAR = 1
    YEAR_MONTH = 2
    FULL_DATE = 3
    DATETIME = 4

    @property
    def label(self) -> str:
        return self.name


# --- Rangos de validación (configurables por entorno) -----------------------
DATE_MIN_YEAR = int(os.getenv("DATE_MIN_YEAR", "1990"))
DATE_MAX_YEAR_OFFSET = int(os.getenv("DATE_MAX_YEAR_OFFSET", "5"))


def _max_year() -> int:
    return datetime.now().year + DATE_MAX_YEAR_OFFSET


@dataclass
class DetectedDate:
    """Resultado de una detección de fecha."""
    precision: Precision = Precision.NONE
    confidence: float = 0.0
    matched_text: str = ""
    source: str = ""          # "filename" | "path" | ""
    year: Optional[int] = None
    month: Optional[int] = None
    day: Optional[int] = None
    hour: Optional[int] = None
    minute: Optional[int] = None
    second: Optional[int] = None
    notes: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.precision != Precision.NONE

    def to_datetime(self) -> Optional[datetime]:
        """
        Construye un datetime "hasta donde se pueda llegar" completando con los
        valores mínimos por defecto (mes=1, día=1, hora=00:00:00).
        """
        if not self.year:
            return None
        try:
            return datetime(
                self.year,
                self.month or 1,
                self.day or 1,
                self.hour or 0,
                self.minute or 0,
                self.second or 0,
            )
        except ValueError:
            return None

    def to_exif_string(self) -> Optional[str]:
        """Formato EXIF 'YYYY:MM:DD HH:MM:SS' completando por precisión."""
        dt = self.to_datetime()
        if dt is None:
            return None
        return dt.strftime("%Y:%m:%d %H:%M:%S")

    def as_dict(self) -> dict:
        return {
            "precision": self.precision.label,
            "confidence": round(self.confidence, 3),
            "matched_text": self.matched_text,
            "source": self.source,
            "year": self.year,
            "month": self.month,
            "day": self.day,
            "hour": self.hour,
            "minute": self.minute,
            "second": self.second,
            "datetime": self.to_exif_string(),
            "notes": self.notes,
        }


# --- Validadores -------------------------------------------------------------

def _valid_year(y: int) -> bool:
    return DATE_MIN_YEAR <= y <= _max_year()


def _valid_month(m: int) -> bool:
    return 1 <= m <= 12


def _valid_day(d: int) -> bool:
    return 1 <= d <= 31


def _valid_ymd(y: int, m: int, d: int) -> bool:
    if not (_valid_year(y) and _valid_month(m) and _valid_day(d)):
        return False
    try:
        datetime(y, m, d)
        return True
    except ValueError:
        return False


# --- Patrones de nombre de archivo ------------------------------------------
# Se evalúan de MAYOR a MENOR precisión; el primero válido gana.

# YYYYMMDD_HHMMSS ó YYYY-MM-DD HH:MM:SS ó YYYY.MM.DD_HH.MM.SS ...
_RE_DATETIME = re.compile(
    r"(?P<y>(?:19|20)\d{2})[-._/]?(?P<mo>\d{2})[-._/]?(?P<d>\d{2})"
    r"[ _T]"
    r"(?P<h>\d{2})[-._:]?(?P<mi>\d{2})[-._:]?(?P<s>\d{2})?"
)

# YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD / YYYYMMDD
_RE_FULL = re.compile(
    r"(?P<y>(?:19|20)\d{2})[-._/]?(?P<mo>\d{2})[-._/]?(?P<d>\d{2})"
)

# YYYY-MM / YYYY/MM / YYYY.MM / YYYYMM
_RE_YEAR_MONTH = re.compile(
    r"(?P<y>(?:19|20)\d{2})[-._/](?P<mo>\d{2})(?![-._/]?\d)"
    r"|(?P<y2>(?:19|20)\d{2})(?P<mo2>\d{2})(?!\d)"
)

# YYYY aislado (delimitado por no-dígitos)
_RE_YEAR = re.compile(r"(?<!\d)(?P<y>(?:19|20)\d{2})(?!\d)")


# --- Patrones de estructura de carpetas -------------------------------------
_RE_PATH_YMD = re.compile(r"/(?P<y>(?:19|20)\d{2})/(?P<mo>\d{1,2})/(?P<d>\d{1,2})(?:/|$)")
_RE_PATH_YM = re.compile(r"/(?P<y>(?:19|20)\d{2})/(?P<mo>\d{1,2})(?:/|$)")
_RE_PATH_Y = re.compile(r"/(?P<y>(?:19|20)\d{2})(?:/|$)")


def detect_from_filename(name: str) -> DetectedDate:
    """Detecta la fecha embebida en el nombre de archivo (sin la ruta)."""
    base = os.path.basename(name)
    stem = os.path.splitext(base)[0]

    # 1) DATETIME
    m = _RE_DATETIME.search(stem)
    if m:
        y, mo, d = int(m["y"]), int(m["mo"]), int(m["d"])
        h, mi = int(m["h"]), int(m["mi"])
        s = int(m["s"]) if m["s"] else 0
        if _valid_ymd(y, mo, d) and 0 <= h < 24 and 0 <= mi < 60 and 0 <= s < 60:
            return DetectedDate(
                precision=Precision.DATETIME, confidence=0.97,
                matched_text=m.group(0), source="filename",
                year=y, month=mo, day=d, hour=h, minute=mi, second=s,
            )

    # 2) FULL_DATE
    m = _RE_FULL.search(stem)
    if m:
        y, mo, d = int(m["y"]), int(m["mo"]), int(m["d"])
        if _valid_ymd(y, mo, d):
            # confianza algo menor si no hay separadores (más ambiguo)
            conf = 0.9 if any(c in m.group(0) for c in "-._/") else 0.8
            return DetectedDate(
                precision=Precision.FULL_DATE, confidence=conf,
                matched_text=m.group(0), source="filename",
                year=y, month=mo, day=d,
            )

    # 3) YEAR_MONTH
    m = _RE_YEAR_MONTH.search(stem)
    if m:
        y = int(m["y"] or m["y2"])
        mo = int(m["mo"] or m["mo2"])
        if _valid_year(y) and _valid_month(mo):
            conf = 0.7 if m["y"] else 0.6
            return DetectedDate(
                precision=Precision.YEAR_MONTH, confidence=conf,
                matched_text=m.group(0), source="filename",
                year=y, month=mo,
            )

    # 4) YEAR
    m = _RE_YEAR.search(stem)
    if m:
        y = int(m["y"])
        if _valid_year(y):
            return DetectedDate(
                precision=Precision.YEAR, confidence=0.45,
                matched_text=m.group(0), source="filename",
                year=y,
            )

    return DetectedDate()


def detect_from_path(path: str) -> DetectedDate:
    """
    Detecta la fecha por la ESTRUCTURA de carpetas contenedoras.
    Usa el directorio (se ignora el propio nombre de archivo).
    """
    directory = os.path.dirname(path)
    # normaliza a '/' y garantiza barras alrededor para los patrones
    norm = "/" + directory.replace("\\", "/").strip("/") + "/"

    m = _RE_PATH_YMD.search(norm)
    if m:
        y, mo, d = int(m["y"]), int(m["mo"]), int(m["d"])
        if _valid_ymd(y, mo, d):
            return DetectedDate(
                precision=Precision.FULL_DATE, confidence=0.85,
                matched_text=m.group(0).strip("/"), source="path",
                year=y, month=mo, day=d,
                notes=["fecha derivada de estructura de carpetas"],
            )

    m = _RE_PATH_YM.search(norm)
    if m:
        y, mo = int(m["y"]), int(m["mo"])
        if _valid_year(y) and _valid_month(mo):
            return DetectedDate(
                precision=Precision.YEAR_MONTH, confidence=0.65,
                matched_text=m.group(0).strip("/"), source="path",
                year=y, month=mo,
                notes=["fecha derivada de estructura de carpetas"],
            )

    m = _RE_PATH_Y.search(norm)
    if m:
        y = int(m["y"])
        if _valid_year(y):
            return DetectedDate(
                precision=Precision.YEAR, confidence=0.4,
                matched_text=m.group(0).strip("/"), source="path",
                year=y,
                notes=["fecha derivada de estructura de carpetas"],
            )

    return DetectedDate()


def detect(path: str) -> DetectedDate:
    """
    Detección combinada: prioriza el nombre de archivo (más específico) y, si
    empata en precisión o el nombre no aporta, cae a la estructura de carpetas.
    Devuelve el candidato con mayor precisión; a igualdad, mayor confianza.
    """
    by_name = detect_from_filename(path)
    by_path = detect_from_path(path)

    candidates = [c for c in (by_name, by_path) if c.is_valid]
    if not candidates:
        return DetectedDate()

    best = max(candidates, key=lambda c: (int(c.precision), c.confidence))

    # Enriquecer: si el ganador es por carpeta pero el nombre confirma el año,
    # dejamos constancia como nota de refuerzo.
    if best.source == "path" and by_name.is_valid and by_name.year == best.year:
        best.notes.append("año confirmado también por el nombre de archivo")
    return best


__all__ = ["Precision", "DetectedDate", "detect", "detect_from_filename", "detect_from_path"]
