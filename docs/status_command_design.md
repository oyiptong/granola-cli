# Status command design

## Goal

Add a local-only `status` subcommand to `granola-cli` that gives humans and agents a compact summary of the current local archive state without making any API calls.

The command must answer three questions:

1. Which database file is this CLI using?
2. What note corpus is currently stored locally?
3. What is the current incremental-sync and FTS state?

## Scope

This command reads from the local SQLite database only. It does not read the API key, does not contact the Granola API, and does not mutate database state.

The command is added to the existing command surface:

```bash
granola-cli status
granola-cli status --json
```

It follows the existing output-mode contract already used by the CLI:

- human-readable output when stdout is a TTY
- JSON when `--json` is passed
- JSON by default when stdout is not a TTY

`--quiet` remains part of the global parser, but this design does not define a special quiet-specific status format. The simplest implementation is to treat quiet the same as human output unless the project later wants a dedicated minimal mode.

## Acceptance criteria

- `uv run granola_cli.py status` prints human-friendly status to stdout
- `uv run granola_cli.py status --json` emits a single JSON object
- when stdout is not a TTY, output defaults to JSON
- all values come from the local DB only
- exit code is `0` unless the DB is unreadable

## Output contract

### JSON

```json
{
  "db_path": "/absolute/path/to/granola.db",
  "notes": {
    "count": 847,
    "earliest_created": "2024-03-12",
    "latest_created": "2026-04-04",
    "last_synced_at": "2026-04-05T08:23:11Z",
    "watermark": "2026-04-04T17:45:00Z"
  },
  "fts_index": "current"
}
```

### Human output

```text
DB: /absolute/path/to/granola.db
Notes: 847 (2024-03-12 → 2026-04-04)
Last synced: 2026-04-05 08:23 UTC
FTS index: current
```

## Field definitions

### db_path

The absolute path of the SQLite database currently opened by the CLI.

Source:
- `Database.path`, which already expands the configured path in `granola/db.py`

### notes.count

The total number of rows in `notes`.

### notes.earliest_created

The minimum `created_at` date across stored notes, rendered as `YYYY-MM-DD`.

If there are no notes, this value is `null`.

### notes.latest_created

The maximum `created_at` date across stored notes, rendered as `YYYY-MM-DD`.

If there are no notes, this value is `null`.

### notes.last_synced_at

The `finished_at` value of the most recent successful fetch run.

Definition of successful here:
- use the newest row in `fetch_runs` where `status = 'success'`

If there has never been a successful fetch, this value is `null`.

This deliberately excludes `partial_failure`, because the proposed meaning is “the last time a complete sync finished successfully.”

### notes.watermark

The value currently stored in `sync_state.last_watermark`.

This is the value the next incremental fetch will use when `--overwrite-from` is not provided.

If no watermark has been stored yet, this value is `null`.

### fts_index

This design intentionally defines `fts_index` in terms of current persisted signals, not inferred external behavior.

Definitions:

- `empty`: no note rows exist in `notes_fts`
- `current`: at least one successful or partial fetch run has finished, and `notes_fts` contains rows for the current local archive
- `stale`: local note rows exist, but `notes_fts` is empty

This definition is conservative and implementable with the current schema. It does **not** claim to detect arbitrary out-of-band drift, because the database does not currently persist a dedicated “last FTS rebuild timestamp” or “notes changed since rebuild” marker.

### Why this definition

The current code rebuilds FTS inside fetch finalization and uses SQLite FTS5 as the local text-search source of truth. What the DB does **not** currently store is an explicit freshness timestamp for the index. That means a stronger definition such as “stale if notes were added since last rebuild” would require new bookkeeping.

This design chooses the simplest valid interpretation that matches current persisted data.

## Data sources

The command should be satisfied from existing local state:

- `notes`
  - count
  - earliest and latest `created_at`
- `fetch_runs`
  - last successful `finished_at`
  - evidence that fetch finalization has happened
- `sync_state`
  - `last_watermark`
- `notes_fts`
  - whether the index is empty or populated

No schema changes are required for the first version.

## DB helper shape

Add a single read-only summary helper in `granola/db.py` that returns a normalized payload for the command.

Suggested shape:

```python
def status_summary(self) -> dict:
    ...
```

The helper should perform local aggregate queries and return already-normalized values for:

- `db_path`
- note count
- earliest/latest created date
- latest successful `finished_at`
- stored watermark
- FTS state

This keeps the command implementation in `granola_cli.py` thin and consistent with the current pattern of pushing data access into the DB layer.

## CLI shape

### Parser

Add a new subparser:

```python
status_parser = subparsers.add_parser(
    "status",
    parents=[subcommand_common],
    help="Show local database and sync status",
)
```

No status-specific flags are required for the first version.

### Command handler

Add:

```python
def run_status(args: argparse.Namespace, mode: OutputMode) -> int:
    ...
```

and dispatch it from `main()`.

The handler should:

1. open the local DB
2. read the summary helper
3. format either JSON or human output
4. return `0`

Unreadable DB behavior should continue to use the CLI's existing error path and exit semantics.

## Formatting

Add dedicated status-format helpers in `granola/formatter.py` rather than inlining formatting in the command handler.

Suggested helpers:

```python
def format_status(payload: dict, *, mode: OutputMode) -> str:
    ...
```

Human formatting rules:

- first line shows `DB: <path>`
- second line shows note count and date span
  - when count is `0`, render `Notes: 0`
  - when dates are present, render `Notes: <count> (<earliest> → <latest>)`
- third line shows `Last synced: ...`
  - render `Last synced: never` when `last_synced_at` is `null`
- fourth line shows `FTS index: <state>`

JSON formatting rules:

- emit one JSON object, not JSONL
- preserve `null` values as JSON `null`

## Edge cases

### Fresh DB

- `count = 0`
- `earliest_created = null`
- `latest_created = null`
- `last_synced_at = null`
- `watermark = null`
- `fts_index = empty`

### Never synced

- `last_synced_at = null`
- `watermark = null`

### Partial fetch history

If only partial failures exist and no successful fetch has completed:

- `last_synced_at = null`
- `watermark = null` unless some earlier successful run stored one
- `fts_index` still evaluates from local DB contents and FTS rows, not from remote sync assumptions

### Unreadable DB

The command should fail through the existing unreadable-database error path and return a non-zero exit code.

## Test plan

### CLI tests

- parser accepts `status`
- `status --json` emits a single JSON object
- non-TTY default mode emits JSON
- human output matches the expected line-oriented format
- unreadable DB returns non-zero

### DB tests

- empty DB summary returns all-null/zero values
- populated DB summary returns correct count and date span
- summary picks latest successful fetch run for `last_synced_at`
- watermark is read from `sync_state.last_watermark`
- FTS state resolves to `empty`, `current`, and `stale` according to the definitions above

## Manual QA

Run at least:

```bash
uv run granola_cli.py status
uv run granola_cli.py status --json
uv run granola_cli.py status | cat
```

The final command verifies the non-TTY JSON default.

## Recommendation

Implement the command without schema changes first. The command is useful for both humans and agents now, and the conservative `fts_index` definition keeps the feature grounded in the state the current database actually stores.

If later the project wants stricter freshness semantics, add an explicit FTS rebuild marker in bookkeeping as a follow-up rather than overloading the first version.
