"""Tests del parser de patrones por tokens (override manual)."""

import pattern_parser as pp
from date_detector import Precision


def test_iso_pattern():
    d = pp.apply_pattern("2009-10-02", "AAAA-MM-DD")
    assert (d.year, d.month, d.day) == (2009, 10, 2)
    assert d.precision == Precision.FULL_DATE


def test_compact_pattern_no_separators():
    # patrón con separadores reconoce texto compacto
    d = pp.apply_pattern("02102009", "DD-MM-AAAA")
    assert (d.year, d.month, d.day) == (2009, 10, 2)


def test_ddmmaaaa_compact_pattern():
    d = pp.apply_pattern("02102009", "DDMMAAAA")
    assert (d.year, d.month, d.day) == (2009, 10, 2)


def test_mdy_american():
    d = pp.apply_pattern("10-02-2009", "MM-DD-AAAA")
    assert (d.year, d.month, d.day) == (2009, 10, 2)


def test_yymmdd():
    d = pp.apply_pattern("020926", "AAMMDD")
    assert (d.year, d.month, d.day) == (2002, 9, 26)


def test_year_month_precision():
    d = pp.apply_pattern("2009-08", "AAAA-MM")
    assert d.precision == Precision.YEAR_MONTH
    assert (d.year, d.month) == (2009, 8)


def test_datetime_pattern():
    d = pp.apply_pattern("20200702_143512", "AAAAMMDD_hhmmss")
    assert d.precision == Precision.DATETIME
    assert d.to_exif_string() == "2020:07:02 14:35:12"


def test_invalid_month_rejected():
    assert pp.apply_pattern("2009-13-02", "AAAA-MM-DD") is None


def test_pattern_without_year_rejected():
    assert pp.apply_pattern("1002", "DDMM") is None


def test_resolve_from_folder():
    d = pp.resolve("/media/2009/02102009/IMG_0006.JPG", "DDMMAAAA", "auto")
    assert (d.year, d.month, d.day) == (2009, 10, 2)


def test_resolve_from_filename():
    d = pp.resolve("/media/random/IMG_20060126.jpg", "AAAAMMDD", "auto")
    assert (d.year, d.month, d.day) == (2006, 1, 26)


def test_resolve_daymonth_folderyear_sentinel():
    d = pp.resolve("/media/2009/IMGRANDOM_0209.jpg", pp.DAYMONTH_FOLDERYEAR, "auto")
    assert (d.year, d.month, d.day) == (2009, 9, 2)


def test_presets_exist():
    keys = {p["key"] for p in pp.PRESETS}
    assert {"iso", "dmy", "yymmdd", "daymonth_folderyear"} <= keys
