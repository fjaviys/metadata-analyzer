"""
Tests de los nuevos endpoints/lógica: browse, formats, count en test,
filtro de extensiones y recursividad de la corrección.
"""

import os
import subprocess
import sys
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="ma_cfg_")
os.environ.setdefault("ALLOWED_MEDIA_ROOTS", tempfile.gettempdir())
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TMP}/test.db")
os.environ.setdefault("LOG_DIR", os.path.join(_TMP, "logs"))
os.environ.setdefault("REPORT_DIR", os.path.join(_TMP, "reports"))
os.environ.setdefault("BACKUP_DIR", os.path.join(_TMP, "backups"))

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "backend"))

import formats as fmts  # noqa: E402
import metadata_analyzer as ma  # noqa: E402

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False
_REAL = _HAS_PIL and ma.exiftool_available()

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402
import app as backend_app  # noqa: E402
from services.correction_service import _under_folder, _candidates  # noqa: E402
import services.correction_service as correction_service  # noqa: E402
from database.db import get_db  # noqa: E402


def test_pattern_presets_endpoint():
    r = client.get("/api/corrections/pattern-presets")
    assert r.status_code == 200
    keys = {p["key"] for p in r.json()["presets"]}
    assert {"iso", "dmy", "daymonth_folderyear"} <= keys


def test_override_recomputes_and_applies(tmp_path):
    db = get_db()
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "2009", "02102009"))
    sid = db.create_session(root, "local")
    fpath = os.path.join(root, "2009", "02102009", "IMG_0006.JPG")
    open(fpath, "wb").close()
    # análisis previo propuso solo el año (simulado)
    db.insert_file(sid, {
        "path": fpath, "media_type": "photo", "needs_correction": True,
        "recommended_date": "2009:01:01 00:00:00", "recommended_precision": "YEAR",
        "recommended_source": "path", "inconsistencies": [],
    }, "2009", "2009/02102009")

    # crear override con patrón DDMMAAAA sobre la carpeta 2009
    r = client.post("/api/corrections/overrides", json={
        "session_id": sid, "folder": os.path.join(root, "2009"),
        "pattern": "DDMMAAAA", "source": "auto"})
    assert r.status_code == 200
    body = r.json()
    assert body["affected"] == 1
    assert body["preview"][0]["new"] == "2009:10:02 00:00:00"

    # al aplicar overrides a los candidatos, la fecha recomendada cambia
    cands = correction_service.apply_overrides(
        sid, db.get_files(sid, needs_correction=True, limit=100))
    assert cands[0]["recommended_date"] == "2009:10:02 00:00:00"
    assert cands[0]["recommended_source"] == "override"

    # listar y borrar
    assert len(client.get("/api/corrections/overrides", params={"session_id": sid}).json()["overrides"]) == 1
    client.delete(f"/api/corrections/overrides/{body['id']}")
    assert client.get("/api/corrections/overrides", params={"session_id": sid}).json()["overrides"] == []


def test_override_rescues_unmarked_files(tmp_path):
    db = get_db()
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "2009", "02102009"))
    sid = db.create_session(root, "local")
    # archivo que el análisis NO marcó (needs_correction=False), con EXIF "correcto"
    unmarked = os.path.join(root, "2009", "02102009", "IMG_9.JPG")
    open(unmarked, "wb").close()
    db.insert_file(sid, {
        "path": unmarked, "media_type": "photo", "needs_correction": False,
        "exif_date": "2015:05:05 12:00:00", "exif_date_tag": "DateTimeOriginal",
        "has_exif_date": True, "recommended_date": None, "inconsistencies": [],
    }, "2009", "2009/02102009")

    # sin override, no es candidato
    assert correction_service.build_candidates(sid, [], root) == []

    # con override DDMMAAAA sobre 2009 -> rescata el archivo no marcado
    r = client.post("/api/corrections/overrides", json={
        "session_id": sid, "folder": os.path.join(root, "2009"),
        "pattern": "DDMMAAAA", "source": "auto"})
    assert r.status_code == 200
    body = r.json()
    assert body["affected"] == 1 and body["rescued"] == 1

    cands = correction_service.build_candidates(sid, [], root)
    assert len(cands) == 1
    assert cands[0]["recommended_date"] == "2009:10:02 00:00:00"
    assert cands[0]["recommended_source"] == "override"


