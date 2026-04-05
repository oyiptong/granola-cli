from __future__ import annotations

import json
from pathlib import Path

from granola.util import created_date, slugify_title, transcript_to_text


def build_output_path(
    artifacts_dir: Path,
    created_at: str,
    prefix: str,
    title: str | None,
    note_id: str,
    suffix: str,
) -> Path:
    date_part = created_date(created_at)
    slug = slugify_title(title)
    filename = f"{date_part}_{prefix}_{slug}_{note_id}.{suffix}"
    return artifacts_dir / filename


def summary_text(note: dict) -> str:
    value = note.get("summary_text") or ""
    return f"{value}\n" if value else ""


def transcript_text(note: dict) -> str:
    return transcript_to_text(note.get("transcript"))


def raw_json_text(note: dict) -> str:
    return json.dumps(note, indent=2, ensure_ascii=False) + "\n"


def export_note_files(
    note: dict,
    artifacts_dir: Path,
    *,
    include_json: bool,
    include_summary: bool,
    include_transcript: bool,
) -> list[Path]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    note_id = note["id"]
    created_at = note["created_at"]
    title = note.get("title")
    written: list[Path] = []

    if include_json:
        path = build_output_path(
            artifacts_dir, created_at, "note", title, note_id, "json"
        )
        path.write_text(raw_json_text(note), encoding="utf-8")
        written.append(path)

    if include_summary:
        path = build_output_path(
            artifacts_dir, created_at, "summary", title, note_id, "txt"
        )
        path.write_text(summary_text(note), encoding="utf-8")
        written.append(path)

    if include_transcript:
        path = build_output_path(
            artifacts_dir, created_at, "transcript", title, note_id, "txt"
        )
        path.write_text(transcript_text(note), encoding="utf-8")
        written.append(path)

    return written
