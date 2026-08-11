"""Tests de date_detector: detección por nombre y por estructura de carpetas."""

import date_detector as dd
from date_detector import Precision


def test_datetime_full():
    r = dd.detect_from_filename("IMG_20200702_143512.jpg")
    assert r.precision == Precision.DATETIME
    assert (r.year, r.month, r.day, r.hour, r.minute, r.second) == (2020, 7, 2, 14, 35, 12)
    assert r.to_exif_string() == "2020:07:02 14:35:12"


def test_full_date_dashes():
    r = dd.detect_from_filename("vacaciones 2020-07-02 playa.png")
    assert r.precision == Precision.FULL_DATE
    assert (r.year, r.month, r.day) == (2020, 7, 2)
    assert r.confidence >= 0.85


def test_full_date_compact():
    r = dd.detect_from_filename("20200702.mp4")
    assert r.precision == Precision.FULL_DATE
    assert (r.year, r.month, r.day) == (2020, 7, 2)


def test_year_month():
    r = dd.detect_from_filename("album-2020-07.zip")
    assert r.precision == Precision.YEAR_MONTH
    assert (r.year, r.month) == (2020, 7)
    assert r.to_exif_string() == "2020:07:01 00:00:00"


def test_year_only():
    r = dd.detect_from_filename("recuerdos 2020.heic")
    assert r.precision == Precision.YEAR
    assert r.year == 2020
    assert r.to_exif_string() == "2020:01:01 00:00:00"


def test_none():
    r = dd.detect_from_filename("captura_de_pantalla.png")
    assert r.precision == Precision.NONE
    assert not r.is_valid
    assert r.to_datetime() is None


def test_invalid_month_rejected():
    # 13 no es un mes válido -> no debe clasificar como fecha completa
    r = dd.detect_from_filename("2020-13-40.jpg")
    assert r.precision != Precision.FULL_DATE


def test_out_of_range_year_rejected():
    r = dd.detect_from_filename("1850-07-02.jpg")
    assert r.precision == Precision.NONE


def test_path_ymd():
    r = dd.detect_from_path("/srv/media/2020/07/02/foto.jpg")
    assert r.precision == Precision.FULL_DATE
    assert (r.year, r.month, r.day) == (2020, 7, 2)
    assert r.source == "path"


def test_path_ym():
    r = dd.detect_from_path("/srv/media/2020/07/foto.jpg")
    assert r.precision == Precision.YEAR_MONTH
    assert (r.year, r.month) == (2020, 7)


def test_path_year():
    r = dd.detect_from_path("/srv/media/2020/foto.jpg")
    assert r.precision == Precision.YEAR
    assert r.year == 2020


def test_combined_prefers_higher_precision():
    # nombre da datetime, carpeta solo año -> gana el nombre (datetime)
    r = dd.detect("/srv/media/2020/IMG_20200702_143512.jpg")
    assert r.precision == Precision.DATETIME
    assert r.source == "filename"


def test_combined_falls_back_to_path():
    # nombre no aporta fecha, carpeta sí
    r = dd.detect("/srv/media/2020/07/02/DSC_0001.jpg")
    assert r.precision == Precision.FULL_DATE
    assert r.source == "path"


def test_combined_none():
    r = dd.detect("/srv/media/misc/DSC_0001.jpg")
    assert r.precision == Precision.NONE


# --- fecha embebida en un único nombre de carpeta ---------------------------

def test_path_compact_ddmmyyyy():
    # caso reportado: 2009/02102009 = 2 de octubre de 2009 (europeo)
    r = dd.detect_from_path("/srv/media/2009/02102009/IMG_0006.JPG")
    assert r.precision == Precision.FULL_DATE
    assert (r.year, r.month, r.day) == (2009, 10, 2)
    assert r.to_exif_string() == "2009:10:02 00:00:00"


def test_path_compact_ddmmyyyy_full_flow():
    r = dd.detect("/srv/media/2009/02102009/IMG_0006.JPG")
    assert r.precision == Precision.FULL_DATE
    assert r.to_exif_string() == "2009:10:02 00:00:00"


def test_path_compact_iso_yyyymmdd():
    r = dd.detect_from_path("/srv/media/2009/20091002/x.jpg")
    assert r.precision == Precision.FULL_DATE
    assert (r.year, r.month, r.day) == (2009, 10, 2)


def test_path_dashed_daymonth_year():
    r = dd.detect_from_path("/srv/media/02-10-2009/x.jpg")
    assert r.precision == Precision.FULL_DATE
    assert (r.year, r.month, r.day) == (2009, 10, 2)


def test_path_iso_dashed_folder():
    r = dd.detect_from_path("/srv/media/2020-07-02/x.jpg")
    assert r.precision == Precision.FULL_DATE
    assert (r.year, r.month, r.day) == (2020, 7, 2)


def test_path_month_year_folder():
    r = dd.detect_from_path("/srv/media/10-2009/x.jpg")
    assert r.precision == Precision.YEAR_MONTH
    assert (r.year, r.month) == (2009, 10)


def test_path_disambiguation_month_gt_12():
    # 25122009: 25 no es mes -> día=25, mes=12 (Navidad 2009)
    r = dd.detect_from_path("/srv/media/25122009/x.jpg")
    assert r.precision == Precision.FULL_DATE
    assert (r.year, r.month, r.day) == (2009, 12, 25)


def test_path_hierarchical_still_works():
    r = dd.detect_from_path("/srv/media/2020/07/02/x.jpg")
    assert r.precision == Precision.FULL_DATE
    assert (r.year, r.month, r.day) == (2020, 7, 2)


def test_path_non_date_8digits_no_false_positive():
    r = dd.detect_from_path("/srv/media/12345678/x.jpg")
    assert r.precision == Precision.NONE
