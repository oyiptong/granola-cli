from __future__ import annotations

import sqlite3

from granola.util import normalize_user_datetime


class SearchEngine:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def search(
        self,
        query: str,
        *,
        scope: str | None,
        date_start: str | None,
        date_end: str | None,
        limit: int,
    ) -> list[dict]:
        match_query = query if scope is None else f"{self._scope_column(scope)} : {query}"
        snippet_column = {None: -1, "summary": 2, "transcript": 3}[scope]

        conditions = ["notes_fts MATCH ?"]
        params: list[object] = [match_query]
        if date_start:
            conditions.append("n.created_at >= ?")
            params.append(normalize_user_datetime(date_start, is_end=False))
        if date_end:
            conditions.append("n.created_at <= ?")
            params.append(normalize_user_datetime(date_end, is_end=True))
        params.append(limit)

        rows = self.connection.execute(
            f"""
            SELECT
                n.note_id,
                n.title,
                n.created_at,
                snippet(notes_fts, ?, '[', ']', '...', 32) AS snippet,
                bm25(notes_fts) AS rank
            FROM notes_fts
            JOIN notes n ON n.note_id = notes_fts.note_id
            WHERE {' AND '.join(conditions)}
            ORDER BY rank
            LIMIT ?
            """,
            [snippet_column, *params],
        ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _scope_column(scope: str) -> str:
        if scope == "summary":
            return "summary_text"
        if scope == "transcript":
            return "transcript_text"
        raise ValueError(f"Unsupported scope: {scope}")
