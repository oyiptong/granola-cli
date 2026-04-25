import pytest

from granola.db import Database
from tests.helpers import sample_note


def test_schema_creation() -> None:
    db = Database(":memory:")
    db.initialize()
    names = {row[0] for row in db.connection.execute("SELECT name FROM sqlite_master")}
    assert {
        "notes",
        "transcript_entries",
        "sync_state",
        "notes_fts",
        "fetch_runs",
        "request_log",
        "rate_limit_events",
    }.issubset(names)


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
    assert [tuple(row) for row in rows] == [
        ("microphone", "I'm done pretending."),
        ("speaker", "Finally."),
    ]


def test_list_notes_date_filter_inclusive() -> None:
    db = Database(":memory:")
    db.initialize()
    db.upsert_note(
        sample_note(note_id="not_old0000000001", created_at="2026-01-01T12:00:00Z")
    )
    db.upsert_note(
        sample_note(note_id="not_new0000000002", created_at="2026-01-27T12:00:00Z")
    )
    rows = db.list_notes(date_start="2026-01-27", date_end="2026-01-27", limit=10)
    assert [row["note_id"] for row in rows] == ["not_new0000000002"]


def test_fetch_run_round_trip() -> None:
    db = Database(":memory:")
    db.initialize()
    run_id = db.start_fetch_run(overwrite_from=None, dry_run=False)
    db.set_fetch_discovered(run_id, 1)
    db.record_fetch_success(
        run_id,
        sample_note(updated_at="2026-01-01T00:00:00Z"),
    )
    db.finish_fetch_run(
        run_id,
        status="success",
        rebuild_fts=True,
        update_watermark=True,
    )
    row = db.fetch_run(run_id)
    assert row is not None
    assert row["status"] == "success"
    assert row["notes_fetched"] == 1
    assert row["watermark"] == "2026-01-01T00:00:00Z"
    assert db.get_sync_state("last_watermark") == "2026-01-01T00:00:00Z"


def test_finish_fetch_run_derives_partial_failure_status() -> None:
    db = Database(":memory:")
    db.initialize()
    run_id = db.start_fetch_run(overwrite_from=None, dry_run=False)
    db.set_fetch_discovered(run_id, 2)
    db.record_fetch_success(
        run_id,
        sample_note(updated_at="2026-01-01T00:00:00Z"),
    )
    db.record_fetch_failure(run_id)

    row = db.finish_fetch_run(run_id, rebuild_fts=True, update_watermark=True)

    assert row["status"] == "partial_failure"
    assert db.get_sync_state("last_watermark") is None


def test_request_log_round_trip() -> None:
    db = Database(":memory:")
    db.initialize()
    db.record_request_log(
        method="GET", path="/v1/notes", status="success", status_code=200
    )
    rows = db.request_log_rows()
    assert len(rows) == 1
    assert rows[0]["path"] == "/v1/notes"


def test_shared_rate_limit_slot_uses_same_db_file(tmp_path) -> None:
    path = str(tmp_path / "granola.sqlite3")
    first = Database(path)
    second = Database(path)
    first.initialize()
    second.initialize()
    assert (
        first.acquire_rate_limit_slot(
            now=100.0, burst_capacity=25, window_seconds=5.0, min_interval=0.2
        )
        == 0.0
    )
    assert (
        second.acquire_rate_limit_slot(
            now=100.0, burst_capacity=25, window_seconds=5.0, min_interval=0.2
        )
        > 0.0
    )
    first.close()
    second.close()


def test_record_fetch_success_updates_note_and_bookkeeping_together() -> None:
    db = Database(":memory:")
    db.initialize()
    run_id = db.start_fetch_run(overwrite_from=None, dry_run=False)
    db.set_fetch_discovered(run_id, 1)

    db.record_fetch_success(
        run_id,
        sample_note(
            note_id="not_txn0000000001",
            updated_at="2026-02-01T00:00:00Z",
        ),
    )

    row = db.fetch_run(run_id)
    assert row is not None
    assert db.get_note("not_txn0000000001") is not None
    assert row["notes_fetched"] == 1
    assert row["watermark"] == "2026-02-01T00:00:00Z"


def test_record_fetch_success_rolls_back_when_run_is_missing() -> None:
    db = Database(":memory:")
    db.initialize()

    with pytest.raises(ValueError, match="Unknown fetch run"):
        db.record_fetch_success(
            "missing-run",
            sample_note(
                note_id="not_missing000001",
                updated_at="2026-02-01T00:00:00Z",
            ),
        )

    assert db.get_note("not_missing000001") is None


def test_fetch_run_mutators_raise_when_run_is_missing() -> None:
    db = Database(":memory:")
    db.initialize()

    with pytest.raises(ValueError, match="Unknown fetch run"):
        db.set_fetch_discovered("missing-run", 1)

    with pytest.raises(ValueError, match="Unknown fetch run"):
        db.record_fetch_failure("missing-run")


def test_status_summary_empty_db() -> None:
    db = Database(":memory:")
    db.initialize()

    summary = db.status_summary()

    assert summary == {
        "db_path": ":memory:",
        "notes": {
            "count": 0,
            "earliest_created": None,
            "latest_created": None,
            "last_synced_at": None,
            "watermark": None,
        },
        "fts_index": "empty",
    }


def test_status_summary_populated_db(tmp_path) -> None:
    db = Database(str(tmp_path / "granola.sqlite3"))
    db.initialize()
    db.upsert_note(
        sample_note(note_id="not_old0000000001", created_at="2026-01-01T12:00:00Z")
    )
    db.upsert_note(
        sample_note(note_id="not_new0000000002", created_at="2026-01-27T12:00:00Z")
    )
    run_id = db.start_fetch_run(overwrite_from=None, dry_run=False)
    db.set_fetch_discovered(run_id, 2)
    db.record_fetch_success(
        run_id,
        sample_note(note_id="not_new0000000002", updated_at="2026-01-28T00:00:00Z"),
    )
    db.finish_fetch_run(run_id, status="success", rebuild_fts=True, update_watermark=True)

    summary = db.status_summary()

    assert summary["notes"]["count"] == 2
    assert summary["notes"]["earliest_created"] == "2026-01-01"
    assert summary["notes"]["latest_created"] == "2026-01-27"
    assert summary["notes"]["last_synced_at"] is not None
    assert summary["notes"]["watermark"] == "2026-01-28T00:00:00Z"
    assert summary["fts_index"] == "current"
    db.close()


def test_status_summary_stale_fts() -> None:
    db = Database(":memory:")
    db.initialize()
    db.upsert_note(sample_note())

    summary = db.status_summary()

    assert summary["fts_index"] == "stale"
