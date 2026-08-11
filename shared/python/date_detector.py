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

# Versión del motor de detección. Súbela cuando cambie la lógica de detección
# para que la UI sugiera re-analizar sesiones antiguas.
DETECTOR_VERSION = 3


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

# DD-MM-YYYY / DD.MM.YYYY / DDMMYYYY (día primero, año 4 cifras)
_RE_FULL_DMY = re.compile(
    r"(?<!\d)(?P<a>\d{2})[-._/]?(?P<b>\d{2})[-._/]?(?P<y>(?:19|20)\d{2})(?!\d)"
)
# AAMMDD (año de 2 cifras primero): 020926 -> 2002-09-26
_RE_FULL_YY = re.compile(r"(?<!\d)(?P<yy>\d{2})(?P<mo>\d{2})(?P<d>\d{2})(?!\d)")
# DDMM / MMDD (día+mes SIN año, para combinar con el año de la carpeta)
_RE_DAYMONTH = re.compile(r"(?<!\d)(?P<a>\d{2})[-._]?(?P<b>\d{2})(?!\d)")

# YYYY aislado (delimitado por no-dígitos)
_RE_YEAR = re.compile(r"(?<!\d)(?P<y>(?:19|20)\d{2})(?!\d)")


def _yy_to_year(yy: int) -> Optional[int]:
    """Año de 2 cifras -> 4 cifras, dentro del rango válido (1990..actual+5)."""
    for cand in (2000 + yy, 1900 + yy):
        if _valid_year(cand):
            return cand
    return None


# --- Patrones de estructura de carpetas (jerárquica: /AAAA/MM/DD/) -----------
_RE_PATH_YMD = re.compile(r"/(?P<y>(?:19|20)\d{2})/(?P<mo>\d{1,2})/(?P<d>\d{1,2})(?:/|$)")
_RE_PATH_YM = re.compile(r"/(?P<y>(?:19|20)\d{2})/(?P<mo>\d{1,2})(?:/|$)")
_RE_PATH_Y = re.compile(r"/(?P<y>(?:19|20)\d{2})(?:/|$)")

# --- Fecha embebida en UN SOLO nombre de carpeta -----------------------------
# Orden europeo (día primero) por defecto para formatos ambiguos como 02102009.
PREFER_DAY_FIRST = os.getenv("DATE_PREFER_DAY_FIRST", "1") not in ("0", "false", "False")

# AAAA[sep]MM[sep]DD  (ISO / año primero): 2009-10-02, 20091002
_C_YMD = re.compile(r"(?<!\d)(?P<y>(?:19|20)\d{2})[-._]?(?P<mo>\d{2})[-._]?(?P<d>\d{2})(?!\d)")
# DD[sep]MM[sep]AAAA / MM[sep]DD[sep]AAAA (año al final): 02102009, 02-10-2009
_C_DMY = re.compile(r"(?<!\d)(?P<a>\d{2})[-._]?(?P<b>\d{2})[-._]?(?P<y>(?:19|20)\d{2})(?!\d)")
# AAAA[sep]MM (mes/año): 200910, 2009-10
_C_YM = re.compile(r"(?<!\d)(?P<y>(?:19|20)\d{2})[-._]?(?P<mo>\d{2})(?!\d)")
# MM[sep]AAAA (mes/año, europeo): 102009, 10-2009
_C_MY = re.compile(r"(?<!\d)(?P<mo>\d{2})[-._]?(?P<y>(?:19|20)\d{2})(?!\d)")
# AAAA aislado
_C_Y = re.compile(r"(?<!\d)(?P<y>(?:19|20)\d{2})(?!\d)")


