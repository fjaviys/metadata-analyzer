"""
Tests del backend FastAPI.

- Endpoints síncronos vía TestClient: health, config/roots, config/test (rechazo
  de rutas de sistema, aceptación de la allowlist).
- Guarda de confirmación: corrección REAL sin confirmar -> 428.
- Pipeline E2E (con exiftool): análisis de una carpeta de ejemplo -> BD + PDF, y
  luego corrección en DRY-RUN que NO modifica archivos.
"""

import asyncio
import os
import subprocess
import sys
import tempfile
import threading
import time

import pytest

# --- configurar entorno ANTES de importar el backend ---
_TMP = tempfile.mkdtemp(prefix="ma_backend_")
os.environ["ALLOWED_MEDIA_ROOTS"] = tempfile.gettempdir()
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/test.db"
os.environ["LOG_DIR"] = os.path.join(_TMP, "logs")
os.environ["REPORT_DIR"] = os.path.join(_TMP, "reports")
os.environ["BACKUP_DIR"] = os.path.join(_TMP, "backups")

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "backend"))

import metadata_analyzer as ma  # noqa: E402

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

_REAL = _HAS_PIL and ma.exiftool_available()

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

import app as backend_app  # noqa: E402
from database.db import get_db  # noqa: E402
import services.analysis_service as an  # noqa: E402
import services.correction_service as co  # noqa: E402
import services.reorganize_service as ro  # noqa: E402

client = TestClient(backend_app.app)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_config_roots():
    r = client.get("/api/config/roots")
    assert r.status_code == 200
    assert "allowed_media_roots" in r.json()


