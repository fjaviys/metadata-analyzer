"""
Tests de correction_engine.

- plan_from_file: set_date / cleanup / skip.
- dry-run: NUNCA modifica el archivo.
- real: backup -> escribir -> verificar (round-trip exiftool).
- abort + restore cuando el ratio de errores supera el umbral.
"""

import os
import subprocess

import pytest

import correction_engine as ce
import metadata_analyzer as ma

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

_REAL = _HAS_PIL and ma.exiftool_available()
skip_real = pytest.mark.skipif(not _REAL, reason="requiere Pillow y exiftool")


def _jpeg(path, exif_date=None):
    Image.new("RGB", (2, 2), (10, 120, 200)).save(path, "JPEG")
    if exif_date:
        subprocess.run(["exiftool", "-overwrite_original", f"-DateTimeOriginal={exif_date}",
                        str(path)], capture_output=True, check=True)


def _read_date(path):
    tags = ma.run_exiftool([str(path)])[0]
    return tags.get("DateTimeOriginal")


# --------------------------- plan -------------------------------------------

def test_plan_set_date():
    row = {"path": "/a.jpg", "media_type": "photo", "needs_correction": True,
           "recommended_date": "2020:07:02 00:00:00", "recommended_source": "filename",
           "recommended_precision": "FULL_DATE"}
    p = ce.plan_from_file(row)
    assert p.action == "set_date"
    assert p.target == "2020:07:02 00:00:00"


def test_plan_cleanup():
    row = {"path": "/a.jpg", "media_type": "photo", "needs_correction": True,
           "is_corrupt": True, "recommended_source": "cleanup",
           "recommended_date": None}
    p = ce.plan_from_file(row)
    assert p.action == "cleanup"


def test_plan_skip():
    row = {"path": "/a.jpg", "needs_correction": False}
    p = ce.plan_from_file(row)
    assert p.action == "skip"


# --------------------------- dry-run ----------------------------------------

@skip_real
def test_dry_run_does_not_modify(tmp_path):
    f = tmp_path / "IMG_20200702.jpg"
    _jpeg(f, exif_date="2015:01:01 00:00:00")
    before = _read_date(f)

    row = {"path": str(f), "media_type": "photo", "needs_correction": True,
           "exif_date": "2015:01:01 00:00:00", "exif_date_tag": "DateTimeOriginal",
           "recommended_date": "2020:07:02 00:00:00", "recommended_source": "filename",
           "recommended_precision": "FULL_DATE"}
    eng = ce.CorrectionEngine()  # sin backup_fn -> permitido en dry-run
    res = eng.run([row], dry_run=True)

    assert res.applied == 1
    assert res.verified == 0
    assert _read_date(f) == before  # NO cambió


def test_dry_run_no_backup_required():
    eng = ce.CorrectionEngine()
    res = eng.run([{"path": "/x.jpg", "needs_correction": False}], dry_run=True)
    assert res.skipped == 1


def test_real_run_requires_backup_fn():
    eng = ce.CorrectionEngine(backup_fn=None)
    with pytest.raises(ValueError):
        eng.run([{"path": "/x.jpg", "media_type": "photo", "needs_correction": True,
                  "recommended_date": "2020:07:02 00:00:00",
                  "recommended_source": "filename"}], dry_run=False)


# --------------------------- real -------------------------------------------

@skip_real
def test_real_set_date_verified(tmp_path):
    f = tmp_path / "IMG_20200702.jpg"
    _jpeg(f, exif_date="2015:01:01 00:00:00")
    backup_root = tmp_path / "backups"

    row = {"path": str(f), "media_type": "photo", "needs_correction": True,
           "exif_date": "2015:01:01 00:00:00", "exif_date_tag": "DateTimeOriginal",
           "recommended_date": "2020:07:02 00:00:00", "recommended_source": "filename",
           "recommended_precision": "FULL_DATE"}
    eng = ce.CorrectionEngine(backup_fn=ce.make_backup_fn(str(backup_root)))
    res = eng.run([row], dry_run=False)

    assert res.verified == 1
    assert res.failed == 0
    assert ma.parse_exif_datetime(_read_date(f)) == ma.parse_exif_datetime("2020:07:02 00:00:00")
    # backup existe
    assert any(os.path.isfile(os.path.join(dp, fn))
               for dp, _, fns in os.walk(backup_root) for fn in fns)


@skip_real
def test_abort_and_restore_on_high_error_ratio(tmp_path):
    backup_root = tmp_path / "backups"
    files = []
    good_paths = []
    # 6 buenas + 4 malas (texto) => 40% error > 10% umbral
    for i in range(6):
        p = tmp_path / f"good_{i}_20200702.jpg"
        _jpeg(p, exif_date="2015:01:01 00:00:00")
        good_paths.append(p)
        files.append({"path": str(p), "media_type": "photo", "needs_correction": True,
                      "exif_date": "2015:01:01 00:00:00", "exif_date_tag": "DateTimeOriginal",
                      "recommended_date": "2020:07:02 00:00:00",
                      "recommended_source": "filename", "recommended_precision": "FULL_DATE"})
    for i in range(4):
        p = tmp_path / f"bad_{i}.jpg"
        p.write_text("no soy una imagen")
        files.append({"path": str(p), "media_type": "photo", "needs_correction": True,
                      "exif_date": None, "exif_date_tag": None,
                      "recommended_date": "2020:07:02 00:00:00",
                      "recommended_source": "filename", "recommended_precision": "FULL_DATE"})

    eng = ce.CorrectionEngine(backup_fn=ce.make_backup_fn(str(backup_root)),
                              error_abort_ratio=0.10, min_files_for_ratio=3)
    res = eng.run(files, dry_run=False)

    assert res.aborted is True
    assert res.reverted >= 1
    # los archivos buenos ya escritos han sido restaurados a su valor original
    restored = [ma.parse_exif_datetime(_read_date(p)) for p in good_paths
                if os.path.isfile(p)]
    # al menos uno restaurado a 2015 (no quedó en 2020)
    assert any(dt is not None and dt.year == 2015 for dt in restored)


@skip_real
def test_cleanup_removes_corrupt_date(tmp_path):
    f = tmp_path / "DSC_0001.jpg"
    _jpeg(f, exif_date="1799:01:01 00:00:00")  # corrupta
    backup_root = tmp_path / "backups"
    row = {"path": str(f), "media_type": "photo", "needs_correction": True,
           "is_corrupt": True, "exif_date": "1799:01:01 00:00:00",
           "exif_date_tag": "DateTimeOriginal", "recommended_source": "cleanup",
           "recommended_date": None}
    eng = ce.CorrectionEngine(backup_fn=ce.make_backup_fn(str(backup_root)))
    res = eng.run([row], dry_run=False)
    assert res.verified == 1
    assert ma.parse_exif_datetime(_read_date(f)) is None
