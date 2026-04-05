# granola-cli

granola-cli is a Python CLI for downloading, searching, and exporting Granola meeting notes and transcripts into a local SQLite database. It works with both Personal and Enterprise API keys and keeps local querying separate from the remote API after sync.

## Design philosophy

This tool is built for humans at a terminal and AI agents in shell pipelines. Output adapts to context automatically: human-friendly text on a TTY, structured JSON or JSONL when piped, with `--json` and `--quiet` available for explicit control. The command flow is summary-first and local-first: `fetch` builds the archive, then `list`, `search`, `get`, and `output` work from SQLite with FTS5-backed search and structured errors.

## Quickstart

Put your API key at `~/.config/granola/api_key.txt`, then run:

```bash
uv run granola_cli.py fetch
uv run granola_cli.py list
uv run granola_cli.py search "topic"
uv run granola_cli.py get <note_id> --transcript
```

## Commands

### fetch

Sync notes from the Granola API into the local SQLite database.

Important flags: `--overwrite-from`, `--dry-run`, `--api-key-file`, `--api-base-url`, `--page-size`

```bash
uv run granola_cli.py fetch --overwrite-from 2026-01-01
```

### list

List locally stored notes filtered by `created_at`.

Important flags: `--date-start`, `--date-end`, `--limit`, `--detailed`

```bash
uv run granola_cli.py list --date-start 2026-03-01 --detailed
```

### get

Read a single note from the local database.

Important flags: `--summary`, `--transcript`, `--json`

```bash
uv run granola_cli.py get not_1d3tmYTlCICgjy --summary
```

### search

Search local notes with SQLite FTS5.

Important flags: `--in`, `--date-start`, `--date-end`, `--limit`

```bash
uv run granola_cli.py search "budget review" --in transcript
```

### output

Export local notes to `./artifacts` or another directory.

Important flags: `--note-id`, `--date-start`, `--date-end`, `--summary`, `--transcript`, `--all`, `--artifacts-dir`

```bash
uv run granola_cli.py output --all --summary --transcript
```

Run `--help` on any subcommand for details.

## Agent usage

TTY detection means shell pipelines get machine-readable output by default.

```bash
uv run granola_cli.py search "Q1 planning" --quiet | xargs -I{} uv run granola_cli.py get {} --transcript
uv run granola_cli.py list --json
uv run granola_cli.py output --quiet
```

Use `--json` to force JSON/JSONL and `--quiet` for bare values such as note IDs or written file paths.

## How it works

`fetch` uses the Granola list endpoint for note discovery and then fetches each note with transcript data for canonical storage. Incremental sync uses an `updated_at` watermark stored in SQLite so edits to older notes are captured. Local commands filter by `created_at`, while search uses an FTS5 index rebuilt after fetch runs.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General or unexpected failure |
| 2 | Usage error |
| 3 | Resource not found |
| 4 | Authentication failure |
| 5 | Rate limited after retries |
| 6 | Partial fetch failure |

## Configuration

The default API key path is `~/.config/granola/api_key.txt`. Runtime config is stored in `~/.config/granola/config.toml`, which provides `api_base_url` and `db_path`. By default the database path is `~/.local/share/granola-cli/granola-cli.sqlite3`, and the parent directory is created automatically on startup. You can still override the API base URL with `--api-base-url` and the SQLite database path with `--db-path`. Personal and Enterprise API keys both work; they only differ in which notes are visible.

## Development

Run tests with:

```bash
uv run -m pytest
```

Run linting with:

```bash
uv run ruff check .
```

Use `--log-level DEBUG` for verbose logging during development.
