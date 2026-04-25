from unittest.mock import patch

import pytest

from granola.client import ApiError
from granola.config import AppConfig
from granola.db import Database
from granola_cli import (
    build_parser,
    fetch_updated_after,
    main,
    open_database,
    parse_args,
)
from tests.helpers import sample_note


def test_json_and_quiet_are_mutually_exclusive() -> None:
    parser = build_parser(
        AppConfig(
            api_base_url="https://public-api.granola.ai", db_path="./granola.sqlite3"
        )
    )
    with pytest.raises(SystemExit):
        parser.parse_args(["--json", "--quiet", "list"])


def test_list_defaults_and_overrides() -> None:
    parser = build_parser(
        AppConfig(
            api_base_url="https://public-api.granola.ai", db_path="./granola.sqlite3"
        )
    )
    args = parser.parse_args(["list", "--limit", "5", "--date-start", "2026-01-01"])
    assert args.command == "list"
    assert args.limit == 5
    assert args.date_start == "2026-01-01"


def test_global_flags_work_before_and_after_subcommand() -> None:
    parser = build_parser(
        AppConfig(
            api_base_url="https://public-api.granola.ai", db_path="./granola.sqlite3"
        )
    )
    before = parser.parse_args(["--db-path", "/tmp/before.sqlite3", "list", "--json"])
    after = parser.parse_args(["list", "--db-path", "/tmp/after.sqlite3", "--json"])
    assert before.db_path == "/tmp/before.sqlite3"
    assert after.db_path == "/tmp/after.sqlite3"
    assert before.json is True
    assert after.json is True


def test_overwrite_from_all_is_distinct(tmp_path) -> None:
    db = open_database(str(tmp_path / "granola.sqlite3"))
    db.set_sync_state("last_watermark", "2026-02-01T00:00:00Z")
    assert fetch_updated_after(db, "all") is None


def test_search_scope_parsing() -> None:
    parser = build_parser(
        AppConfig(
            api_base_url="https://public-api.granola.ai", db_path="./granola.sqlite3"
        )
    )
    args = parser.parse_args(["search", "yoghurt", "--in", "transcript"])
    assert args.scope == "transcript"


def test_get_requires_note_id() -> None:
    parser = build_parser(
        AppConfig(
            api_base_url="https://public-api.granola.ai", db_path="./granola.sqlite3"
        )
    )
    with pytest.raises(SystemExit):
        parser.parse_args(["get"])


def test_output_note_id_repeatable() -> None:
    parser = build_parser(
        AppConfig(
            api_base_url="https://public-api.granola.ai", db_path="./granola.sqlite3"
        )
    )
    args = parser.parse_args(["output", "--note-id", "n1", "--note-id", "n2"])
    assert args.note_id == ["n1", "n2"]


def test_status_command_parsing() -> None:
    parser = build_parser(
        AppConfig(
            api_base_url="https://public-api.granola.ai", db_path="./granola.sqlite3"
        )
    )
    args = parser.parse_args(["status"])
    assert args.command == "status"


def test_parse_args_uses_config_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    config_dir = tmp_path / ".config" / "granola"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        'api_base_url = "http://localhost:9999"\ndb_path = "/tmp/from-config.sqlite3"\n',
        encoding="utf-8",
    )
    args = parse_args(["list"])
    assert args.db_path == "/tmp/from-config.sqlite3"


def test_get_summary_overrides_non_tty_json_default(tmp_path, capsys) -> None:
    db = open_database(str(tmp_path / "granola.sqlite3"))
    db.upsert_note(sample_note())
    db.close()
    with patch("sys.stdout.isatty", return_value=False):
        result = main(
            [
                "get",
                "--db-path",
                str(tmp_path / "granola.sqlite3"),
                "not_1d3tmYTlCICgjy",
                "--summary",
            ]
        )
    captured = capsys.readouterr()
    assert result == 0
    assert captured.out == "The quarterly yoghurt budget review was a success.\n"


def test_get_defaults_to_json_when_not_tty(tmp_path, capsys) -> None:
    db = open_database(str(tmp_path / "granola.sqlite3"))
    db.upsert_note(sample_note())
    db.close()
    with patch("sys.stdout.isatty", return_value=False):
        result = main(
            [
                "get",
                "--db-path",
                str(tmp_path / "granola.sqlite3"),
                "not_1d3tmYTlCICgjy",
            ]
        )
    captured = capsys.readouterr()
    assert result == 0
    assert '"id": "not_1d3tmYTlCICgjy"' in captured.out


def test_get_json_overrides_other_content_flags(tmp_path, capsys) -> None:
    db = open_database(str(tmp_path / "granola.sqlite3"))
    db.upsert_note(sample_note())
    db.close()
    with patch("sys.stdout.isatty", return_value=True):
        result = main(
            [
                "get",
                "--db-path",
                str(tmp_path / "granola.sqlite3"),
                "not_1d3tmYTlCICgjy",
                "--json",
                "--transcript",
            ]
        )
    captured = capsys.readouterr()
    assert result == 0
    assert '"id": "not_1d3tmYTlCICgjy"' in captured.out


def test_missing_api_key_returns_auth_failure(tmp_path, capsys) -> None:
    with patch("sys.stdout.isatty", return_value=False):
        result = main(
            [
                "fetch",
                "--db-path",
                str(tmp_path / "granola.sqlite3"),
                "--api-key-file",
                str(tmp_path / "missing-key.txt"),
                "--api-base-url",
                "http://127.0.0.1:8765",
            ]
        )
    captured = capsys.readouterr()
    assert result == 4
    assert '"error": "auth_failed"' in captured.err


