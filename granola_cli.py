from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

from granola.client import ApiError, GranolaClient
from granola.config import (
    AppConfig,
    default_config,
    load_or_create_config,
)
from granola.db import Database
from granola.export import (
    export_note_files,
    raw_json_text,
    summary_text,
    transcript_text,
)
from granola.formatter import (
    OutputMode,
    detect_output_mode,
    format_error,
    format_list_rows,
    format_search_rows,
    format_status,
)
from granola.ratelimit import RateLimiter
from granola.search import SearchEngine
from granola.util import normalize_user_datetime

DEFAULT_API_KEY_FILE = "~/.config/granola/api_key.txt"

logger = logging.getLogger("granola")


class CommandError(Exception):
    def __init__(
        self,
        error: str,
        message: str,
        *,
        exit_code: int,
        retryable: bool,
        **context: object,
    ):
        super().__init__(message)
        self.error = error
        self.message = message
        self.exit_code = exit_code
        self.retryable = retryable
        self.context = context


def build_parser(config: AppConfig | None = None) -> argparse.ArgumentParser:
    config = config or default_config()
    root_common = _common_parser(use_defaults=True, db_path=config.db_path)
    subcommand_common = _common_parser(use_defaults=False, db_path=config.db_path)

    parser = argparse.ArgumentParser(description="Granola CLI", parents=[root_common])

    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch",
        parents=[subcommand_common],
        help="Sync notes from the API into the local SQLite database",
    )
    fetch_parser.add_argument(
        "--overwrite-from",
        help="If ISO date/datetime: re-fetch and overwrite from that updated_at point. If 'all': re-fetch everything.",
    )
    fetch_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run discovery only and show what would be fetched",
    )
    fetch_parser.add_argument("--api-key-file", default=DEFAULT_API_KEY_FILE)
    fetch_parser.add_argument("--api-base-url", default=config.api_base_url)
    fetch_parser.add_argument("--page-size", type=int, default=30)

    list_parser = subparsers.add_parser(
        "list",
        parents=[subcommand_common],
        help="List notes from the local DB by created_at",
    )
    list_parser.add_argument(
        "--date-start",
        help="Inclusive lower bound on note creation date (created_at, UTC). Accepts YYYY-MM-DD or ISO datetime.",
    )
    list_parser.add_argument(
        "--date-end",
        help="Inclusive upper bound on note creation date (created_at, UTC).",
    )
    list_parser.add_argument("--limit", type=int, default=50)
    list_parser.add_argument("--detailed", action="store_true")

    get_parser = subparsers.add_parser(
        "get", parents=[subcommand_common], help="Retrieve one note from the local DB"
    )
    get_parser.add_argument("note_id")
    get_parser.add_argument(
        "--summary", action="store_true", help="Print the summary text"
    )
    get_parser.add_argument(
        "--transcript",
        action="store_true",
        help="Print the transcript in me:/them: format",
    )

    search_parser = subparsers.add_parser(
        "search",
        parents=[subcommand_common],
        help="Search stored notes by created_at range",
    )
    search_parser.add_argument("query")
    search_parser.add_argument(
        "--in",
        dest="scope",
        choices=["transcript", "summary"],
        help="Scope search to 'transcript' or 'summary' only. If omitted, searches across title, summary, and transcript.",
    )
    search_parser.add_argument(
        "--date-start",
        help="Inclusive lower bound on note creation date (created_at, UTC). Accepts YYYY-MM-DD or ISO datetime.",
    )
    search_parser.add_argument(
        "--date-end",
        help="Inclusive upper bound on note creation date (created_at, UTC). Accepts YYYY-MM-DD or ISO datetime.",
    )
    search_parser.add_argument("--limit", type=int, default=20)

    output_parser = subparsers.add_parser(
        "output",
        parents=[subcommand_common],
        help="Bulk-export notes from the local DB by created_at",
    )
    output_parser.add_argument(
        "--date-start",
        help="Inclusive lower bound on note creation date (created_at, UTC). Accepts YYYY-MM-DD or ISO datetime.",
    )
    output_parser.add_argument(
        "--date-end",
        help="Inclusive upper bound on note creation date (created_at, UTC). Accepts YYYY-MM-DD or ISO datetime.",
    )
    output_parser.add_argument("--note-id", action="append", default=[])
    output_parser.add_argument("--summary", action="store_true")
    output_parser.add_argument("--transcript", action="store_true")
    output_parser.add_argument(
        "--all", action="store_true", help="Output raw JSON files"
    )
    output_parser.add_argument("--artifacts-dir", default="./artifacts")

    subparsers.add_parser(
        "status",
        parents=[subcommand_common],
        help="Show local database and sync status",
    )

    return parser


