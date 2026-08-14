"""
Tests de reorganize_engine (Fase 2: mover archivos por fecha, sin tocar EXIF).

- compute_base_folder: pela subcarpetas de fecha.
- build_target_dir / format_layout: layouts de tokens.
- plan_reorganize: nunca fabrica fecha; colisiones -> sufijo automático.
- dry-run: NUNCA mueve nada.
- real: mueve con fallback EXDEV, registra en BD, abort+restore por ratio de error.
- undo_run: deshace un run real completo.
"""

from datetime import datetime

import pytest

import reorganize_engine as re_
from database_manager import DatabaseManager


# --------------------------- compute_base_folder ------------------------------

def test_compute_base_folder_peels_hierarchical_date():
    assert re_.compute_base_folder("/fotos/2009/08/02/IMG_0001.jpg") == "/fotos"


def test_compute_base_folder_peels_compact_folder():
    assert re_.compute_base_folder("/fotos/20090802/IMG_0001.jpg") == "/fotos"


def test_compute_base_folder_stops_at_non_date_folder():
    assert re_.compute_base_folder("/fotos/vacaciones/2009/IMG_0001.jpg") == "/fotos/vacaciones"


def test_compute_base_folder_no_date_folders():
    assert re_.compute_base_folder("/fotos/varios/IMG_0001.jpg") == "/fotos/varios"


# --- raíz = carpeta con TEXTO + FECHA: se conserva, no se pela ----------------

@pytest.mark.parametrize("root_name", ["vacaciones 2009", "vacaciones 200908",
                                       "vacaciones_2009-08-02", "boda 02-10-2009"])
def test_compute_base_folder_keeps_text_plus_date_root(root_name):
    path = f"/fotos/{root_name}/2009/08/IMG_0001.jpg"
    assert re_.compute_base_folder(path) == f"/fotos/{root_name}"


@pytest.mark.parametrize("comp", ["2009", "20090802", "2009-08", "2009.08.02", "08", "2"])
def test_pure_date_components_are_still_peeled(comp):
    assert re_._component_is_date_like(comp) is True


@pytest.mark.parametrize("comp", ["vacaciones 2009", "vacaciones200908", "IMG_2009",
                                  "varios", "2009 fotos"])
def test_text_plus_date_components_are_not_peeled(comp):
    assert re_._component_is_date_like(comp) is False


# --- el pelado nunca sube por encima de la raíz analizada ---------------------

def test_compute_base_folder_never_climbs_above_stop_at():
    # la raíz analizada se llama literalmente "2009": sin el tope, los archivos
    # acabarían fuera del árbol analizado.
    assert re_.compute_base_folder("/fotos/2009/08/IMG.jpg", stop_at="/fotos/2009") == "/fotos/2009"
    assert re_.compute_base_folder("/fotos/2009/IMG.jpg", stop_at="/fotos/2009") == "/fotos/2009"


def test_compute_base_folder_stop_at_outside_path_is_ignored():
    assert re_.compute_base_folder("/otro/2009/IMG.jpg", stop_at="/fotos") == "/otro"


# --------------------------- layout -------------------------------------------

def test_format_layout_tokens():
    dt = datetime(2020, 7, 2, 13, 5, 9)
    assert re_.format_layout("AAAA/MM", dt) == "2020/07"
    assert re_.format_layout("AAAA-MM", dt) == "2020-07"
    assert re_.format_layout("AAAA/MM/DD", dt) == "2020/07/02"
    assert re_.format_layout("AA", dt) == "20"


def test_build_target_dir_nested():
    dt = datetime(2020, 7, 2)
    assert re_.build_target_dir("/fotos", "AAAA/MM", dt) == "/fotos/2020/07"


# --------------------------- resolve_row_date ---------------------------------

def test_resolve_row_date_session_recommended():
    row = {"needs_correction": True, "recommended_date": "2020:07:02 00:00:00", "path": "/a.jpg"}
    dt = re_.resolve_row_date(row, "session")
    assert dt == datetime(2020, 7, 2)


def test_resolve_row_date_session_exif_fallback():
    row = {"needs_correction": False, "has_exif_date": True,
           "exif_date": "2018:01:01 00:00:00", "path": "/a.jpg"}
    dt = re_.resolve_row_date(row, "session")
    assert dt == datetime(2018, 1, 1)


def test_resolve_row_date_never_fabricates():
    row = {"needs_correction": False, "has_exif_date": False, "path": "/a.jpg"}
    assert re_.resolve_row_date(row, "session") is None


def test_resolve_row_date_exif_live_uses_reader():
    row = {"path": "/a.jpg"}
    dt = re_.resolve_row_date(row, "exif_live", live_reader=lambda p: "2021:03:04 00:00:00")
    assert dt == datetime(2021, 3, 4)


# --------------------------- plan_reorganize -----------------------------------

def test_plan_reorganize_skips_without_date():
    rows = [{"path": "/fotos/varios/a.jpg", "needs_correction": False, "has_exif_date": False}]
    plans = re_.plan_reorganize(rows, "auto", None, "AAAA/MM", "session")
    assert plans[0].action == "skip"
    assert "sin fecha" in plans[0].reason


def test_plan_reorganize_auto_base():
    rows = [{"path": "/fotos/2009/08/02/IMG.jpg", "needs_correction": True,
             "recommended_date": "2009:08:02 00:00:00"}]
    plans = re_.plan_reorganize(rows, "auto", None, "AAAA/MM", "session")
    assert plans[0].action == "move"
    assert plans[0].target == "/fotos/2009/08/IMG.jpg"


