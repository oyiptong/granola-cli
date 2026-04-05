from granola.db import Database
from tests.helpers import sample_note


def test_schema_creation() -> None:
    db = Database(":memory:")
    db.initialize()
    names = {row[0] for row in db.connection.execute("SELECT name FROM sqlite_master")}
    assert {"notes", "transcript_entries", "sync_state", "notes_fts", "fetch_runs", "request_log", "rate_limit_events"}.issubset(names)


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


def test_fetch_run_round_trip() -> None:
    db = Database(":memory:")
    db.initialize()
    run_id = db.start_fetch_run(overwrite_from=None, dry_run=False)
    db.finish_fetch_run(run_id, status="success", notes_discovered=1, notes_fetched=1, notes_failed=0, watermark="2026-01-01T00:00:00Z")
    row = db.fetch_run(run_id)
    assert row is not None
    assert row["status"] == "success"
    assert row["notes_fetched"] == 1


def test_request_log_round_trip() -> None:
    db = Database(":memory:")
    db.initialize()
    db.record_request_log(method="GET", path="/v1/notes", status="success", status_code=200)
    rows = db.request_log_rows()
    assert len(rows) == 1
    assert rows[0]["path"] == "/v1/notes"


def test_shared_rate_limit_slot_uses_same_db_file(tmp_path) -> None:
    path = str(tmp_path / "granola.sqlite3")
    first = Database(path)
    second = Database(path)
    first.initialize()
    second.initialize()
    assert first.acquire_rate_limit_slot(now=100.0, burst_capacity=25, window_seconds=5.0, min_interval=0.2) == 0.0
    assert second.acquire_rate_limit_slot(now=100.0, burst_capacity=25, window_seconds=5.0, min_interval=0.2) > 0.0
    first.close()
    second.close()
