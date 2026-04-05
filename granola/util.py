from __future__ import annotations

import re
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def parse_iso_datetime(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_user_datetime(value: str, *, is_end: bool) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Datetime value cannot be empty")

    if "T" not in text and " " not in text:
        datetime.strptime(text, "%Y-%m-%d")
        suffix = "23:59:59Z" if is_end else "00:00:00Z"
        return f"{text}T{suffix}"

    return (
        parse_iso_datetime(text)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def slugify_title(title: str | None) -> str:
    if title is None:
        return "untitled"

    slug = title.lower().strip()
    slug = re.sub(r"[\\/:*?\"<>|]", " ", slug)
    slug = re.sub(r"[^\w\s-]", " ", slug, flags=re.UNICODE)
    slug = re.sub(r"[\s_-]+", "-", slug, flags=re.UNICODE)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "untitled"


def created_date(value: str) -> str:
    return parse_iso_datetime(value).strftime("%Y-%m-%d")


def transcript_label(source: str | None) -> str:
    return "me" if source == "microphone" else "them"


def transcript_to_text(transcript: list[dict] | None) -> str:
    if not transcript:
        return ""

    lines: list[str] = []
    for entry in transcript:
        speaker = entry.get("speaker") or {}
        label = transcript_label(speaker.get("source"))
        lines.append(f"{label}: {entry.get('text', '')}")
    return "\n".join(lines)


def word_count(text: str | None) -> int:
    if not text:
        return 0
    return len(text.split())
