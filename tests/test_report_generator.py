"""Tests de report_generator: genera un PDF válido y respeta la regla sub/super."""

import os

import pytest

try:
    import reportlab  # noqa: F401
    _HAS_RL = True
except Exception:
    _HAS_RL = False

pytestmark = pytest.mark.skipif(not _HAS_RL, reason="requiere reportlab")

import report_generator as rg


_SUMMARY = {
    "root": "/srv/media", "total_files": 120, "photos": 100, "videos": 20,
    "with_exif_date": 70, "without_exif_date": 50, "corrupt": 8,
    "inconsistent": 40, "needs_correction": 55, "read_errors": 1,
}
_L1 = [
    {"folder": "2020", "total": 80, "needs_correction": 40, "corrupt": 5, "no_exif_date": 30},
    {"folder": "2019", "total": 40, "needs_correction": 15, "corrupt": 3, "no_exif_date": 20},
]
_L2 = [
    {"folder": "2020/07", "total": 50, "needs_correction": 25, "corrupt": 2, "no_exif_date": 18},
    {"folder": "2020/08", "total": 30, "needs_correction": 15, "corrupt": 3, "no_exif_date": 12},
]


def test_generate_pdf(tmp_path):
    out = tmp_path / "informe.pdf"
    path = rg.generate_report(
        _SUMMARY, _L1, _L2, str(out),
        precision_breakdown={"FULL_DATE": 30, "YEAR": 15, "YEAR_MONTH": 10},
        duplicates_count=6,
    )
    assert os.path.isfile(path)
    data = out.read_bytes()
    assert data[:5] == b"%PDF-"          # cabecera PDF válida
    assert len(data) > 1500              # tiene contenido real


def test_superscript_uses_markup_not_unicode():
    s = rg.superscript("2")
    assert s == "<super>2</super>"
    # aseguramos que NO hay unicode de superíndice
    assert "²" not in s and "³" not in s


def test_empty_folders_ok(tmp_path):
    out = tmp_path / "vacio.pdf"
    rg.generate_report({"root": "/x", "total_files": 0}, [], [], str(out))
    assert out.read_bytes()[:5] == b"%PDF-"