def _common_parser(*, use_defaults: bool, db_path: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--db-path",
        default=db_path if use_defaults else argparse.SUPPRESS,
        help=f"Override SQLite file (default: {db_path})",
    )
    parser.add_argument(
        "--log-level",
        default="INFO" if use_defaults else argparse.SUPPRESS,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--json",
        action="store_true",
        default=False if use_defaults else argparse.SUPPRESS,
        help="Force JSON/JSONL output regardless of TTY detection",
    )
    mode_group.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False if use_defaults else argparse.SUPPRESS,
        help="Bare minimal output",
    )
    return parser


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    return build_parser(load_or_create_config()).parse_args(argv)


def emit_stdout(text: str) -> None:
    if text:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")


def read_api_key(path: str) -> str:
    try:
        api_key = Path(path).expanduser().read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise CommandError(
            "auth_failed",
            f"Unable to read API key file {path}: {exc.strerror or str(exc)}",
            exit_code=4,
            retryable=False,
            path=path,
        ) from exc
    if not api_key:
        raise CommandError(
            "auth_failed",
            f"API key file {path} is empty",
            exit_code=4,
            retryable=False,
            path=path,
        )
    return api_key


def open_database(path: str) -> Database:
    db = Database(path)
    db.initialize()
    return db


def fetch_updated_after(db: Database, overwrite_from: str | None) -> str | None:
    if overwrite_from == "all":
        return None
    if overwrite_from:
        return normalize_user_datetime(overwrite_from, is_end=False)
    return db.get_sync_state("last_watermark")


def run_fetch(args: argparse.Namespace, mode: OutputMode) -> int:
    db = open_database(args.db_path)
    run_id = db.start_fetch_run(
        overwrite_from=args.overwrite_from, dry_run=args.dry_run
    )
    try:
        api_key = read_api_key(args.api_key_file)
        client = GranolaClient(
            api_key,
            api_base_url=args.api_base_url,
            rate_limiter=RateLimiter(database=db),
        )
        updated_after = fetch_updated_after(db, args.overwrite_from)
        notes = client.iter_note_summaries(
            updated_after=updated_after, page_size=min(args.page_size, 30)
        )
        db.set_fetch_discovered(run_id, len(notes))

        if args.dry_run:
            rows = [
                {
                    "note_id": note["id"],
                    "title": note.get("title"),
                    "created_at": note["created_at"],
                    "updated_at": note["updated_at"],
                    "note": note,
                }
                for note in notes
            ]
            emit_stdout(format_list_rows(rows, mode=mode, detailed=False))
            db.finish_fetch_run(
                run_id,
                status="dry_run",
            )
            return 0

        for note_summary in notes:
            note_id = note_summary["id"]
            try:
                note = client.get_note(note_id)
                db.record_fetch_success(run_id, note)
            except ApiError as exc:
                db.record_fetch_failure(run_id)
                logger.warning("failed to fetch %s: %s", note_id, exc.message)

        run_row = db.finish_fetch_run(
            run_id,
            rebuild_fts=True,
            update_watermark=True,
        )
        watermark = db.get_sync_state("last_watermark")

        logger.info(
            "fetch complete: discovered=%s fetched=%s failed=%s watermark=%s",
            run_row["notes_discovered"],
            run_row["notes_fetched"],
            run_row["notes_failed"],
            watermark,
        )
        if mode is OutputMode.JSON:
            emit_stdout(
                json.dumps(
                    {
                        "notes_discovered": run_row["notes_discovered"],
                        "notes_fetched": run_row["notes_fetched"],
                        "notes_failed": run_row["notes_failed"],
                        "watermark": watermark,
                    },
                    ensure_ascii=False,
                )
            )
        return 6 if run_row["notes_failed"] else 0
    except Exception as exc:
        try:
            db.finish_fetch_run(
                run_id,
                status="failed",
                error=str(exc),
                rebuild_fts=True,
            )
        except Exception:
            logger.exception("failed to finalize fetch run after original error")
        raise
    finally:
        db.close()


def run_list(args: argparse.Namespace, mode: OutputMode) -> int:
    db = open_database(args.db_path)
    try:
        rows = db.list_notes(
            date_start=args.date_start, date_end=args.date_end, limit=args.limit
        )
        emit_stdout(format_list_rows(rows, mode=mode, detailed=args.detailed))
        return 0
    finally:
        db.close()