def test_override_idempotent_when_exif_matches(tmp_path):
    db = get_db()
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "2009", "02102009"))
    sid = db.create_session(root, "local")
    good = os.path.join(root, "2009", "02102009", "IMG_ok.JPG")
    open(good, "wb").close()
    db.insert_file(sid, {
        "path": good, "media_type": "photo", "needs_correction": False,
        "exif_date": "2009:10:02 00:00:00", "exif_date_tag": "DateTimeOriginal",
        "has_exif_date": True, "recommended_date": None, "inconsistencies": [],
    }, "2009", "2009/02102009")
    db.add_override(sid, os.path.join(root, "2009"), "DDMMAAAA", "auto")
    # EXIF ya coincide con el patrón -> no se corrige (idempotente)
    assert correction_service.build_candidates(sid, [], root) == []


def _seed_file(db, root, sub, name, **kw):
    os.makedirs(os.path.join(root, sub), exist_ok=True)
    p = os.path.join(root, sub, name)
    open(p, "wb").close()
    row = {"path": p, "media_type": "photo", "needs_correction": kw.get("needs", True),
           "exif_date": kw.get("exif"), "exif_date_tag": "DateTimeOriginal",
           "has_exif_date": kw.get("exif") is not None,
           "filename_date": kw.get("fname"), "path_date": kw.get("pdate"),
           "recommended_date": kw.get("rec"), "recommended_precision": kw.get("prec"),
           "recommended_source": "path", "inconsistencies": []}
    db.insert_file(db_sid_cache[0], row, sub.split("/")[0], sub)
    return p


db_sid_cache = [0]