def test_plan_reorganize_collision_renames():
    rows = [
        {"path": "/fotos/a/IMG.jpg", "needs_correction": True,
         "recommended_date": "2020:07:02 00:00:00"},
        {"path": "/fotos/b/IMG.jpg", "needs_correction": True,
         "recommended_date": "2020:07:02 00:00:00"},
    ]
    plans = re_.plan_reorganize(rows, "manual", "/fotos", "AAAA/MM", "session")
    targets = {p.target for p in plans}
    assert len(targets) == 2  # no colisión: uno de los dos gana sufijo
    assert any(t.endswith("_1.jpg") for t in targets)


def test_plan_reorganize_already_in_place_skips(tmp_path):
    target_dir = tmp_path / "2020" / "07"
    target_dir.mkdir(parents=True)
    f = target_dir / "IMG.jpg"
    f.write_text("x")
    rows = [{"path": str(f), "needs_correction": True,
             "recommended_date": "2020:07:02 00:00:00"}]
    plans = re_.plan_reorganize(rows, "manual", str(tmp_path), "AAAA/MM", "session")
    assert plans[0].action == "skip"
    assert "ya está" in plans[0].reason


# --------------------------- engine.run: dry-run -------------------------------

def test_dry_run_never_moves(tmp_path):
    f = tmp_path / "src" / "IMG.jpg"
    f.parent.mkdir()
    f.write_text("x")
    plans = [re_.ReorganizePlan(str(f), "move", target=str(tmp_path / "2020" / "07" / "IMG.jpg"))]
    eng = re_.ReorganizeEngine()
    res = eng.run(plans, dry_run=True)
    assert res.moved == 1
    assert f.exists()  # NO se movió


# --------------------------- engine.run: real -----------------------------------

def _db(tmp_path):
    db = DatabaseManager(str(tmp_path / "db.sqlite"))
    db.init_db()
    db.create_session(str(tmp_path))  # id=1, para satisfacer la FK de session_id
    return db


def test_real_run_moves_and_records(tmp_path):
    src = tmp_path / "src" / "IMG.jpg"
    src.parent.mkdir()
    src.write_text("x")
    dst = tmp_path / "2020" / "07" / "IMG.jpg"

    db = _db(tmp_path)
    plans = [re_.ReorganizePlan(str(src), "move", target=str(dst), reason="test")]
    eng = re_.ReorganizeEngine(db=db, session_id=1)
    res = eng.run(plans, dry_run=False, run_id="r1")

    assert res.moved == 1
    assert res.failed == 0
    assert not src.exists()
    assert dst.exists()
    moves = db.get_reorganize_moves(run_id="r1")
    assert moves[0]["status"] == "moved"
    assert moves[0]["new_path"] == str(dst)


def test_real_run_exdev_fallback(tmp_path, monkeypatch):
    src = tmp_path / "src.jpg"
    src.write_text("contenido")
    dst = tmp_path / "dest" / "src.jpg"

    # forzamos la rama EXDEV parcheando os.rename dentro de _do_move
    import os as _os

    def rename_raises_exdev(a, b):
        raise OSError(18, "cross-device link")  # errno.EXDEV en Linux

    monkeypatch.setattr(_os, "rename", rename_raises_exdev)
    plans = [re_.ReorganizePlan(str(src), "move", target=str(dst))]
    eng = re_.ReorganizeEngine()
    res = eng.run(plans, dry_run=False, run_id="r2")

    assert res.moved == 1
    assert not src.exists()
    assert dst.read_text() == "contenido"


def test_abort_and_restore_on_high_error_ratio(tmp_path):
    db = _db(tmp_path)
    plans = []
    good_srcs = []
    for i in range(6):
        p = tmp_path / f"good_{i}.jpg"
        p.write_text("x")
        good_srcs.append(p)
        plans.append(re_.ReorganizePlan(str(p), "move",
                                        target=str(tmp_path / "ok" / f"good_{i}.jpg")))
    for i in range(4):
        # origen inexistente -> el move falla (OSError)
        plans.append(re_.ReorganizePlan(str(tmp_path / f"missing_{i}.jpg"), "move",
                                        target=str(tmp_path / "ok" / f"bad_{i}.jpg")))

    eng = re_.ReorganizeEngine(db=db, session_id=1, error_abort_ratio=0.10, min_files_for_ratio=3)
    res = eng.run(plans, dry_run=False, run_id="r3")

    assert res.aborted is True
    assert res.reverted >= 1
    # al menos un archivo bueno ha vuelto a su carpeta original
    assert any(p.exists() for p in good_srcs)


def test_undo_run(tmp_path):
    src = tmp_path / "src" / "IMG.jpg"
    src.parent.mkdir()
    src.write_text("x")
    dst = tmp_path / "2020" / "07" / "IMG.jpg"

    db = _db(tmp_path)
    plans = [re_.ReorganizePlan(str(src), "move", target=str(dst))]
    eng = re_.ReorganizeEngine(db=db, session_id=1)
    eng.run(plans, dry_run=False, run_id="r4")
    assert dst.exists()

    result = re_.undo_run(db, "r4")
    assert result["undone"] == 1
    assert src.exists()
    assert not dst.exists()
    moves = db.get_reorganize_moves(run_id="r4")
    assert moves[0]["status"] == "reverted"
