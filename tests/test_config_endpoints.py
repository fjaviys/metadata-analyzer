"""
Tests de los endpoints/lógica de configuración y del Paso 1 (Metadatos):
browse, formats, count en test, filtro de extensiones, recursividad, y el
modelo simplificado de decisión por archivo (keep/filename/folder).
"""

import os
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
from services.correction_service import _under_folder  # noqa: E402
import services.correction_service as correction_service  # noqa: E402
from database.db import get_db  # noqa: E402

client = TestClient(backend_app.app)


def _seed_file(db, sid, root, sub, name, **kw):
    os.makedirs(os.path.join(root, sub), exist_ok=True)
    p = os.path.join(root, sub, name)
    open(p, "wb").close()
    row = {"path": p, "media_type": "photo", "needs_correction": kw.get("needs", False),
           "exif_date": kw.get("exif"), "exif_date_tag": "DateTimeOriginal",
           "has_exif_date": kw.get("exif") is not None,
           "filename_date": kw.get("fname"), "path_date": kw.get("pdate"),
           "recommended_date": kw.get("rec"), "recommended_precision": kw.get("prec"),
           "recommended_source": "path", "inconsistencies": []}
    db.insert_file(sid, row, sub.split("/")[0], sub)
    return p


# ---------------- Paso 1 (Metadatos): decisión por archivo ------------------

