from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from granola.util import normalize_user_datetime, transcript_to_text, utc_now_iso

SCHEMA_VERSION = "2"


class Database:
    def __init__(self, path: str):
        if path != ":memory:":
            expanded = Path(path).expanduser()
            expanded.parent.mkdir(parents=True, exist_ok=True)
            self.path = str(expanded)
        else:
            self.path = path
        self.connection = sqlite3.connect(self.path, timeout=30)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 30000")
        if self.path != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        self.connection.close()

    def initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS notes (
                    note_id TEXT PRIMARY KEY,
                    object_type TEXT NOT NULL,
                    title TEXT NULL,
                    owner_name TEXT NULL,
                    owner_email TEXT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    summary_text TEXT NULL,
                    summary_markdown TEXT NULL,
                    raw_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transcript_entries (
                    note_id TEXT NOT NULL,
                    entry_index INTEGER NOT NULL,
                    speaker_source TEXT NULL,
                    text TEXT NOT NULL,
                    start_time TEXT NULL,
                    end_time TEXT NULL,
                    PRIMARY KEY (note_id, entry_index)
                );

                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fetch_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NULL,
                    status TEXT NOT NULL,
                    overwrite_from TEXT NULL,
                    dry_run INTEGER NOT NULL,
                    notes_discovered INTEGER NOT NULL DEFAULT 0,
                    notes_fetched INTEGER NOT NULL DEFAULT 0,
                    notes_failed INTEGER NOT NULL DEFAULT 0,
                    watermark TEXT NULL,
                    error TEXT NULL
                );

                CREATE TABLE IF NOT EXISTS request_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    method TEXT NOT NULL,
                    path TEXT NOT NULL,
                    status TEXT NOT NULL,
                    status_code INTEGER NULL,
                    error TEXT NULL,
                    retry_after_seconds REAL NULL
                );

                CREATE TABLE IF NOT EXISTS rate_limit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requested_at REAL NOT NULL
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                    note_id UNINDEXED,
                    title,
                    summary_text,
                    transcript_text,
                    tokenize='unicode61'
                );
                """
            )
            self.set_sync_state("schema_version", SCHEMA_VERSION)

    def set_sync_state(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO sync_state(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_sync_state(self, key: str) -> str | None:
        row = self.connection.execute(
            "SELECT value FROM sync_state WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None else row["value"]

    def start_fetch_run(self, *, overwrite_from: str | None, dry_run: bool) -> str:
        run_id = str(uuid.uuid4())
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO fetch_runs(run_id, started_at, status, overwrite_from, dry_run)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, utc_now_iso(), "running", overwrite_from, 1 if dry_run else 0),
            )
        return run_id

    def finish_fetch_run(
        self,
        run_id: str,
        *,
        status: str,
        notes_discovered: int,
        notes_fetched: int,
        notes_failed: int,
        watermark: str | None,
        error: str | None = None,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                UPDATE fetch_runs
                SET finished_at = ?, status = ?, notes_discovered = ?, notes_fetched = ?,
                    notes_failed = ?, watermark = ?, error = ?
                WHERE run_id = ?
                """,
                (
                    utc_now_iso(),
                    status,
                    notes_discovered,
                    notes_fetched,
                    notes_failed,
                    watermark,
                    error,
                    run_id,
                ),
            )

    def record_request_log(
        self,
        *,
        method: str,
        path: str,
        status: str,
        status_code: int | None = None,
        error: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO request_log(created_at, method, path, status, status_code, error, retry_after_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now_iso(),
                    method,
                    path,
                    status,
                    status_code,
                    error,
                    retry_after_seconds,
                ),
            )

    def acquire_rate_limit_slot(
        self,
        *,
        now: float,
        burst_capacity: int,
        window_seconds: float,
        min_interval: float,
    ) -> float:
        cursor = self.connection.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cutoff = now - window_seconds
            cursor.execute(
                "DELETE FROM rate_limit_events WHERE requested_at <= ?", (cutoff,)
            )
            rows = cursor.execute(
                "SELECT requested_at FROM rate_limit_events ORDER BY requested_at ASC"
            ).fetchall()
            timestamps = [row[0] for row in rows]
            delays = [0.0]
            if timestamps:
                delays.append(max(0.0, min_interval - (now - timestamps[-1])))
            if len(timestamps) >= burst_capacity:
                delays.append(max(0.0, window_seconds - (now - timestamps[0])))
            delay = max(delays)
            if delay == 0.0:
                cursor.execute(
                    "INSERT INTO rate_limit_events(requested_at) VALUES (?)", (now,)
                )
                self.connection.commit()
                return 0.0
            self.connection.rollback()
            return delay
        except Exception:
            self.connection.rollback()
            raise
        finally:
            cursor.close()

    def request_log_rows(self) -> list[sqlite3.Row]:
        return self.connection.execute(
            "SELECT * FROM request_log ORDER BY id ASC"
        ).fetchall()

    def fetch_run(self, run_id: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM fetch_runs WHERE run_id = ?", (run_id,)
        ).fetchone()

    def upsert_note(self, note: dict) -> None:
        owner = note.get("owner") or {}
        transcript = note.get("transcript") or []
        raw_json = json.dumps(note, ensure_ascii=False, sort_keys=True)
        fetched_at = utc_now_iso()

        with self.connection:
            self.connection.execute(
                """
                INSERT INTO notes(
                    note_id, object_type, title, owner_name, owner_email, created_at, updated_at,
                    summary_text, summary_markdown, raw_json, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(note_id) DO UPDATE SET
                    object_type = excluded.object_type,
                    title = excluded.title,
                    owner_name = excluded.owner_name,
                    owner_email = excluded.owner_email,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    summary_text = excluded.summary_text,
                    summary_markdown = excluded.summary_markdown,
                    raw_json = excluded.raw_json,
                    fetched_at = excluded.fetched_at
                """,
                (
                    note["id"],
                    note["object"],
                    note.get("title"),
                    owner.get("name"),
                    owner.get("email"),
                    note["created_at"],
                    note["updated_at"],
                    note.get("summary_text"),
                    note.get("summary_markdown"),
                    raw_json,
                    fetched_at,
                ),
            )
            self.connection.execute(
                "DELETE FROM transcript_entries WHERE note_id = ?", (note["id"],)
            )
            self.connection.executemany(
                """
                INSERT INTO transcript_entries(note_id, entry_index, speaker_source, text, start_time, end_time)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        note["id"],
                        index,
                        (entry.get("speaker") or {}).get("source"),
                        entry.get("text", ""),
                        entry.get("start_time"),
                        entry.get("end_time"),
                    )
                    for index, entry in enumerate(transcript)
                ],
            )

    def rebuild_fts(self) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM notes_fts")
            self.connection.execute(
                """
                INSERT INTO notes_fts (note_id, title, summary_text, transcript_text)
                SELECT
                    n.note_id,
                    COALESCE(n.title, ''),
                    COALESCE(n.summary_text, ''),
                    COALESCE(
                        (
                            SELECT GROUP_CONCAT(te.text, char(10))
                            FROM transcript_entries te
                            WHERE te.note_id = n.note_id
                            ORDER BY te.entry_index
                        ),
                        ''
                    )
                FROM notes n
                """
            )

    def get_note(self, note_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT raw_json FROM notes WHERE note_id = ?", (note_id,)
        ).fetchone()
        return None if row is None else json.loads(row["raw_json"])

    def list_notes(
        self, *, date_start: str | None, date_end: str | None, limit: int
    ) -> list[dict]:
        conditions: list[str] = []
        params: list[object] = []
        if date_start:
            conditions.append("created_at >= ?")
            params.append(normalize_user_datetime(date_start, is_end=False))
        if date_end:
            conditions.append("created_at <= ?")
            params.append(normalize_user_datetime(date_end, is_end=True))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"SELECT * FROM notes {where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(query, params).fetchall()
        return [self._note_row_payload(row) for row in rows]

    def exportable_notes(
        self, *, note_ids: list[str], date_start: str | None, date_end: str | None
    ) -> list[dict]:
        conditions: list[str] = []
        params: list[object] = []
        if note_ids:
            placeholders = ", ".join("?" for _ in note_ids)
            conditions.append(f"note_id IN ({placeholders})")
            params.extend(note_ids)
        if date_start:
            conditions.append("created_at >= ?")
            params.append(normalize_user_datetime(date_start, is_end=False))
        if date_end:
            conditions.append("created_at <= ?")
            params.append(normalize_user_datetime(date_end, is_end=True))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self.connection.execute(
            f"SELECT raw_json FROM notes {where} ORDER BY created_at DESC", params
        ).fetchall()
        return [json.loads(row["raw_json"]) for row in rows]

    def _note_row_payload(self, row: sqlite3.Row) -> dict:
        note = json.loads(row["raw_json"])
        return {
            "note_id": row["note_id"],
            "title": row["title"],
            "owner_name": row["owner_name"],
            "owner_email": row["owner_email"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "summary_text": row["summary_text"],
            "note": note,
            "transcript_text": transcript_to_text(note.get("transcript")),
        }