def _detect_component(name: str, source: str = "path") -> DetectedDate:
    """
    Detecta una fecha embebida en un ÚNICO componente (nombre de carpeta), incluidos
    formatos compactos y orden europeo día-primero. Devuelve el candidato de mayor
    precisión que valide.
    """
    # FULL_DATE — ISO (año primero)
    m = _C_YMD.search(name)
    if m:
        y, mo, d = int(m["y"]), int(m["mo"]), int(m["d"])
        if _valid_ymd(y, mo, d):
            return DetectedDate(Precision.FULL_DATE, 0.85, m.group(0), source,
                                y, mo, d, notes=["fecha en carpeta (AAAA-MM-DD)"])
    # FULL_DATE — día/mes primero, año al final (desambiguación europea)
    m = _C_DMY.search(name)
    if m:
        a, b, y = int(m["a"]), int(m["b"]), int(m["y"])
        primary = ("DD-MM", a, b) if PREFER_DAY_FIRST else ("MM-DD", b, a)
        secondary = ("MM-DD", b, a) if PREFER_DAY_FIRST else ("DD-MM", a, b)
        for label, day, month in (primary, secondary):
            if _valid_ymd(y, month, day):
                conf = 0.78 if label == primary[0] else 0.68
                return DetectedDate(Precision.FULL_DATE, conf, m.group(0), source,
                                    y, month, day,
                                    notes=[f"fecha en carpeta ({label}-AAAA)"])
    # YEAR_MONTH — AAAA-MM
    m = _C_YM.search(name)
    if m:
        y, mo = int(m["y"]), int(m["mo"])
        if _valid_year(y) and _valid_month(mo):
            return DetectedDate(Precision.YEAR_MONTH, 0.6, m.group(0), source,
                                y, mo, notes=["mes/año en carpeta (AAAA-MM)"])
    # YEAR_MONTH — MM-AAAA (europeo)
    m = _C_MY.search(name)
    if m:
        mo, y = int(m["mo"]), int(m["y"])
        if _valid_year(y) and _valid_month(mo):
            return DetectedDate(Precision.YEAR_MONTH, 0.55, m.group(0), source,
                                y, mo, notes=["mes/año en carpeta (MM-AAAA)"])
    # YEAR
    m = _C_Y.search(name)
    if m:
        y = int(m["y"])
        if _valid_year(y):
            return DetectedDate(Precision.YEAR, 0.4, m.group(0), source, y,
                                notes=["año en carpeta"])
    return DetectedDate()


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

    # 2) FULL_DATE (año primero: YYYY-MM-DD / YYYYMMDD)
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

    # 2b) FULL_DATE (día primero, año 4 cifras: DD-MM-YYYY / DDMMYYYY)
    m = _RE_FULL_DMY.search(stem)
    if m:
        a, b, y = int(m["a"]), int(m["b"]), int(m["y"])
        primary = (a, b) if PREFER_DAY_FIRST else (b, a)
        for order_i, (day, month) in enumerate(((a, b) if PREFER_DAY_FIRST else (b, a),
                                                (b, a) if PREFER_DAY_FIRST else (a, b))):
            if _valid_ymd(y, month, day):
                label = "DD-MM" if (day, month) == (a, b) else "MM-DD"
                return DetectedDate(
                    precision=Precision.FULL_DATE,
                    confidence=0.88 if order_i == 0 else 0.78,
                    matched_text=m.group(0), source="filename",
                    year=y, month=month, day=day,
                    notes=[f"fecha en nombre ({label}-AAAA)"],
                )

    # 2c) FULL_DATE con año de 2 cifras (AAMMDD): 020926 -> 2002-09-26
    m = _RE_FULL_YY.search(stem)
    if m:
        yy, mo, d = int(m["yy"]), int(m["mo"]), int(m["d"])
        y = _yy_to_year(yy)
        if y and _valid_ymd(y, mo, d):
            return DetectedDate(
                precision=Precision.FULL_DATE, confidence=0.6,
                matched_text=m.group(0), source="filename",
                year=y, month=mo, day=d, notes=["fecha en nombre (AAMMDD)"],
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
    Detecta la fecha por la ESTRUCTURA de carpetas contenedoras. Combina:
      1) jerarquía numérica /AAAA/MM/DD/, /AAAA/MM/, /AAAA/
      2) fecha embebida en UN nombre de carpeta (p. ej. 02102009, 2009-10-02)
    Se ignora el propio nombre de archivo. Devuelve el candidato de mayor precisión
    (a igualdad, mayor confianza); si el año aparece en varias carpetas, refuerza
    la confianza.
    """
    directory = os.path.dirname(path)
    norm = "/" + directory.replace("\\", "/").strip("/") + "/"
    candidates: list[DetectedDate] = []

    # 1) jerárquico
    m = _RE_PATH_YMD.search(norm)
    if m:
        y, mo, d = int(m["y"]), int(m["mo"]), int(m["d"])
        if _valid_ymd(y, mo, d):
            candidates.append(DetectedDate(
                Precision.FULL_DATE, 0.85, m.group(0).strip("/"), "path",
                y, mo, d, notes=["fecha en jerarquía de carpetas (AAAA/MM/DD)"]))
    m = _RE_PATH_YM.search(norm)
    if m:
        y, mo = int(m["y"]), int(m["mo"])
        if _valid_year(y) and _valid_month(mo):
            candidates.append(DetectedDate(
                Precision.YEAR_MONTH, 0.65, m.group(0).strip("/"), "path",
                y, mo, notes=["mes/año en jerarquía de carpetas (AAAA/MM)"]))
    m = _RE_PATH_Y.search(norm)
    if m:
        y = int(m["y"])
        if _valid_year(y):
            candidates.append(DetectedDate(
                Precision.YEAR, 0.4, m.group(0).strip("/"), "path", y,
                notes=["año en jerarquía de carpetas"]))

    # 2) por componente (fecha embebida en un solo nombre de carpeta)
    for comp in (c for c in directory.replace("\\", "/").split("/") if c):
        cand = _detect_component(comp)
        if cand.is_valid:
            candidates.append(cand)

    if not candidates:
        return DetectedDate()

    best = max(candidates, key=lambda c: (int(c.precision), c.confidence))

    # refuerzo: el año del mejor candidato aparece en varias carpetas
    years = [c.year for c in candidates if c.year]
    if best.year and years.count(best.year) >= 2:
        best.confidence = min(1.0, best.confidence + 0.1)
        best.notes.append("año confirmado por varias carpetas")
    return best


def detect_daymonth_from_filename(name: str) -> Optional[dict]:
    """
    Detecta un token día+mes (DDMM/MMDD, sin año) en el nombre de archivo, para
    COMBINAR con el año que aporte la carpeta. Orden europeo por defecto, con
    validación (descarta contadores/resoluciones que no son fechas válidas).
    Devuelve {"day", "month", "confidence", "matched", "order"} o None.
    """
    stem = os.path.splitext(os.path.basename(name))[0]
    for m in _RE_DAYMONTH.finditer(stem):
        a, b = int(m["a"]), int(m["b"])
        orders = ((a, b, "DD-MM"), (b, a, "MM-DD"))
        if not PREFER_DAY_FIRST:
            orders = ((b, a, "MM-DD"), (a, b, "DD-MM"))
        for i, (day, month, label) in enumerate(orders):
            if _valid_month(month) and _valid_day(day):
                return {"day": day, "month": month,
                        "confidence": 0.6 if i == 0 else 0.5,
                        "matched": m.group(0), "order": label}
    return None


def detect(path: str) -> DetectedDate:
    """
    Detección combinada.
      1) Si el NOMBRE contiene una fecha completa/con hora, PREVALECE.
      2) Si no, combina el día+mes del nombre (p. ej. 0209) con el año (y mes) que
         aporte la CARPETA (p. ej. 2009/ u 2009/08/).
      3) En su defecto, el mejor candidato entre nombre y carpeta.
    A igualdad de precisión gana la mayor confianza.
    """
    by_name = detect_from_filename(path)
    by_path = detect_from_path(path)

    # 1) el nombre con fecha completa prevalece sobre la carpeta
    if int(by_name.precision) >= int(Precision.FULL_DATE):
        if by_path.is_valid and by_path.year == by_name.year:
            by_name.notes.append("año también presente en la carpeta")
        return by_name

    candidates = [c for c in (by_name, by_path) if c.is_valid]

    # 2) combinar día+mes del NOMBRE con el año (y mes) de la CARPETA
    dm = detect_daymonth_from_filename(path)
    year_src = by_path if by_path.year else (by_name if by_name.year else None)
    if dm and year_src and year_src.year:
        day, month = dm["day"], dm["month"]
        notes = [f"día/mes del nombre ({dm['order']}) + año de carpeta"]
        conf = 0.75 if year_src.source == "path" else 0.7
        if by_path.month and by_path.month == month:
            conf = min(1.0, conf + 0.1)
            notes.append("mes confirmado por la carpeta")
        elif by_path.month and by_path.month != month:
            conf = max(0.4, conf - 0.2)
            notes.append(f"discrepancia de mes con la carpeta ({by_path.month:02d})")
        candidates.append(DetectedDate(
            Precision.FULL_DATE, conf, dm["matched"], "filename+path",
            year_src.year, month, day, notes=notes))

    if not candidates:
        return DetectedDate()

    best = max(candidates, key=lambda c: (int(c.precision), c.confidence))
    if best.source == "path" and by_name.is_valid and by_name.year == best.year:
        best.notes.append("año confirmado también por el nombre de archivo")
    return best


__all__ = ["Precision", "DetectedDate", "detect", "detect_from_filename", "detect_from_path"]