def test_date_options_lists_candidates(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local"); db_sid_cache[0] = sid
    p = _seed_file(db, root, "2009/02102009", "IMG_20081014.jpg",
                   exif="2008:10:14 12:00:00", rec="2009:01:01 00:00:00", prec="YEAR")
    r = client.get("/api/corrections/date-options", params={"session_id": sid, "path": p})
    assert r.status_code == 200
    opts = r.json()["options"]
    values = {o["value"] for o in opts}
    # EXIF, recomendada (año) y el patrón de carpeta DDMMAAAA (2009-10-02) y del nombre ISO
    assert "2008:10:14 12:00:00" in values
    assert "2009:10:02 00:00:00" in values  # de 02102009 (DDMMAAAA)
    assert "2008:10:14 00:00:00" in values  # del nombre IMG_20081014


def test_file_override_value_and_skip(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local"); db_sid_cache[0] = sid
    p = _seed_file(db, root, "2009", "IMG_x.jpg", exif="2008:10:14 12:00:00",
                   rec="2009:01:01 00:00:00", prec="YEAR")

    # fijar una fecha concreta para ese archivo
    r = client.post("/api/corrections/file-overrides", json={
        "session_id": sid, "path": p, "kind": "date_value",
        "value": "2009:10:02 00:00:00", "precision": "FULL_DATE"})
    assert r.status_code == 200 and r.json()["new"] == "2009:10:02 00:00:00"
    cands = correction_service.build_candidates(sid, [], root)
    assert cands[0]["recommended_date"] == "2009:10:02 00:00:00"
    assert cands[0]["recommended_source"] == "file-override"

    # cambiar a "no cambiar" (skip) -> excluido de candidatos
    client.post("/api/corrections/file-overrides", json={
        "session_id": sid, "path": p, "kind": "skip"})
    assert correction_service.build_candidates(sid, [], root) == []

    # borrar el override -> vuelve al comportamiento del análisis (needs_correction)
    client.delete("/api/corrections/file-overrides", params={"session_id": sid, "path": p})
    assert client.get("/api/corrections/file-overrides", params={"session_id": sid}).json()["file_overrides"] == []
    assert len(correction_service.build_candidates(sid, [], root)) == 1


def test_file_override_pattern_resolves(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local"); db_sid_cache[0] = sid
    p = _seed_file(db, root, "misc", "IMG_20081014.jpg", exif="2000:01:01 00:00:00",
                   needs=True, rec="2000:01:01 00:00:00", prec="DATETIME")
    # patrón AAAAMMDD sobre el nombre -> 2008:10:14
    r = client.post("/api/corrections/file-overrides", json={
        "session_id": sid, "path": p, "kind": "date_pattern", "value": "AAAAMMDD"})
    assert r.status_code == 200 and r.json()["new"] == "2008:10:14 00:00:00"
    cands = correction_service.build_candidates(sid, [], root)
    assert cands[0]["recommended_date"] == "2008:10:14 00:00:00"

    # patrón que NO resuelve para este archivo -> 400
    bad = client.post("/api/corrections/file-overrides", json={
        "session_id": sid, "path": p, "kind": "date_pattern", "value": "hhmmss"})
    assert bad.status_code == 400


def test_corrections_run_pagination_and_filter():
    db = get_db()
    sid = db.create_session("/tmp", "local")
    # 3 propuestos + 1 skip
    for i in range(3):
        db.insert_correction({
            "session_id": sid, "run_id": "runX", "path": f"/tmp/f{i}.jpg", "dry_run": 1,
            "correction_type": "set_date", "original_value": "2010:01:01 00:00:00",
            "new_value": "2020:07:02 00:00:00", "status": "dry-run",
        })
    db.insert_correction({
        "session_id": sid, "run_id": "runX", "path": "/tmp/skip.jpg", "dry_run": 1,
        "correction_type": "skip", "status": "skipped",
    })
    # only_changes excluye el skip
    r = client.get("/api/corrections/runX", params={"only_changes": True})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 3
    assert all(c["correction_type"] != "skip" for c in body["corrections"])
    assert body["corrections"][0]["original_value"] == "2010:01:01 00:00:00"
    # sin filtro: incluye el skip (4)
    r2 = client.get("/api/corrections/runX")
    assert r2.json()["total"] == 4
    # paginación
    r3 = client.get("/api/corrections/runX", params={"only_changes": True, "limit": 2, "offset": 0})
    assert r3.json()["count"] == 2

client = TestClient(backend_app.app)


# ---------------- formats ----------------

def test_formats_catalog_groups():
    r = client.get("/api/config/formats")
    assert r.status_code == 200
    cat = r.json()
    assert {"image", "raw", "video"} <= set(cat.keys())
    assert ".jpg" in cat["image"] and ".mp4" in cat["video"] and ".cr3" in cat["raw"]


def test_resolve_extensions_include_exclude():
    got = fmts.resolve_extensions(include=["jpg", ".MP4"], exclude=[".mp4"])
    assert got == {".jpg"}
    # sin include => todas menos las excluidas
    allm = fmts.resolve_extensions(exclude=[".png"])
    assert ".png" not in allm and ".jpg" in allm


# ---------------- browse ----------------

def test_browse_root_lists_allowlist():
    r = client.get("/api/config/browse")
    assert r.status_code == 200
    assert isinstance(r.json()["dirs"], list)


def test_browse_lists_subdirs(tmp_path):
    base = tempfile.mkdtemp(dir=tempfile.gettempdir())
    os.makedirs(os.path.join(base, "2020"))
    os.makedirs(os.path.join(base, "2019"))
    r = client.get("/api/config/browse", params={"path": base})
    assert r.status_code == 200
    names = {d["name"] for d in r.json()["dirs"]}
    assert {"2019", "2020"} <= names


def test_browse_rejects_system_path():
    r = client.get("/api/config/browse", params={"path": "/etc"})
    assert r.status_code == 403


# ---------------- recursividad corrección ----------------

def test_under_folder_recursive_and_boundary():
    assert _under_folder("/media/2020/07/02/x.jpg", "/media/2020") is True
    assert _under_folder("/media/2020/x.jpg", "/media/2020") is True
    # límite: no debe colar carpetas hermanas con prefijo común
    assert _under_folder("/media/2020b/x.jpg", "/media/2020") is False


def test_candidates_recursion(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    rows = [
        ({"path": f"{root}/2020/07/a.jpg", "needs_correction": True}, "2020", "2020/07", None),
        ({"path": f"{root}/2020/08/deep/b.jpg", "needs_correction": True}, "2020", "2020/08", None),
        ({"path": f"{root}/2019/c.jpg", "needs_correction": True}, "2019", "2019", None),
    ]
    db.insert_files_bulk(sid, rows)
    # seleccionar "2020" debe incluir 07 y 08/deep (todos los niveles), no 2019
    got = _candidates(sid, [f"{root}/2020"], root)
    paths = {r["path"] for r in got}
    assert paths == {f"{root}/2020/07/a.jpg", f"{root}/2020/08/deep/b.jpg"}


# ---------------- count en test ----------------

@pytest.mark.skipif(not _REAL, reason="requiere Pillow y exiftool")
def test_local_test_counts_total(tmp_path):
    media = tempfile.mkdtemp(dir=tempfile.gettempdir())
    os.makedirs(os.path.join(media, "sub"))
    for p in ("a.jpg", "sub/b.jpg", "sub/c.mp4"):
        full = os.path.join(media, p)
        Image.new("RGB", (2, 2), (1, 2, 3)).save(full, "JPEG") if p.endswith(".jpg") else open(full, "wb").write(b"x")
    r = client.post("/api/config/test", json={"type": "local", "root_path": media})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["details"]["total_media_files"] == 3
