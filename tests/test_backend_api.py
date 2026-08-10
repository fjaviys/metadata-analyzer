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
