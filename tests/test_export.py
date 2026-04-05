import json

from granola.export import (
    build_output_path,
    export_note_files,
    raw_json_text,
    summary_text,
    transcript_text,
)
from tests.helpers import sample_note


def test_summary_file_content() -> None:
    note = sample_note(summary_text="Known summary")
    assert summary_text(note) == "Known summary\n"


def test_transcript_file_content() -> None:
    note = sample_note(
        transcript=[
            {"speaker": {"source": "microphone"}, "text": "hello"},
            {"speaker": {"source": "speaker"}, "text": "world"},
            {"speaker": None, "text": "fallback"},
        ]
    )
    assert transcript_text(note) == "me: hello\nthem: world\nthem: fallback"


def test_null_transcript_is_empty() -> None:
    note = sample_note(transcript=None)
    note["transcript"] = None
    assert transcript_text(note) == ""


def test_raw_json_round_trip() -> None:
    note = sample_note()
    payload = raw_json_text(note)
    assert json.loads(payload) == note


def test_filename_generation() -> None:
    note = sample_note()
    path = build_output_path(
        tmp_artifacts_dir(),
        note["created_at"],
        "summary",
        note["title"],
        note["id"],
        "txt",
    )
    assert (
        path.name
        == "2026-01-27_summary_quarterly-yoghurt-budget-review_not_1d3tmYTlCICgjy.txt"
    )


def test_export_note_files(tmp_path) -> None:
    note = sample_note()
    written = export_note_files(
        note, tmp_path, include_json=True, include_summary=True, include_transcript=True
    )
    assert len(written) == 3
    assert all(path.exists() for path in written)


def tmp_artifacts_dir():
    from pathlib import Path

    return Path("/tmp/artifacts-test")
