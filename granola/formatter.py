from __future__ import annotations

import json
import sys
from enum import Enum

from granola.util import parse_iso_datetime, transcript_to_text, word_count


class OutputMode(str, Enum):
    HUMAN = "human"
    JSON = "json"
    QUIET = "quiet"


def detect_output_mode(force_json: bool, quiet: bool) -> OutputMode:
    if force_json:
        return OutputMode.JSON
    if quiet:
        return OutputMode.QUIET
    return OutputMode.HUMAN if sys.stdout.isatty() else OutputMode.JSON


def json_line(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def format_error(
    mode: OutputMode, *, error: str, message: str, retryable: bool, **context: object
) -> str:
    if mode is OutputMode.JSON:
        payload = {
            "error": error,
            "message": message,
            "retryable": retryable,
            **context,
        }
        return json.dumps(payload, ensure_ascii=False)
    return message


def note_to_list_payload(row: dict, *, detailed: bool) -> dict:
    payload = {
        "note_id": row["note_id"],
        "title": row.get("title"),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
    if detailed:
        note = row["note"]
        payload.update(
            {
                "owner_name": row.get("owner_name"),
                "owner_email": row.get("owner_email"),
                "attendee_count": len(note.get("attendees") or []),
                "has_transcript": bool(note.get("transcript")),
                "summary_word_count": word_count(note.get("summary_text")),
                "transcript_word_count": word_count(
                    transcript_to_text(note.get("transcript"))
                ),
            }
        )
    return payload


def format_list_rows(rows: list[dict], *, mode: OutputMode, detailed: bool) -> str:
    if mode is OutputMode.QUIET:
        return "\n".join(row["note_id"] for row in rows)

    if mode is OutputMode.JSON:
        return "\n".join(
            json_line(note_to_list_payload(row, detailed=detailed)) for row in rows
        )

    lines: list[str] = []
    for row in rows:
        base = f"{row['created_at'][:10]}  {(row.get('title') or 'Untitled')[:40]:<40}  {row['note_id']}"
        lines.append(base)
        if detailed:
            note = row["note"]
            attendee_count = len(note.get("attendees") or [])
            has_transcript = "yes" if note.get("transcript") else "no"
            lines.append(
                f"  owner={row.get('owner_name') or '-'} attendees={attendee_count} transcript={has_transcript}"
            )
    return "\n".join(lines)


def format_search_rows(rows: list[dict], *, mode: OutputMode) -> str:
    if mode is OutputMode.QUIET:
        return "\n".join(row["note_id"] for row in rows)

    if mode is OutputMode.JSON:
        return "\n".join(
            json_line(
                {
                    "note_id": row["note_id"],
                    "title": row.get("title"),
                    "created_at": row["created_at"],
                    "snippet": row["snippet"],
                    "rank": row["rank"],
                }
            )
            for row in rows
        )

    blocks: list[str] = []
    for row in rows:
        header = f"{row['created_at'][:10]}  {row.get('title') or 'Untitled'}  {row['note_id']}"
        blocks.append(f"{header}\n  {row['snippet']}")
    return "\n\n".join(blocks)


def format_status(payload: dict, *, mode: OutputMode) -> str:
    if mode is OutputMode.JSON:
        return json.dumps(payload, ensure_ascii=False)

    notes = payload["notes"]
    count = notes["count"]
    if count == 0:
        notes_line = "Notes: 0"
    else:
        notes_line = (
            f"Notes: {count} ({notes['earliest_created']} → {notes['latest_created']})"
        )

    last_synced_at = notes["last_synced_at"]
    if last_synced_at is None:
        last_synced_line = "Last synced: never"
    else:
        dt = parse_iso_datetime(last_synced_at)
        last_synced_line = f"Last synced: {dt.strftime('%Y-%m-%d %H:%M UTC')}"

    return "\n".join(
        [
            f"DB: {payload['db_path']}",
            notes_line,
            last_synced_line,
            f"FTS index: {payload['fts_index']}",
        ]
    )