def test_invalid_date_returns_usage_error(tmp_path, capsys) -> None:
    with patch("sys.stdout.isatty", return_value=False):
        result = main(
            [
                "list",
                "--db-path",
                str(tmp_path / "granola.sqlite3"),
                "--date-start",
                "not-a-date",
            ]
        )
    captured = capsys.readouterr()
    assert result == 2
    assert '"error": "usage_error"' in captured.err


def test_partial_fetch_does_not_advance_watermark(tmp_path, monkeypatch) -> None:
    key_path = tmp_path / "api_key.txt"
    key_path.write_text("test-key\n", encoding="utf-8")
    db_path = tmp_path / "granola.sqlite3"

    class FakeClient:
        def __init__(self, api_key: str, *, api_base_url: str, rate_limiter=None):
            self.api_key = api_key
            self.api_base_url = api_base_url
            self.rate_limiter = rate_limiter

        def iter_note_summaries(
            self, *, updated_after: str | None, page_size: int
        ) -> list[dict]:
            return [
                {
                    "id": "not_ok00000000001",
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-02T00:00:00Z",
                },
                {
                    "id": "not_bad0000000002",
                    "created_at": "2026-01-03T00:00:00Z",
                    "updated_at": "2026-01-04T00:00:00Z",
                },
            ]

        def get_note(self, note_id: str) -> dict:
            if note_id == "not_bad0000000002":
                raise ApiError("fetch_failed", "boom", False, 1, {})
            return sample_note(
                note_id="not_ok00000000001",
                created_at="2026-01-01T00:00:00Z",
                updated_at="2026-01-02T00:00:00Z",
            )

    monkeypatch.setattr("granola_cli.GranolaClient", FakeClient)
    result = main(
        [
            "fetch",
            "--db-path",
            str(db_path),
            "--api-key-file",
            str(key_path),
            "--api-base-url",
            "http://127.0.0.1:8765",
        ]
    )
    assert result == 6
    db = open_database(str(db_path))
    assert db.get_note("not_ok00000000001") is not None
    assert db.get_sync_state("last_watermark") is None
    db.close()


def test_fetch_preserves_original_exception_when_finalization_fails(
    tmp_path, monkeypatch
) -> None:
    key_path = tmp_path / "api_key.txt"
    key_path.write_text("test-key\n", encoding="utf-8")
    db_path = tmp_path / "granola.sqlite3"

    class FakeClient:
        def __init__(self, api_key: str, *, api_base_url: str, rate_limiter=None):
            self.api_key = api_key
            self.api_base_url = api_base_url
            self.rate_limiter = rate_limiter

        def iter_note_summaries(
            self, *, updated_after: str | None, page_size: int
        ) -> list[dict]:
            raise RuntimeError("boom")

    original_finish = Database.finish_fetch_run

    def failing_finish(self, run_id: str, **kwargs):
        if kwargs.get("status") == "failed":
            raise RuntimeError("finalization failed")
        return original_finish(self, run_id, **kwargs)

    monkeypatch.setattr("granola_cli.GranolaClient", FakeClient)
    monkeypatch.setattr("granola_cli.Database.finish_fetch_run", failing_finish)

    with pytest.raises(RuntimeError, match="boom"):
        main(
            [
                "fetch",
                "--db-path",
                str(db_path),
                "--api-key-file",
                str(key_path),
                "--api-base-url",
                "http://127.0.0.1:8765",
            ]
        )


def test_status_defaults_to_json_when_not_tty(tmp_path, capsys) -> None:
    db = open_database(str(tmp_path / "granola.sqlite3"))
    db.close()

    with patch("sys.stdout.isatty", return_value=False):
        result = main(["status", "--db-path", str(tmp_path / "granola.sqlite3")])

    captured = capsys.readouterr()
    assert result == 0
    assert '"db_path":' in captured.out
    assert '"fts_index": "empty"' in captured.out


def test_status_human_output(tmp_path, capsys) -> None:
    db = open_database(str(tmp_path / "granola.sqlite3"))
    db.upsert_note(sample_note(created_at="2026-01-27T15:30:00Z"))
    run_id = db.start_fetch_run(overwrite_from=None, dry_run=False)
    db.set_fetch_discovered(run_id, 1)
    db.record_fetch_success(
        run_id, sample_note(updated_at="2026-01-27T16:45:00Z")
    )
    db.finish_fetch_run(run_id, status="success", rebuild_fts=True, update_watermark=True)
    db.close()

    with patch("sys.stdout.isatty", return_value=True):
        result = main(["status", "--db-path", str(tmp_path / "granola.sqlite3")])

    captured = capsys.readouterr()
    assert result == 0
    assert "DB: " in captured.out
    assert "Notes: 1 (2026-01-27 → 2026-01-27)" in captured.out
    assert "FTS index: current" in captured.out


def test_status_unreadable_db_returns_nonzero(tmp_path, capsys) -> None:
    db_path = tmp_path / "missing" / "blocked.sqlite3"

    with patch("granola_cli.open_database", side_effect=__import__("sqlite3").OperationalError("unable to open database file")):
        result = main(["status", "--db-path", str(db_path), "--json"])

    captured = capsys.readouterr()
    assert result == 1
    assert '"error": "database_error"' in captured.err
