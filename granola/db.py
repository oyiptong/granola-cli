from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from granola.util import normalize_user_datetime, transcript_to_text, utc_now_iso


SCHEMA_VERSION = "1"


class Database:
    def __init__(self, path: str):
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

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
        row = self.connection.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
        return None if row is None else row["value"]

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
            self.connection.execute("DELETE FROM transcript_entries WHERE note_id = ?", (note["id"],))
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
        row = self.connection.execute("SELECT raw_json FROM notes WHERE note_id = ?", (note_id,)).fetchone()
        return None if row is None else json.loads(row["raw_json"])

    def list_notes(self, *, date_start: str | None, date_end: str | None, limit: int) -> list[dict]:
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

    def exportable_notes(self, *, note_ids: list[str], date_start: str | None, date_end: str | None) -> list[dict]:
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
        rows = self.connection.execute(f"SELECT raw_json FROM notes {where} ORDER BY created_at DESC", params).fetchall()
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
