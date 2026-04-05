from granola.db import Database
from granola.search import SearchEngine
from tests.helpers import sample_note


def test_rebuild_and_search_finds_inserted_notes() -> None:
    db = Database(":memory:")
    db.initialize()
    db.upsert_note(sample_note(summary_text="We discussed yoghurt budget"))
    db.rebuild_fts()
    rows = SearchEngine(db.connection).search("yoghurt", scope=None, date_start=None, date_end=None, limit=10)
    assert [row["note_id"] for row in rows] == ["not_1d3tmYTlCICgjy"]


def test_scoped_search_transcript_only() -> None:
    db = Database(":memory:")
    db.initialize()
    db.upsert_note(sample_note(summary_text="No keyword here", transcript=[{"speaker": {"source": "speaker"}, "text": "yoghurt appears here"}]))
    db.rebuild_fts()
    transcript_rows = SearchEngine(db.connection).search("yoghurt", scope="transcript", date_start=None, date_end=None, limit=10)
    summary_rows = SearchEngine(db.connection).search("yoghurt", scope="summary", date_start=None, date_end=None, limit=10)
    assert len(transcript_rows) == 1
    assert summary_rows == []


def test_date_filter_and_snippet_markers() -> None:
    db = Database(":memory:")
    db.initialize()
    db.upsert_note(sample_note(note_id="not_old0000000001", created_at="2026-01-01T12:00:00Z", summary_text="yoghurt old"))
    db.upsert_note(sample_note(note_id="not_new0000000002", created_at="2026-02-01T12:00:00Z", summary_text="yoghurt new"))
    db.rebuild_fts()
    rows = SearchEngine(db.connection).search("yoghurt", scope=None, date_start="2026-02-01", date_end="2026-02-01", limit=10)
    assert [row["note_id"] for row in rows] == ["not_new0000000002"]
    assert "[yoghurt]" in rows[0]["snippet"]


def test_empty_results() -> None:
    db = Database(":memory:")
    db.initialize()
    db.upsert_note(sample_note(title="Budget review", summary_text="budget only"))
    db.rebuild_fts()
    assert SearchEngine(db.connection).search("yoghurt", scope=None, date_start=None, date_end=None, limit=10) == []