def test_metadata_candidates_default_keep(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    _seed_file(db, sid, root, "misc", "IMG_20081014.jpg", exif="2000:01:01 00:00:00",
              fname="2008:10:14 00:00:00")
    # sin decisión explícita -> no se toca nada (default seguro)
    assert correction_service.build_metadata_candidates(sid, [], root) == []


def test_metadata_candidates_filename_source(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    p = _seed_file(db, sid, root, "misc", "IMG_20081014.jpg", exif="2000:01:01 00:00:00",
                   fname="2008:10:14 00:00:00")
    r = client.post("/api/corrections/file-overrides",
                    json={"session_id": sid, "path": p, "kind": "filename"})
    assert r.status_code == 200
    cands = correction_service.build_metadata_candidates(sid, [], root)
    assert len(cands) == 1
    assert cands[0]["recommended_date"] == "2008:10:14 00:00:00"
    assert cands[0]["recommended_source"] == "filename"


def test_metadata_candidates_folder_source(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    p = _seed_file(db, sid, root, "2009/02102009", "IMG_x.jpg", exif="2000:01:01 00:00:00",
                   pdate="2009:10:02 00:00:00")
    r = client.post("/api/corrections/file-overrides",
                    json={"session_id": sid, "path": p, "kind": "folder"})
    assert r.status_code == 200
    cands = correction_service.build_metadata_candidates(sid, [], root)
    assert len(cands) == 1
    assert cands[0]["recommended_date"] == "2009:10:02 00:00:00"
    assert cands[0]["recommended_source"] == "folder"


def test_metadata_candidates_keep_excludes(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    p = _seed_file(db, sid, root, "misc", "IMG_20081014.jpg", exif="2000:01:01 00:00:00",
                   fname="2008:10:14 00:00:00")
    db.set_file_override(sid, p, "keep")
    assert correction_service.build_metadata_candidates(sid, [], root) == []


def test_metadata_candidates_never_fabricates(tmp_path):
    """Aunque se fuerce el override en BD (saltándose la validación del endpoint),
    el servicio nunca inventa una fecha si esa fuente no tiene ninguna."""
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    p = _seed_file(db, sid, root, "misc", "photo.jpg", exif="2000:01:01 00:00:00")
    db.set_file_override(sid, p, "filename")
    assert correction_service.build_metadata_candidates(sid, [], root) == []


def test_metadata_candidates_idempotent_when_exif_matches(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    p = _seed_file(db, sid, root, "misc", "IMG_20081014.jpg", exif="2008:10:14 00:00:00",
                   fname="2008:10:14 00:00:00")
    db.set_file_override(sid, p, "filename")
    assert correction_service.build_metadata_candidates(sid, [], root) == []


def test_metadata_candidates_recursion(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    p1 = _seed_file(db, sid, root, "2020/07", "IMG_20200702.jpg", fname="2020:07:02 00:00:00")
    p2 = _seed_file(db, sid, root, "2020/08/deep", "IMG_20200803.jpg", fname="2020:08:03 00:00:00")
    p3 = _seed_file(db, sid, root, "2019", "IMG_20190101.jpg", fname="2019:01:01 00:00:00")
    for p in (p1, p2, p3):
        db.set_file_override(sid, p, "filename")
    got = correction_service.build_metadata_candidates(sid, [f"{root}/2020"], root)
    assert {r["path"] for r in got} == {p1, p2}


def test_file_override_keep_filename_folder_roundtrip(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    p = _seed_file(db, sid, root, "2009/02102009", "IMG_20081014.jpg",
                   exif="2000:01:01 00:00:00", fname="2008:10:14 00:00:00",
                   pdate="2009:10:02 00:00:00")

    r = client.post("/api/corrections/file-overrides",
                    json={"session_id": sid, "path": p, "kind": "filename"})
    assert r.status_code == 200
    assert correction_service.build_metadata_candidates(sid, [], root)[0]["recommended_date"] \
        == "2008:10:14 00:00:00"

    r = client.post("/api/corrections/file-overrides",
                    json={"session_id": sid, "path": p, "kind": "folder"})
    assert r.status_code == 200
    assert correction_service.build_metadata_candidates(sid, [], root)[0]["recommended_date"] \
        == "2009:10:02 00:00:00"

    client.post("/api/corrections/file-overrides",
               json={"session_id": sid, "path": p, "kind": "keep"})
    assert correction_service.build_metadata_candidates(sid, [], root) == []

    client.delete("/api/corrections/file-overrides", params={"session_id": sid, "path": p})
    assert client.get("/api/corrections/file-overrides",
                      params={"session_id": sid}).json()["file_overrides"] == []
    assert correction_service.build_metadata_candidates(sid, [], root) == []  # sin decisión = keep


def test_file_overrides_bulk_applies_and_reports_skipped(tmp_path):
    """Aplicar el patrón a una selección entera: los que no tienen fecha en esa
    fuente se reportan en `skipped`, nunca se les inventa una."""
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    ok1 = _seed_file(db, sid, root, "a", "IMG_20081014.jpg", fname="2008:10:14 00:00:00")
    ok2 = _seed_file(db, sid, root, "a", "IMG_20200702.jpg", fname="2020:07:02 00:00:00")
    sin_fecha = _seed_file(db, sid, root, "a", "escaneo.jpg", exif="2000:01:01 00:00:00")

    r = client.post("/api/corrections/file-overrides/bulk", json={
        "session_id": sid, "paths": [ok1, ok2, sin_fecha, "/tmp/no-existe.jpg"],
        "kind": "filename"})
    assert r.status_code == 200
    body = r.json()
    assert set(body["applied"]) == {ok1, ok2}
    skipped = {s["path"]: s["reason"] for s in body["skipped"]}
    assert "el nombre" in skipped[sin_fecha]
    assert "no encontrado" in skipped["/tmp/no-existe.jpg"]

    # se ha persistido solo para los aplicables
    kinds = {o["path"]: o["kind"] for o in db.get_file_overrides(sid)}
    assert kinds == {ok1: "filename", ok2: "filename"}
    assert {c["path"] for c in correction_service.build_metadata_candidates(sid, [], root)} \
        == {ok1, ok2}


def test_file_overrides_bulk_reapply_replaces_previous_kind(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    p = _seed_file(db, sid, root, "2009/02102009", "IMG_20081014.jpg",
                   fname="2008:10:14 00:00:00", pdate="2009:10:02 00:00:00")

    client.post("/api/corrections/file-overrides/bulk",
                json={"session_id": sid, "paths": [p], "kind": "filename"})
    client.post("/api/corrections/file-overrides/bulk",
                json={"session_id": sid, "paths": [p], "kind": "folder"})

    assert len(db.get_file_overrides(sid)) == 1  # upsert, no duplica
    assert correction_service.build_metadata_candidates(sid, [], root)[0]["recommended_date"] \
        == "2009:10:02 00:00:00"


def test_file_override_rejects_source_without_date(tmp_path):
    db = get_db()
    root = str(tmp_path)
    sid = db.create_session(root, "local")
    p = _seed_file(db, sid, root, "misc", "photo.jpg", exif="2000:01:01 00:00:00")
    r = client.post("/api/corrections/file-overrides",
                    json={"session_id": sid, "path": p, "kind": "filename"})
    assert r.status_code == 400


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


# ---------------- recursividad ----------------

def test_under_folder_recursive_and_boundary():
    assert _under_folder("/media/2020/07/02/x.jpg", "/media/2020") is True
    assert _under_folder("/media/2020/x.jpg", "/media/2020") is True
    # límite: no debe colar carpetas hermanas con prefijo común
    assert _under_folder("/media/2020b/x.jpg", "/media/2020") is False


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
