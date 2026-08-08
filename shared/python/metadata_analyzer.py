"""
metadata_analyzer.py — Lectura y análisis de metadatos con exiftool.

- Lee EXIF/QuickTime en JSON con exiftool para fotos y vídeos.
- Extrae la fecha priorizando:
      DateTimeOriginal > CreateDate/DateTime > MediaCreateDate/CreationDate/
      CreationTime (vídeo) > FileModifyDate.
- Detecta inconsistencias entre EXIF, nombre de archivo, ruta y fecha del sistema.
- Marca metadatos corruptos (fechas fuera de rango razonable).
- Calcula estadísticas globales y por carpeta (nivel 1 y 2), ordenadas de más a
  menos por nº de archivos.

Emite progreso opcional mediante un callback (para WebSocket).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Callable, Iterable, Optional

import date_detector as dd
from date_detector import Precision

# --- Configuración -----------------------------------------------------------
EXIFTOOL_BIN = os.getenv("EXIFTOOL_BIN", "exiftool")
DATE_MIN_YEAR = int(os.getenv("DATE_MIN_YEAR", "1990"))
DATE_MAX_YEAR_OFFSET = int(os.getenv("DATE_MAX_YEAR_OFFSET", "5"))

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff",
              ".webp", ".gif", ".bmp", ".dng", ".cr2", ".cr3", ".nef",
              ".arw", ".rw2", ".orf", ".raf"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".3gp", ".mts",
              ".m2ts", ".wmv", ".flv", ".webm", ".mpg", ".mpeg"}
MEDIA_EXTS = PHOTO_EXTS | VIDEO_EXTS

# Orden de prioridad de tags de fecha (foto + vídeo).
DATE_TAG_PRIORITY = [
    "DateTimeOriginal",
    "CreateDate",
    "DateTime",
    "MediaCreateDate",
    "CreationDate",
    "CreationTime",
    "TrackCreateDate",
    "FileModifyDate",
]

# Formatos que devuelve exiftool para fechas.
_EXIF_DATE_FORMATS = [
    "%Y:%m:%d %H:%M:%S",
    "%Y:%m:%d %H:%M:%S%z",
    "%Y:%m:%d %H:%M:%SZ",
    "%Y-%m-%d %H:%M:%S",
    "%Y:%m:%d",
]


def _max_year() -> int:
    return datetime.now().year + DATE_MAX_YEAR_OFFSET


def exiftool_available() -> bool:
    return shutil.which(EXIFTOOL_BIN) is not None


def parse_exif_datetime(raw: Optional[str]) -> Optional[datetime]:
    """Parsea una fecha EXIF a datetime naive. Devuelve None si no se puede."""
    if not raw or not isinstance(raw, str):
        return None
    s = raw.strip()
    # exiftool usa a veces subsegundos y zona: recortamos subsegundos.
    if "." in s:
        # 2020:07:02 14:35:12.500+02:00 -> quita ".500"
        head, _, tail = s.partition(".")
        tz = ""
        for i, ch in enumerate(tail):
            if ch in "+-Z":
                tz = tail[i:]
                break
        s = head + tz
    for fmt in _EXIF_DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return None


def _date_in_range(dt: Optional[datetime]) -> bool:
    if dt is None:
        return False
    return DATE_MIN_YEAR <= dt.year <= _max_year()


@dataclass
class FileMetadata:
    """Resultado del análisis de un único archivo."""
    path: str
    media_type: str = "unknown"          # "photo" | "video" | "unknown"
    size_bytes: int = 0
    read_ok: bool = False
    error: Optional[str] = None

    # fecha EXIF elegida
    exif_date: Optional[str] = None       # string EXIF normalizado
    exif_date_tag: Optional[str] = None   # tag del que salió
    exif_datetime: Optional[datetime] = None
    all_date_tags: dict = field(default_factory=dict)

    # fechas alternativas
    filename_date: Optional[str] = None
    filename_precision: str = Precision.NONE.label
    path_date: Optional[str] = None
    path_precision: str = Precision.NONE.label
    filesystem_mtime: Optional[str] = None

    # diagnóstico
    has_exif_date: bool = False
    is_corrupt: bool = False              # fecha EXIF fuera de rango
    inconsistencies: list[str] = field(default_factory=list)
    needs_correction: bool = False
    recommended_date: Optional[str] = None
    recommended_precision: str = Precision.NONE.label
    recommended_source: Optional[str] = None

    def as_dict(self) -> dict:
        d = asdict(self)
        for k in ("exif_datetime",):
            if d.get(k) is not None:
                d[k] = self.__dict__[k].isoformat()
        return d


def _media_type(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in PHOTO_EXTS:
        return "photo"
    if ext in VIDEO_EXTS:
        return "video"
    return "unknown"


def run_exiftool(paths: list[str]) -> list[dict]:
    """
    Ejecuta exiftool sobre una lista de rutas y devuelve la lista de dicts JSON.
    Lanza RuntimeError si exiftool no está disponible.
    """
    if not exiftool_available():
        raise RuntimeError(f"exiftool no encontrado (EXIFTOOL_BIN={EXIFTOOL_BIN})")
    if not paths:
        return []
    cmd = [
        EXIFTOOL_BIN, "-json", "-n", "-charset", "filename=utf8",
        "-api", "largefilesupport=1",
        "-DateTimeOriginal", "-CreateDate", "-DateTime", "-ModifyDate",
        "-MediaCreateDate", "-CreationDate", "-CreationTime", "-TrackCreateDate",
        "-FileModifyDate", "-FileSize", "-MIMEType",
        *paths,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    out = proc.stdout.strip()
    if not out:
        # exiftool falla por completo (p. ej. ninguna ruta legible)
        if proc.returncode != 0 and proc.stderr:
            raise RuntimeError(f"exiftool error: {proc.stderr.strip()[:300]}")
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"salida de exiftool no parseable: {e}")


def _pick_exif_date(tags: dict) -> tuple[Optional[str], Optional[str], dict]:
    """
    Devuelve (valor_elegido, tag_elegido, todos_los_tags_de_fecha) según la
    prioridad DATE_TAG_PRIORITY.
    """
    found: dict[str, str] = {}
    for tag in DATE_TAG_PRIORITY:
        val = tags.get(tag)
        if isinstance(val, str) and val.strip() and not val.startswith("0000"):
            found[tag] = val
    for tag in DATE_TAG_PRIORITY:
        if tag in found:
            return found[tag], tag, found
    return None, None, found


def analyze_one(path: str, exif_tags: Optional[dict] = None) -> FileMetadata:
    """
    Analiza un archivo. Si `exif_tags` se pasa (dict de exiftool ya leído) se usa;
    si no, se invoca exiftool para ese archivo.
    """
    fm = FileMetadata(path=path, media_type=_media_type(path))
    try:
        st = os.stat(path)
        fm.size_bytes = st.st_size
        fm.filesystem_mtime = datetime.fromtimestamp(st.st_mtime).strftime("%Y:%m:%d %H:%M:%S")
    except OSError as e:
        fm.error = f"stat: {e}"
        return fm

    if exif_tags is None:
        try:
            batch = run_exiftool([path])
            exif_tags = batch[0] if batch else {}
        except RuntimeError as e:
            fm.error = str(e)
            return fm

    fm.read_ok = True

    # --- fecha EXIF elegida ---
    chosen, chosen_tag, all_tags = _pick_exif_date(exif_tags)
    fm.all_date_tags = all_tags
    fm.exif_date = chosen
    fm.exif_date_tag = chosen_tag
    fm.exif_datetime = parse_exif_datetime(chosen)
    fm.has_exif_date = fm.exif_datetime is not None and chosen_tag not in (None, "FileModifyDate")

    # --- fechas por nombre y ruta ---
    by_name = dd.detect_from_filename(path)
    by_path = dd.detect_from_path(path)
    if by_name.is_valid:
        fm.filename_date = by_name.to_exif_string()
        fm.filename_precision = by_name.precision.label
    if by_path.is_valid:
        fm.path_date = by_path.to_exif_string()
        fm.path_precision = by_path.precision.label

    # --- corrupción: fecha EXIF fuera de rango ---
    if fm.exif_datetime is not None and not _date_in_range(fm.exif_datetime):
        fm.is_corrupt = True
        fm.inconsistencies.append(
            f"fecha EXIF fuera de rango ({fm.exif_datetime.year}) en {chosen_tag}"
        )

    # --- inconsistencias entre fuentes ---
    fm.inconsistencies.extend(_detect_inconsistencies(fm, by_name, by_path))

    # --- recomendación de corrección ---
    _fill_recommendation(fm, by_name, by_path)

    return fm


def _detect_inconsistencies(fm: FileMetadata, by_name, by_path) -> list[str]:
    issues: list[str] = []
    exif_dt = fm.exif_datetime

    if fm.has_exif_date and exif_dt is not None:
        # comparar año con nombre / ruta cuando existan
        for cand, src in ((by_name, "nombre"), (by_path, "carpeta")):
            if cand.is_valid and cand.year and cand.year != exif_dt.year:
                issues.append(
                    f"año EXIF ({exif_dt.year}) != año en {src} ({cand.year})"
                )
        # fecha del sistema muy alejada (posible metadato dudoso)
        fs = parse_exif_datetime(fm.filesystem_mtime)
        if fs and abs((fs - exif_dt).days) > 365 and by_name.is_valid is False and by_path.is_valid is False:
            issues.append("EXIF difiere >1 año de la fecha del sistema (sin otra referencia)")
    else:
        # sin fecha EXIF fiable
        if by_name.is_valid or by_path.is_valid:
            issues.append("sin fecha EXIF fiable; hay fecha en nombre/carpeta")
        else:
            issues.append("sin fecha EXIF fiable ni pistas en nombre/carpeta")
    return issues


def _fill_recommendation(fm: FileMetadata, by_name, by_path) -> None:
    """
    Determina la mejor fecha propuesta y si el archivo necesita corrección.
    Prioridad de fuente de referencia: nombre (mayor precisión) > carpeta.
    La fecha EXIF se considera válida solo si no es corrupta y es fiable.
    """
    # Mejor candidato entre nombre y carpeta
    cands = [c for c in (by_name, by_path) if c.is_valid]
    best = max(cands, key=lambda c: (int(c.precision), c.confidence)) if cands else None

    exif_ok = fm.has_exif_date and not fm.is_corrupt

    if exif_ok and not fm.inconsistencies:
        fm.needs_correction = False
        return

    if best is not None:
        fm.recommended_date = best.to_exif_string()
        fm.recommended_precision = best.precision.label
        fm.recommended_source = best.source
        fm.needs_correction = True
    elif fm.is_corrupt:
        # corrupto y sin referencia: marcar para limpieza (borrar fecha corrupta)
        fm.needs_correction = True
        fm.recommended_source = "cleanup"
        fm.recommended_precision = Precision.NONE.label
    else:
        fm.needs_correction = bool(fm.inconsistencies) and not exif_ok


# --- Recorrido de carpetas + estadísticas -----------------------------------

def iter_media_files(root: str, max_depth: Optional[int] = None) -> Iterable[str]:
    """Genera rutas de archivos multimedia bajo `root`, respetando max_depth."""
    root = os.path.abspath(root)
    root_depth = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root):
        if max_depth is not None:
            cur_depth = dirpath.rstrip(os.sep).count(os.sep) - root_depth
            if cur_depth >= max_depth:
                dirnames[:] = []
        for name in filenames:
            if os.path.splitext(name)[1].lower() in MEDIA_EXTS:
                yield os.path.join(dirpath, name)


def _folder_levels(root: str, path: str) -> tuple[str, str]:
    """Devuelve (carpeta_nivel1, carpeta_nivel2) relativas a root."""
    rel = os.path.relpath(os.path.dirname(path), root)
    if rel == ".":
        return ("(raíz)", "(raíz)")
    parts = rel.split(os.sep)
    lvl1 = parts[0]
    lvl2 = os.path.join(parts[0], parts[1]) if len(parts) > 1 else parts[0]
    return (lvl1, lvl2)


@dataclass
class FolderStat:
    folder: str
    total: int = 0
    needs_correction: int = 0
    corrupt: int = 0
    no_exif_date: int = 0


@dataclass
class AnalysisResult:
    root: str
    total_files: int = 0
    photos: int = 0
    videos: int = 0
    read_errors: int = 0
    with_exif_date: int = 0
    without_exif_date: int = 0
    corrupt: int = 0
    inconsistent: int = 0
    needs_correction: int = 0
    precision_breakdown: dict = field(default_factory=dict)
    level1_folders: list[dict] = field(default_factory=list)
    level2_folders: list[dict] = field(default_factory=list)
    files: list[FileMetadata] = field(default_factory=list)
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    def summary_dict(self) -> dict:
        d = asdict(self)
        d.pop("files", None)  # el resumen no incluye el detalle por archivo
        return d


ProgressCb = Callable[[dict], None]


def analyze_folder(
    root: str,
    max_depth: Optional[int] = None,
    progress_cb: Optional[ProgressCb] = None,
    batch_size: int = 200,
    keep_files: bool = True,
) -> AnalysisResult:
    """
    Analiza recursivamente una carpeta. Procesa en lotes con exiftool (rápido) y
    emite progreso por `progress_cb` (dict con archivo actual, procesados/total,
    inconsistencias acumuladas).
    """
    root = os.path.abspath(root)
    result = AnalysisResult(root=root, started_at=datetime.now().isoformat())

    all_files = list(iter_media_files(root, max_depth=max_depth))
    total = len(all_files)
    result.total_files = total

    lvl1_stats: dict[str, FolderStat] = defaultdict(lambda: FolderStat(folder=""))
    lvl2_stats: dict[str, FolderStat] = defaultdict(lambda: FolderStat(folder=""))
    precision_counter: Counter[str] = Counter()
    processed = 0

    for i in range(0, total, batch_size):
        chunk = all_files[i:i + batch_size]
        try:
            exif_batch = run_exiftool(chunk)
        except RuntimeError:
            exif_batch = []
        # exiftool preserva el orden y añade SourceFile
        by_source = {os.path.abspath(d.get("SourceFile", "")): d for d in exif_batch}

        for path in chunk:
            tags = by_source.get(os.path.abspath(path))
            fm = analyze_one(path, exif_tags=tags if tags is not None else {})
            processed += 1

            # agregados
            if fm.media_type == "photo":
                result.photos += 1
            elif fm.media_type == "video":
                result.videos += 1
            if fm.error:
                result.read_errors += 1
            if fm.has_exif_date:
                result.with_exif_date += 1
            else:
                result.without_exif_date += 1
            if fm.is_corrupt:
                result.corrupt += 1
            if fm.inconsistencies:
                result.inconsistent += 1
            if fm.needs_correction:
                result.needs_correction += 1

            precision_counter[fm.recommended_precision or Precision.NONE.label] += 1

            l1, l2 = _folder_levels(root, path)
            for key, store in ((l1, lvl1_stats), (l2, lvl2_stats)):
                s = store[key]
                s.folder = key
                s.total += 1
                if fm.needs_correction:
                    s.needs_correction += 1
                if fm.is_corrupt:
                    s.corrupt += 1
                if not fm.has_exif_date:
                    s.no_exif_date += 1

            if keep_files:
                result.files.append(fm)

            if progress_cb and (processed % 10 == 0 or processed == total):
                progress_cb({
                    "current_file": path,
                    "processed": processed,
                    "total": total,
                    "inconsistencies": result.inconsistent,
                    "needs_correction": result.needs_correction,
                    "percent": round(processed / total * 100, 1) if total else 100.0,
                })

    # ordenar carpetas de más a menos por nº de archivos
    result.level1_folders = [
        asdict(s) for s in sorted(lvl1_stats.values(), key=lambda x: x.total, reverse=True)
    ]
    result.level2_folders = [
        asdict(s) for s in sorted(lvl2_stats.values(), key=lambda x: x.total, reverse=True)
    ]
    result.precision_breakdown = dict(precision_counter)
    result.finished_at = datetime.now().isoformat()
    return result


__all__ = [
    "FileMetadata", "AnalysisResult", "FolderStat",
    "analyze_one", "analyze_folder", "iter_media_files",
    "run_exiftool", "parse_exif_datetime", "exiftool_available",
    "PHOTO_EXTS", "VIDEO_EXTS", "MEDIA_EXTS", "DATE_TAG_PRIORITY",
]