def run_get(args: argparse.Namespace, mode: OutputMode) -> int:
    db = open_database(args.db_path)
    try:
        note = db.get_note(args.note_id)
        if note is None:
            raise CommandError(
                "not_found",
                f"Note {args.note_id} not found in local database",
                exit_code=3,
                retryable=False,
                note_id=args.note_id,
            )
        if args.json:
            emit_stdout(raw_json_text(note))
            return 0
        if args.transcript:
            emit_stdout(transcript_text(note))
            return 0
        if args.summary:
            emit_stdout(summary_text(note))
            return 0
        if mode is OutputMode.JSON:
            emit_stdout(raw_json_text(note))
            return 0
        emit_stdout(summary_text(note))
        return 0
    finally:
        db.close()


def run_search(args: argparse.Namespace, mode: OutputMode) -> int:
    db = open_database(args.db_path)
    try:
        search_engine = SearchEngine(db.connection)
        try:
            rows = search_engine.search(
                args.query,
                scope=args.scope,
                date_start=args.date_start,
                date_end=args.date_end,
                limit=args.limit,
            )
        except Exception as exc:
            if "no such table: notes_fts" in str(exc):
                raise CommandError(
                    "usage_error",
                    "FTS index missing. Run fetch first.",
                    exit_code=1,
                    retryable=False,
                ) from exc
            raise
        if not rows:
            logger.info("No results found")
            return 0
        emit_stdout(format_search_rows(rows, mode=mode))
        return 0
    finally:
        db.close()


def run_output(args: argparse.Namespace, mode: OutputMode) -> int:
    db = open_database(args.db_path)
    try:
        include_json = args.all or not (args.all or args.summary or args.transcript)
        include_summary = args.summary or not (
            args.all or args.summary or args.transcript
        )
        include_transcript = args.transcript or not (
            args.all or args.summary or args.transcript
        )
        notes = db.exportable_notes(
            note_ids=args.note_id, date_start=args.date_start, date_end=args.date_end
        )
        artifacts_dir = Path(args.artifacts_dir)
        written_paths: list[str] = []
        for note in notes:
            paths = export_note_files(
                note,
                artifacts_dir,
                include_json=include_json,
                include_summary=include_summary,
                include_transcript=include_transcript,
            )
            for path in paths:
                logger.info("wrote %s", path)
                written_paths.append(str(path))
        if mode is OutputMode.JSON:
            emit_stdout(json.dumps({"files": written_paths}, ensure_ascii=False))
        elif mode is OutputMode.QUIET:
            emit_stdout("\n".join(written_paths))
        return 0
    finally:
        db.close()


def run_status(args: argparse.Namespace, mode: OutputMode) -> int:
    try:
        db = open_database(args.db_path)
    except sqlite3.Error as exc:
        raise CommandError(
            "database_error",
            f"Unable to open local database: {exc}",
            exit_code=1,
            retryable=False,
            db_path=args.db_path,
        ) from exc

    try:
        emit_stdout(format_status(db.status_summary(), mode=mode))
        return 0
    except sqlite3.Error as exc:
        raise CommandError(
            "database_error",
            f"Unable to read local database status: {exc}",
            exit_code=1,
            retryable=False,
            db_path=args.db_path,
        ) from exc
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    mode = detect_output_mode(args.json, args.quiet)

    try:
        if args.command == "fetch":
            return run_fetch(args, mode)
        if args.command == "list":
            return run_list(args, mode)
        if args.command == "get":
            return run_get(args, mode)
        if args.command == "search":
            return run_search(args, mode)
        if args.command == "output":
            return run_output(args, mode)
        if args.command == "status":
            return run_status(args, mode)
        raise CommandError(
            "usage_error",
            f"Unknown command: {args.command}",
            exit_code=2,
            retryable=False,
        )
    except ApiError as exc:
        sys.stderr.write(
            format_error(
                mode,
                error=exc.error,
                message=exc.message,
                retryable=exc.retryable,
                **exc.context,
            )
            + "\n"
        )
        return exc.exit_code
    except CommandError as exc:
        sys.stderr.write(
            format_error(
                mode,
                error=exc.error,
                message=exc.message,
                retryable=exc.retryable,
                **exc.context,
            )
            + "\n"
        )
        return exc.exit_code
    except ValueError as exc:
        sys.stderr.write(
            format_error(mode, error="usage_error", message=str(exc), retryable=False)
            + "\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
