"""
Tests de metadata_analyzer.

- Unitarios: parseo de fechas, selección por prioridad, inconsistencias,
  agregación por carpeta (con tags EXIF inyectados; no requiere exiftool).
- Integración: round-trip real con exiftool sobre JPEGs generados (se salta
  si exiftool o Pillow no están disponibles).
"""

import os
import subprocess
from datetime import datetime

import pytest

import metadata_analyzer as ma
from date_detector import Precision

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


# --------------------------- unitarios --------------------------------------

def test_parse_exif_datetime_basic():
    dt = ma.parse_exif_datetime("2020:07:02 14:35:12")
    assert dt == datetime(2020, 7, 2, 14, 35, 12)


def test_parse_exif_datetime_with_subsec_tz():
    dt = ma.parse_exif_datetime("2020:07:02 14:35:12.500+02:00")
    assert dt == datetime(2020, 7, 2, 14, 35, 12)


def test_parse_exif_datetime_zero_returns_none():
    assert ma.parse_exif_datetime("0000:00:00 00:00:00") is None
    assert ma.parse_exif_datetime(None) is None


def test_pick_priority_prefers_original():
    tags = {
        "FileModifyDate": "2024:01:01 00:00:00",
        "CreateDate": "2020:07:02 10:00:00",
        "DateTimeOriginal": "2019:05:05 08:00:00",
    }
    chosen, tag, _ = ma._pick_exif_date(tags)
    assert tag == "DateTimeOriginal"
    assert chosen.startswith("2019")


def test_analyze_one_corrupt_date(tmp_path):
    f = tmp_path / "foto.jpg"
    f.write_bytes(b"not-a-real-image")  # solo para os.stat
    tags = {"DateTimeOriginal": "1800:01:01 00:00:00"}
    fm = ma.analyze_one(str(f), exif_tags=tags)
    assert fm.is_corrupt is True
    assert fm.needs_correction is True


def test_analyze_one_uses_filename_when_no_exif(tmp_path):
    f = tmp_path / "IMG_20200702_143512.jpg"
    f.write_bytes(b"x")
    fm = ma.analyze_one(str(f), exif_tags={})
    assert fm.has_exif_date is False
    assert fm.needs_correction is True
    assert fm.recommended_date == "2020:07:02 14:35:12"
    assert fm.recommended_source == "filename"


def test_analyze_one_consistent_no_correction(tmp_path):
    f = tmp_path / "IMG_20200702_143512.jpg"
    f.write_bytes(b"x")
    tags = {"DateTimeOriginal": "2020:07:02 14:35:12"}
    fm = ma.analyze_one(str(f), exif_tags=tags)
    assert fm.has_exif_date is True
    assert fm.is_corrupt is False
    # año coincide con nombre -> sin inconsistencias -> sin corrección
    assert fm.needs_correction is False


def test_analyze_one_year_mismatch(tmp_path):
    f = tmp_path / "IMG_20200702_143512.jpg"
    f.write_bytes(b"x")
    tags = {"DateTimeOriginal": "2015:01:01 00:00:00"}
    fm = ma.analyze_one(str(f), exif_tags=tags)
    assert any("!=" in i for i in fm.inconsistencies)
    assert fm.needs_correction is True


def test_folder_levels():
    root = "/srv/media"
    l1, l2 = ma._folder_levels(root, "/srv/media/2020/07/foto.jpg")
    assert l1 == "2020"
    assert l2 == os.path.join("2020", "07")


# --------------------------- integración ------------------------------------

def _make_jpeg(path, exif_date=None):
    img = Image.new("RGB", (2, 2), (200, 30, 30))
    img.save(path, "JPEG")
    if exif_date:
        subprocess.run(
            ["exiftool", "-overwrite_original", f"-DateTimeOriginal={exif_date}", str(path)],
            capture_output=True, check=True,
        )


@pytest.mark.skipif(not _HAS_PIL or not ma.exiftool_available(),
                    reason="requiere Pillow y exiftool")
def test_integration_real_exif(tmp_path):
    good = tmp_path / "2020" / "07" / "IMG_20200702_143512.jpg"
    good.parent.mkdir(parents=True)
    _make_jpeg(good, exif_date="2020:07:02 14:35:12")

    fm = ma.analyze_one(str(good))
    assert fm.read_ok is True
    assert fm.has_exif_date is True
    assert fm.exif_datetime == datetime(2020, 7, 2, 14, 35, 12)
    assert fm.is_corrupt is False


@pytest.mark.skipif(not _HAS_PIL or not ma.exiftool_available(),
                    reason="requiere Pillow y exiftool")
def test_integration_analyze_folder(tmp_path):
    # árbol: 2020/07 (2 fotos), 2019 (1 foto sin exif con fecha en nombre)
    (tmp_path / "2020" / "07").mkdir(parents=True)
    (tmp_path / "2019").mkdir(parents=True)
    _make_jpeg(tmp_path / "2020" / "07" / "a_20200702.jpg", exif_date="2020:07:02 10:00:00")
    _make_jpeg(tmp_path / "2020" / "07" / "b_20200703.jpg", exif_date="1799:01:01 00:00:00")  # corrupto
    _make_jpeg(tmp_path / "2019" / "IMG_20190105_101010.jpg")  # sin DateTimeOriginal

    seen = []
    res = ma.analyze_folder(str(tmp_path), progress_cb=lambda p: seen.append(p))

    assert res.total_files == 3
    assert res.photos == 3
    assert res.corrupt == 1
    # ordenación de carpetas nivel 1 descendente por total
    assert res.level1_folders[0]["total"] >= res.level1_folders[-1]["total"]
    l1_names = {f["folder"] for f in res.level1_folders}
    assert {"2020", "2019"} <= l1_names
    # progreso emitido al menos una vez con el total final
    assert seen and seen[-1]["processed"] == 3
