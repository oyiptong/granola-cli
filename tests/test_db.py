from granola.db import Database
from tests.helpers import sample_note


def test_schema_creation() -> None:
    db = Database(":memory:")
    db.initialize()
    names = {row[0] for row in db.connection.execute("SELECT name FROM sqlite_master")}
    assert {"notes", "transcript_entries", "sync_state", "notes_fts"}.issubset(names)


def test_upsert_overwrites_changed_data() -> None:
    db = Database(":memory:")
    db.initialize()
    note = sample_note()
    db.upsert_note(note)
    updated = sample_note(summary_text="Updated summary")
    db.upsert_note(updated)
    stored = db.get_note(note["id"])
    assert stored is not None
    assert stored["summary_text"] == "Updated summary"


def test_watermark_round_trip() -> None:
    db = Database(":memory:")
    db.initialize()
    db.set_sync_state("last_watermark", "2026-01-01T00:00:00Z")
    assert db.get_sync_state("last_watermark") == "2026-01-01T00:00:00Z"


def test_transcript_entries_storage() -> None:
    db = Database(":memory:")
    db.initialize()
    note = sample_note()
    db.upsert_note(note)
    rows = db.connection.execute(
        "SELECT speaker_source, text FROM transcript_entries WHERE note_id = ? ORDER BY entry_index",
        (note["id"],),
    ).fetchall()
    assert [tuple(row) for row in rows] == [("microphone", "I'm done pretending."), ("speaker", "Finally.")]


def test_list_notes_date_filter_inclusive() -> None:
    db = Database(":memory:")
    db.initialize()
    db.upsert_note(sample_note(note_id="not_old0000000001", created_at="2026-01-01T12:00:00Z"))
    db.upsert_note(sample_note(note_id="not_new0000000002", created_at="2026-01-27T12:00:00Z"))
    rows = db.list_notes(date_start="2026-01-27", date_end="2026-01-27", limit=10)
    assert [row["note_id"] for row in rows] == ["not_new0000000002"]
