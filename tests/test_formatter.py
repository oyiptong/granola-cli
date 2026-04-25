from unittest.mock import patch

from granola.formatter import (
    OutputMode,
    detect_output_mode,
    format_error,
    format_list_rows,
    format_search_rows,
    format_status,
)
from tests.helpers import sample_note


def test_detect_output_mode_human() -> None:
    with patch("sys.stdout.isatty", return_value=True):
        assert detect_output_mode(False, False) is OutputMode.HUMAN


def test_detect_output_mode_json_when_not_tty() -> None:
    with patch("sys.stdout.isatty", return_value=False):
        assert detect_output_mode(False, False) is OutputMode.JSON


def test_list_format_human_and_quiet() -> None:
    note = sample_note()
    row = {
        "note_id": note["id"],
        "title": note["title"],
        "created_at": note["created_at"],
        "updated_at": note["updated_at"],
        "owner_name": note["owner"]["name"],
        "owner_email": note["owner"]["email"],
        "note": note,
    }
    assert note["id"] in format_list_rows([row], mode=OutputMode.HUMAN, detailed=False)
    assert format_list_rows([row], mode=OutputMode.QUIET, detailed=False) == note["id"]


def test_search_json_format() -> None:
    output = format_search_rows(
        [
            {
                "note_id": "not_1",
                "title": "Title",
                "created_at": "2026-01-01T00:00:00Z",
                "snippet": "...[yoghurt]...",
                "rank": -1.2,
            }
        ],
        mode=OutputMode.JSON,
    )
    assert '"note_id": "not_1"' in output


def test_error_json_format() -> None:
    output = format_error(
        OutputMode.JSON,
        error="not_found",
        message="missing",
        retryable=False,
        note_id="n1",
    )
    assert '"error": "not_found"' in output
    assert '"retryable": false' in output


def test_status_json_format() -> None:
    output = format_status(
        {
            "db_path": "/tmp/granola.sqlite3",
            "notes": {
                "count": 1,
                "earliest_created": "2026-01-01",
                "latest_created": "2026-01-01",
                "last_synced_at": "2026-01-02T03:04:05Z",
                "watermark": "2026-01-01T00:00:00Z",
            },
            "fts_index": "current",
        },
        mode=OutputMode.JSON,
    )
    assert '"db_path": "/tmp/granola.sqlite3"' in output


def test_status_human_format() -> None:
    output = format_status(
        {
            "db_path": "/tmp/granola.sqlite3",
            "notes": {
                "count": 2,
                "earliest_created": "2026-01-01",
                "latest_created": "2026-02-01",
                "last_synced_at": "2026-01-02T03:04:05Z",
                "watermark": "2026-01-01T00:00:00Z",
            },
            "fts_index": "current",
        },
        mode=OutputMode.HUMAN,
    )
    assert output == "\n".join(
        [
            "DB: /tmp/granola.sqlite3",
            "Notes: 2 (2026-01-01 → 2026-02-01)",
            "Last synced: 2026-01-02 03:04 UTC",
            "FTS index: current",
        ]
    )
