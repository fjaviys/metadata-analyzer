"""
database_manager.py — Persistencia SQLite del Metadata Analyzer.

Tablas:
  - analysis_sessions : una fila por análisis (root, contadores, estado, PDF).
  - analyzed_files    : detalle por archivo analizado.
  - duplicates        : grupos de archivos duplicados (por hash).
  - corrections       : registro de cada corrección (dry-run o real) con valor
                        original y nuevo, verificación y estado.

Índices para rendimiento en las columnas de consulta habituales.
Diseño sin dependencias externas (sqlite3 de stdlib). Seguro para uso concurrente
básico con `check_same_thread=False` + WAL. Cada operación abre/usa una conexión;
`DatabaseManager` puede compartirse pero cada hilo debe llamar a `connect()`.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterable, Optional

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS analysis_sessions (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    root              TEXT NOT NULL,
    connection_type   TEXT DEFAULT 'local',
    status            TEXT NOT NULL DEFAULT 'running',   -- running|completed|failed|aborted
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    total_files       INTEGER DEFAULT 0,
    photos            INTEGER DEFAULT 0,
    videos            INTEGER DEFAULT 0,
    with_exif_date    INTEGER DEFAULT 0,
    without_exif_date INTEGER DEFAULT 0,
    corrupt           INTEGER DEFAULT 0,
    inconsistent      INTEGER DEFAULT 0,
    needs_correction  INTEGER DEFAULT 0,
    duplicates_count  INTEGER DEFAULT 0,
    report_path       TEXT,
    summary_json      TEXT,
    error             TEXT
);

CREATE TABLE IF NOT EXISTS analyzed_files (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id            INTEGER NOT NULL,
    path                  TEXT NOT NULL,
    folder_l1             TEXT,
    folder_l2             TEXT,
    media_type            TEXT,
    size_bytes            INTEGER DEFAULT 0,
    content_hash          TEXT,
    exif_date             TEXT,
    exif_date_tag         TEXT,
    has_exif_date         INTEGER DEFAULT 0,
    is_corrupt            INTEGER DEFAULT 0,
    filename_date         TEXT,
    path_date             TEXT,
    filesystem_mtime      TEXT,
    inconsistencies       TEXT,       -- JSON list
    needs_correction      INTEGER DEFAULT 0,
    recommended_date      TEXT,
    recommended_precision TEXT,
    recommended_source    TEXT,
    read_error            TEXT,
    FOREIGN KEY (session_id) REFERENCES analysis_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS duplicates (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    path         TEXT NOT NULL,
    size_bytes   INTEGER DEFAULT 0,
    is_original  INTEGER DEFAULT 0,   -- 1 = candidato a conservar
    FOREIGN KEY (session_id) REFERENCES analysis_sessions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS corrections (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     INTEGER,
    run_id         TEXT,               -- agrupa una ejecución de corrección
    path           TEXT NOT NULL,
    dry_run        INTEGER DEFAULT 1,
    correction_type TEXT,              -- set_date|cleanup
    tag            TEXT,               -- tag EXIF afectado
    original_value TEXT,
    new_value      TEXT,
    precision      TEXT,
    source         TEXT,
    status         TEXT DEFAULT 'pending',  -- pending|applied|verified|failed|reverted|skipped
    verified       INTEGER DEFAULT 0,
    backup_path    TEXT,
    error          TEXT,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES analysis_sessions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_files_session      ON analyzed_files(session_id);
CREATE INDEX IF NOT EXISTS idx_files_needs        ON analyzed_files(session_id, needs_correction);
CREATE INDEX IF NOT EXISTS idx_files_l1           ON analyzed_files(session_id, folder_l1);
CREATE INDEX IF NOT EXISTS idx_files_l2           ON analyzed_files(session_id, folder_l2);
CREATE INDEX IF NOT EXISTS idx_files_hash         ON analyzed_files(content_hash);
CREATE INDEX IF NOT EXISTS idx_dupes_session_hash ON duplicates(session_id, content_hash);
CREATE INDEX IF NOT EXISTS idx_corr_session       ON corrections(session_id);
CREATE INDEX IF NOT EXISTS idx_corr_run           ON corrections(run_id);
CREATE INDEX IF NOT EXISTS idx_corr_status        ON corrections(status);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)

    # --- conexión por hilo ---
    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.db_path, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys=ON")
            c.execute("PRAGMA journal_mode=WAL")
            self._local.conn = c
        return c

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    @contextmanager
    def _tx(self):
        c = self.conn
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise

    def init_db(self) -> None:
        with self._tx() as c:
            c.executescript(_SCHEMA)
            c.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('version', ?)",
                (str(SCHEMA_VERSION),),
            )

    # ------------------------------------------------------------------ sessions
    def create_session(self, root: str, connection_type: str = "local") -> int:
        with self._tx() as c:
            cur = c.execute(
                "INSERT INTO analysis_sessions(root, connection_type, status, started_at) "
                "VALUES(?,?,?,?)",
                (root, connection_type, "running", _now()),
            )
            return int(cur.lastrowid)

    def finish_session(
        self, session_id: int, summary: dict, status: str = "completed",
        report_path: Optional[str] = None, error: Optional[str] = None,
    ) -> None:
        fields = {
            "status": status,
            "finished_at": _now(),
            "total_files": summary.get("total_files", 0),
            "photos": summary.get("photos", 0),
            "videos": summary.get("videos", 0),
            "with_exif_date": summary.get("with_exif_date", 0),
            "without_exif_date": summary.get("without_exif_date", 0),
            "corrupt": summary.get("corrupt", 0),
            "inconsistent": summary.get("inconsistent", 0),
            "needs_correction": summary.get("needs_correction", 0),
            "report_path": report_path,
            "summary_json": json.dumps(summary, ensure_ascii=False),
            "error": error,
        }
        sets = ", ".join(f"{k}=?" for k in fields)
        with self._tx() as c:
            c.execute(
                f"UPDATE analysis_sessions SET {sets} WHERE id=?",
                (*fields.values(), session_id),
            )

    def get_session(self, session_id: int) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM analysis_sessions WHERE id=?", (session_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_sessions(self, limit: int = 50) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM analysis_sessions ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def update_session_duplicates(self, session_id: int, count: int) -> None:
        with self._tx() as c:
            c.execute(
                "UPDATE analysis_sessions SET duplicates_count=? WHERE id=?",
                (count, session_id),
            )

    # ------------------------------------------------------------------ files
    def insert_file(self, session_id: int, fm: Any, folder_l1: str = "",
                    folder_l2: str = "", content_hash: Optional[str] = None) -> int:
        """Inserta una fila desde un FileMetadata (o dict equivalente)."""
        d = fm.as_dict() if hasattr(fm, "as_dict") else dict(fm)
        with self._tx() as c:
            cur = c.execute(
                """INSERT INTO analyzed_files(
                    session_id, path, folder_l1, folder_l2, media_type, size_bytes,
                    content_hash, exif_date, exif_date_tag, has_exif_date, is_corrupt,
                    filename_date, path_date, filesystem_mtime, inconsistencies,
                    needs_correction, recommended_date, recommended_precision,
                    recommended_source, read_error)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    session_id, d.get("path"), folder_l1, folder_l2,
                    d.get("media_type"), d.get("size_bytes", 0), content_hash,
                    d.get("exif_date"), d.get("exif_date_tag"),
                    1 if d.get("has_exif_date") else 0,
                    1 if d.get("is_corrupt") else 0,
                    d.get("filename_date"), d.get("path_date"),
                    d.get("filesystem_mtime"),
                    json.dumps(d.get("inconsistencies", []), ensure_ascii=False),
                    1 if d.get("needs_correction") else 0,
                    d.get("recommended_date"), d.get("recommended_precision"),
                    d.get("recommended_source"), d.get("error"),
                ),
            )
            return int(cur.lastrowid)

    def insert_files_bulk(self, session_id: int, rows: Iterable[tuple]) -> None:
        """rows: iterable de (fm, l1, l2, hash)."""
        with self._tx() as c:
            for fm, l1, l2, h in rows:
                d = fm.as_dict() if hasattr(fm, "as_dict") else dict(fm)
                c.execute(
                    """INSERT INTO analyzed_files(
                        session_id, path, folder_l1, folder_l2, media_type, size_bytes,
                        content_hash, exif_date, exif_date_tag, has_exif_date, is_corrupt,
                        filename_date, path_date, filesystem_mtime, inconsistencies,
                        needs_correction, recommended_date, recommended_precision,
                        recommended_source, read_error)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        session_id, d.get("path"), l1, l2, d.get("media_type"),
                        d.get("size_bytes", 0), h, d.get("exif_date"),
                        d.get("exif_date_tag"), 1 if d.get("has_exif_date") else 0,
                        1 if d.get("is_corrupt") else 0, d.get("filename_date"),
                        d.get("path_date"), d.get("filesystem_mtime"),
                        json.dumps(d.get("inconsistencies", []), ensure_ascii=False),
                        1 if d.get("needs_correction") else 0, d.get("recommended_date"),
                        d.get("recommended_precision"), d.get("recommended_source"),
                        d.get("error"),
                    ),
                )

    def get_files(self, session_id: int, needs_correction: Optional[bool] = None,
                  folder_prefix: Optional[str] = None, limit: int = 1000,
                  offset: int = 0) -> list[dict]:
        q = "SELECT * FROM analyzed_files WHERE session_id=?"
        args: list[Any] = [session_id]
        if needs_correction is not None:
            q += " AND needs_correction=?"
            args.append(1 if needs_correction else 0)
        if folder_prefix:
            q += " AND (folder_l1=? OR folder_l2 LIKE ?)"
            args.extend([folder_prefix, folder_prefix + "%"])
        q += " ORDER BY path LIMIT ? OFFSET ?"
        args.extend([limit, offset])
        rows = self.conn.execute(q, args).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["inconsistencies"] = json.loads(d.get("inconsistencies") or "[]")
            out.append(d)
        return out

    def count_files(self, session_id: int, needs_correction: Optional[bool] = None) -> int:
        q = "SELECT COUNT(*) AS n FROM analyzed_files WHERE session_id=?"
        args: list[Any] = [session_id]
        if needs_correction is not None:
            q += " AND needs_correction=?"
            args.append(1 if needs_correction else 0)
        return int(self.conn.execute(q, args).fetchone()["n"])

    def folder_tree(self, session_id: int) -> list[dict]:
        """Árbol de carpetas (nivel 1 → nivel 2) con contadores para el selector."""
        rows = self.conn.execute(
            """SELECT folder_l1, folder_l2,
                      COUNT(*) AS total,
                      SUM(needs_correction) AS needs
               FROM analyzed_files WHERE session_id=?
               GROUP BY folder_l1, folder_l2
               ORDER BY total DESC""",
            (session_id,),
        ).fetchall()
        tree: dict[str, dict] = {}
        for r in rows:
            l1 = r["folder_l1"] or "(raíz)"
            node = tree.setdefault(l1, {"folder": l1, "total": 0, "needs": 0, "children": []})
            node["total"] += r["total"]
            node["needs"] += r["needs"] or 0
            if r["folder_l2"] and r["folder_l2"] != l1:
                node["children"].append({
                    "folder": r["folder_l2"], "total": r["total"],
                    "needs": r["needs"] or 0,
                })
        return sorted(tree.values(), key=lambda n: n["total"], reverse=True)

    # ------------------------------------------------------------------ duplicates
    def insert_duplicate_group(self, session_id: int, content_hash: str,
                               paths: list[tuple[str, int]], keep_index: int = 0) -> None:
        with self._tx() as c:
            for i, (path, size) in enumerate(paths):
                c.execute(
                    "INSERT INTO duplicates(session_id, content_hash, path, size_bytes, is_original) "
                    "VALUES(?,?,?,?,?)",
                    (session_id, content_hash, path, size, 1 if i == keep_index else 0),
                )

    def get_duplicates(self, session_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM duplicates WHERE session_id=? ORDER BY content_hash, is_original DESC",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ corrections
    def insert_correction(self, record: dict) -> int:
        record = {**record}
        record.setdefault("created_at", _now())
        record.setdefault("dry_run", 1)
        record.setdefault("status", "pending")
        cols = ["session_id", "run_id", "path", "dry_run", "correction_type", "tag",
                "original_value", "new_value", "precision", "source", "status",
                "verified", "backup_path", "error", "created_at"]
        with self._tx() as c:
            cur = c.execute(
                f"INSERT INTO corrections({','.join(cols)}) VALUES({','.join('?'*len(cols))})",
                tuple(record.get(k) for k in cols),
            )
            return int(cur.lastrowid)

    def update_correction(self, correction_id: int, **fields) -> None:
        if not fields:
            return
        sets = ", ".join(f"{k}=?" for k in fields)
        with self._tx() as c:
            c.execute(
                f"UPDATE corrections SET {sets} WHERE id=?",
                (*fields.values(), correction_id),
            )

    def get_corrections(self, session_id: Optional[int] = None,
                        run_id: Optional[str] = None) -> list[dict]:
        q = "SELECT * FROM corrections WHERE 1=1"
        args: list[Any] = []
        if session_id is not None:
            q += " AND session_id=?"
            args.append(session_id)
        if run_id is not None:
            q += " AND run_id=?"
            args.append(run_id)
        q += " ORDER BY id"
        return [dict(r) for r in self.conn.execute(q, args).fetchall()]

    def correction_stats(self, run_id: str) -> dict:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM corrections WHERE run_id=? GROUP BY status",
            (run_id,),
        ).fetchall()
        return {r["status"]: r["n"] for r in rows}


__all__ = ["DatabaseManager", "SCHEMA_VERSION"]
