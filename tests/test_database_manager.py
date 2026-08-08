"""Tests de database_manager: sesiones, ficheros, duplicados, correcciones, árbol."""

from database_manager import DatabaseManager


def _fm(path, l1="2020", l2="2020/07", needs=True, corrupt=False):
    return {
        "path": path, "media_type": "photo", "size_bytes": 1234,
        "exif_date": "2020:07:02 10:00:00", "exif_date_tag": "DateTimeOriginal",
        "has_exif_date": True, "is_corrupt": corrupt,
        "filename_date": "2020:07:02 00:00:00", "path_date": "2020:07:01 00:00:00",
        "filesystem_mtime": "2024:01:01 00:00:00",
        "inconsistencies": ["año EXIF != nombre"] if needs else [],
        "needs_correction": needs, "recommended_date": "2020:07:02 00:00:00",
        "recommended_precision": "FULL_DATE", "recommended_source": "filename",
        "error": None,
    }


def _db(tmp_path):
    db = DatabaseManager(str(tmp_path / "test.db"))
    db.init_db()
    return db


def test_session_lifecycle(tmp_path):
    db = _db(tmp_path)
    sid = db.create_session("/srv/media", "local")
    assert sid > 0
    s = db.get_session(sid)
    assert s["status"] == "running"
    db.finish_session(sid, {"total_files": 3, "needs_correction": 2}, report_path="/x.pdf")
    s = db.get_session(sid)
    assert s["status"] == "completed"
    assert s["total_files"] == 3
    assert s["report_path"] == "/x.pdf"
    assert db.list_sessions()[0]["id"] == sid


def test_insert_and_query_files(tmp_path):
    db = _db(tmp_path)
    sid = db.create_session("/srv/media")
    db.insert_file(sid, _fm("/srv/media/2020/07/a.jpg"), "2020", "2020/07")
    db.insert_file(sid, _fm("/srv/media/2020/07/b.jpg", needs=False), "2020", "2020/07")
    assert db.count_files(sid) == 2
    assert db.count_files(sid, needs_correction=True) == 1
    rows = db.get_files(sid, needs_correction=True)
    assert len(rows) == 1
    assert rows[0]["inconsistencies"] == ["año EXIF != nombre"]


def test_bulk_and_folder_tree(tmp_path):
    db = _db(tmp_path)
    sid = db.create_session("/srv/media")
    rows = [
        (_fm("/srv/media/2020/07/a.jpg"), "2020", "2020/07", "h1"),
        (_fm("/srv/media/2020/07/b.jpg"), "2020", "2020/07", "h2"),
        (_fm("/srv/media/2019/c.jpg"), "2019", "2019", "h3"),
    ]
    db.insert_files_bulk(sid, rows)
    tree = db.folder_tree(sid)
    # nivel 1 ordenado desc por total: 2020 (2) antes que 2019 (1)
    assert tree[0]["folder"] == "2020"
    assert tree[0]["total"] == 2
    assert any(ch["folder"] == "2020/07" for ch in tree[0]["children"])


def test_duplicates(tmp_path):
    db = _db(tmp_path)
    sid = db.create_session("/srv/media")
    db.insert_duplicate_group(sid, "hashX", [("/a.jpg", 100), ("/b.jpg", 100)], keep_index=0)
    dupes = db.get_duplicates(sid)
    assert len(dupes) == 2
    originals = [d for d in dupes if d["is_original"]]
    assert len(originals) == 1
    assert originals[0]["path"] == "/a.jpg"


def test_corrections_flow(tmp_path):
    db = _db(tmp_path)
    sid = db.create_session("/srv/media")
    cid = db.insert_correction({
        "session_id": sid, "run_id": "run-1", "path": "/a.jpg", "dry_run": 0,
        "correction_type": "set_date", "tag": "DateTimeOriginal",
        "original_value": "2015:01:01 00:00:00", "new_value": "2020:07:02 00:00:00",
        "precision": "FULL_DATE", "source": "filename", "status": "applied",
    })
    assert cid > 0
    db.update_correction(cid, status="verified", verified=1)
    corrs = db.get_corrections(run_id="run-1")
    assert corrs[0]["status"] == "verified"
    assert corrs[0]["verified"] == 1
    stats = db.correction_stats("run-1")
    assert stats.get("verified") == 1