def test_config_test_rejects_system_path():
    r = client.post("/api/config/test", json={"type": "local", "root_path": "/etc"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_correction_requires_confirmation():
    db = get_db()
    sid = db.create_session(tempfile.gettempdir(), "local")
    db.finish_session(sid, {"total_files": 0})
    r = client.post("/api/corrections", json={
        "session_id": sid, "dry_run": False, "confirm_real_write": False})
    assert r.status_code == 428  # Precondition Required
    assert "confirm" in r.json()["detail"].lower() or "dry-run" in r.json()["detail"].lower()


def test_reorganize_requires_confirmation():
    db = get_db()
    sid = db.create_session(tempfile.gettempdir(), "local")
    db.finish_session(sid, {"total_files": 0})
    r = client.post("/api/reorganize", json={
        "session_id": sid, "dry_run": False, "confirm_real_write": False})
    assert r.status_code == 428
    assert "confirm" in r.json()["detail"].lower() or "dry-run" in r.json()["detail"].lower()


def test_reorganize_layout_presets():
    r = client.get("/api/reorganize/layout-presets")
    assert r.status_code == 200
    assert any(p["layout"] == "AAAA/MM" for p in r.json()["presets"])


def test_folder_decision_upsert_via_reorganize_api():
    db = get_db()
    sid = db.create_session(tempfile.gettempdir(), "local")
    db.finish_session(sid, {"total_files": 0})
    folder = os.path.join(tempfile.gettempdir(), "algunacarpeta")

    r = client.post("/api/reorganize/folder-decision", json={
        "session_id": sid, "folder": folder, "structure_mode": "update"})
    assert r.status_code == 200
    body = r.json()
    assert body["structure_mode"] == "update"
    assert body["structure_layout"] is None

    # actualización parcial: solo toca structure_layout, structure_mode se conserva
    r = client.post("/api/reorganize/folder-decision", json={
        "session_id": sid, "folder": folder, "structure_layout": "AAAA-MM"})
    assert r.status_code == 200
    body = r.json()
    assert body["structure_mode"] == "update"  # conservado
    assert body["structure_layout"] == "AAAA-MM"

    r = client.get(f"/api/reorganize/folder-decisions?session_id={sid}")
    assert r.status_code == 200
    assert len(r.json()["decisions"]) == 1

    r = client.delete(f"/api/reorganize/folder-decision?session_id={sid}&folder={folder}")
    assert r.status_code == 200
    assert client.get(f"/api/reorganize/folder-decisions?session_id={sid}").json()["decisions"] == []


def test_reorganize_gate_blocks_after_real_correction():
    db = get_db()
    sid = db.create_session(tempfile.gettempdir(), "local")
    db.finish_session(sid, {"total_files": 0})

    # sin correcciones: gate abierto
    assert client.get(f"/api/reorganize/gate?session_id={sid}").json()["blocked"] is False

    # una corrección en DRY-RUN no bloquea
    db.insert_correction({"session_id": sid, "run_id": "dry1", "path": "/tmp/a.jpg",
                          "dry_run": 1, "correction_type": "set_date", "status": "dry-run"})
    assert client.get(f"/api/reorganize/gate?session_id={sid}").json()["blocked"] is False

    # una corrección REAL sí bloquea
    db.insert_correction({"session_id": sid, "run_id": "real1", "path": "/tmp/a.jpg",
                          "dry_run": 0, "correction_type": "set_date", "status": "verified"})
    r = client.get(f"/api/reorganize/gate?session_id={sid}")
    assert r.json()["blocked"] is True and r.json()["reason"]

    r = client.post("/api/reorganize", json={"session_id": sid, "dry_run": True})
    assert r.status_code == 409

    # una sesión NUEVA (re-analizada) del mismo root: gate abierto de nuevo
    sid2 = db.create_session(tempfile.gettempdir(), "local")
    db.finish_session(sid2, {"total_files": 0})
    assert client.get(f"/api/reorganize/gate?session_id={sid2}").json()["blocked"] is False


@pytest.mark.skipif(not _REAL, reason="requiere Pillow y exiftool")
def test_e2e_structure_plan_per_folder_and_preview():
    """
    Solo folderA se marca 'actualizar estructura'; folderB se deja en
    'mantener' (default) y ni se evalúa ni se mueve.
    """
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    try:
        media = tempfile.mkdtemp(prefix="ma_media_struct_", dir=tempfile.gettempdir())
        folder_a = os.path.join(media, "folderA")
        folder_b = os.path.join(media, "folderB")
        os.makedirs(folder_a)
        os.makedirs(folder_b)
        file_a = os.path.join(folder_a, "IMG_20200702.jpg")
        file_b = os.path.join(folder_b, "IMG_20180101.jpg")
        _jpeg(file_a, exif_date="2020:07:02 10:00:00")
        _jpeg(file_b, exif_date="2018:01:01 10:00:00")

        db = get_db()
        sid = db.create_session(media, "local")
        an._run_analysis_blocking(sid, media, None, True, None, loop)
        assert db.get_session(sid)["status"] == "completed"

        db.set_folder_decision(sid, folder_a, structure_mode="update")

        # preview: solo folderA aparece con destino real; folderB ni se evalúa
        r = client.post("/api/reorganize/preview", json={
            "session_id": sid, "base_mode": "auto", "layout": "AAAA/MM"})
        assert r.status_code == 200
        moves_by_path = {m["path"]: m for m in r.json()["moves"]}
        assert file_a in moves_by_path
        assert file_b not in moves_by_path
        expected_target_dir = os.path.join(folder_a, "2020", "07")
        assert moves_by_path[file_a]["after_dir"] == expected_target_dir

        # ejecutar de verdad: folderB no se toca
        plans = ro.build_structure_plan(sid, [], media, "auto", None, "AAAA/MM")
        ro._run_reorganize_blocking("structreal01", sid, plans, False, loop)
        assert os.path.isfile(os.path.join(expected_target_dir, "IMG_20200702.jpg"))
        assert not os.path.isfile(file_a)
        assert os.path.isfile(file_b)  # sin tocar
    finally:
        loop.call_soon_threadsafe(loop.stop)
        time.sleep(0.1)


def _jpeg(path, exif_date=None):
    Image.new("RGB", (2, 2), (30, 90, 160)).save(path, "JPEG")
    if exif_date:
        subprocess.run(["exiftool", "-overwrite_original", f"-DateTimeOriginal={exif_date}",
                        str(path)], capture_output=True, check=True)


@pytest.mark.skipif(not _REAL, reason="requiere Pillow y exiftool")
def test_e2e_analysis_then_dryrun():
    # loop en un hilo para publish_threadsafe de los servicios
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    try:
        media = tempfile.mkdtemp(prefix="ma_media_", dir=tempfile.gettempdir())
        os.makedirs(os.path.join(media, "2020", "07"))
        good = os.path.join(media, "2020", "07", "IMG_20200702_100000.jpg")
        wrong = os.path.join(media, "2020", "07", "IMG_20200703.jpg")
        _jpeg(good, exif_date="2020:07:02 10:00:00")   # coherente
        _jpeg(wrong, exif_date="2010:01:01 00:00:00")  # año no coincide con nombre

        db = get_db()
        sid = db.create_session(media, "local")
        an._run_analysis_blocking(sid, media, None, True, None, loop)

        s = db.get_session(sid)
        assert s["status"] == "completed"
        assert s["total_files"] == 2
        assert s["needs_correction"] >= 1
        assert s["report_path"] and os.path.isfile(s["report_path"])

        # dry-run correction: no debe modificar el archivo incoherente
        before = ma.run_exiftool([wrong])[0].get("DateTimeOriginal")
        cands = db.get_files(sid, needs_correction=True, limit=1000)
        co._run_correction_blocking("dryrun01", sid, cands, True, loop)
        after = ma.run_exiftool([wrong])[0].get("DateTimeOriginal")
        assert before == after  # DRY-RUN no escribe

        corrs = db.get_corrections(run_id="dryrun01")
        assert corrs and all(c["dry_run"] == 1 for c in corrs)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        time.sleep(0.1)


@pytest.mark.skipif(not _REAL, reason="requiere Pillow y exiftool")
def test_e2e_reorganize_dryrun_then_real_then_undo():
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    try:
        media = tempfile.mkdtemp(prefix="ma_media_reorg_", dir=tempfile.gettempdir())
        os.makedirs(os.path.join(media, "varios"))
        f = os.path.join(media, "varios", "IMG_20200702.jpg")
        _jpeg(f, exif_date="2020:07:02 10:00:00")

        db = get_db()
        sid = db.create_session(media, "local")
        an._run_analysis_blocking(sid, media, None, True, None, loop)
        s = db.get_session(sid)
        assert s["status"] == "completed"

        rows = db.get_files(sid, limit=1000)
        from reorganize_engine import plan_reorganize
        plans = plan_reorganize(rows, "auto", None, "AAAA/MM", "session")
        expected_target = os.path.join(media, "varios", "2020", "07",
                                       "IMG_20200702.jpg")
        assert plans[0].action == "move"
        assert plans[0].target == expected_target

        # dry-run: no mueve nada
        ro._run_reorganize_blocking("reorgdry01", sid, plans, True, loop)
        assert os.path.isfile(f)

        # real: mueve de verdad
        ro._run_reorganize_blocking("reorgreal01", sid, plans, False, loop)
        assert not os.path.isfile(f)
        assert os.path.isfile(expected_target)
        moves = db.get_reorganize_moves(run_id="reorgreal01")
        assert moves and moves[0]["status"] == "moved"

        # undo: vuelve a la ruta original
        result = ro.undo("reorgreal01")
        assert result["undone"] == 1
        assert os.path.isfile(f)
        assert not os.path.isfile(expected_target)
    finally:
        loop.call_soon_threadsafe(loop.stop)
        time.sleep(0.1)
