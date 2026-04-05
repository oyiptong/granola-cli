# Granola CLI Download Tool — Coding Agent Prompt

## Acceptance criteria

The implementation is correct if:

- `uv run granola_cli.py fetch` incrementally syncs notes into SQLite
- `uv run granola_cli.py fetch --overwrite-from 2026-01-01` re-fetches from that point onward
- `uv run granola_cli.py fetch --overwrite-from all` re-fetches everything accessible
- `uv run granola_cli.py fetch --dry-run` shows what would be fetched without writing to the DB
- `uv run granola_cli.py list` shows notes in the local DB with human-friendly formatting
- `uv run granola_cli.py list --json` emits one JSON object per line (JSONL)
- `uv run granola_cli.py list --quiet` emits bare note IDs, one per line
- `uv run granola_cli.py get <note_id> --summary` prints summary text to stdout
- `uv run granola_cli.py get <note_id> --transcript` prints transcript to stdout
- `uv run granola_cli.py get <note_id> --json` prints the full canonical JSON to stdout
- `uv run granola_cli.py output --all` writes raw JSON files into `./artifacts`
- `uv run granola_cli.py output --summary` writes summary text files
- `uv run granola_cli.py output --transcript` writes transcript text files in `me:` / `them:` format
- `uv run granola_cli.py output` with no content flags defaults to writing all output types
- `uv run granola_cli.py search "yoghurt"` returns matching notes ranked by relevance
- `uv run granola_cli.py search "yoghurt" --in transcript` searches only transcript text
- `uv run granola_cli.py search "yoghurt" --in summary` searches only summary text
- `uv run granola_cli.py search "yoghurt" --quiet` emits bare note IDs of matches
- Filenames follow the exact pattern described in the "Output filename requirements" section
- The FTS index is rebuilt automatically after each `fetch` run
- API rate limits are respected and 429s are handled gracefully
- When stdout is not a TTY, all subcommands default to machine-readable output (JSON/JSONL)
- Exit codes follow the documented error contract
- Rerunning fetch/output is safe and deterministic
- All unit tests pass with `uv run -m pytest`

---

## Agent workflow examples

These examples illustrate the intended composability of the CLI. The implementation should make these pipelines work naturally.

```bash
# Workflow 1: Incremental sync, then search for a topic
uv run granola_cli.py fetch
uv run granola_cli.py search "budget review" --json

# Workflow 2: Find a meeting, get its transcript
NOTE_ID=$(uv run granola_cli.py search "onboarding" --quiet | head -1)
uv run granola_cli.py get "$NOTE_ID" --transcript

# Workflow 3: List recent meetings, pick one, get summary
uv run granola_cli.py list --date-start 2026-03-01 --quiet
uv run granola_cli.py get not_1d3tmYTlCICgjy --summary

# Workflow 4: Bulk export everything to disk
uv run granola_cli.py output --all --summary --transcript

# Workflow 5: Agent pipeline — search, filter, process
uv run granola_cli.py search "Q1 planning" --quiet | \
  xargs -I{} uv run granola_cli.py get {} --transcript

# Workflow 6: Dry run before a big re-fetch
uv run granola_cli.py fetch --overwrite-from 2026-01-01 --dry-run
```

---

## Granola API reference (canonical, inline)

Use this section as the source of truth for all API behavior. Do NOT fetch external documentation.

### General

- **Base URL default:** `https://public-api.granola.ai`
- **Auth:** `Authorization: Bearer <token>`
- **API key types:** Granola has both Personal API keys (access to your own notes) and Enterprise API keys (workspace-wide access). The CLI should work with either — the endpoints and rate limits are the same; only the scope of visible notes differs. The CLI should not distinguish between them.
- **Rate limits (per user or per workspace):**

  | Metric          | Value                        |
  |-----------------|------------------------------|
  | Burst capacity  | 25 requests                  |
  | Time window     | 5 seconds                    |
  | Sustained rate  | 5 requests/second (300/min)  |

- When rate limits are exceeded, the API returns `429 Too Many Requests`.

### GET /v1/notes — List Notes

Returns a paginated list of note summaries. **Does NOT include** `summary_text`, `summary_markdown`, `transcript`, `attendees`, `calendar_event`, or `folder_membership` — only discovery-level metadata.

**Query parameters:**

| Parameter        | Type                    | Description                                  |
|------------------|-------------------------|----------------------------------------------|
| `created_before` | string (date or datetime) | Notes created before this date             |
| `created_after`  | string (date or datetime) | Notes created after this date              |
| `updated_after`  | string (date or datetime) | Notes updated after this date              |
| `cursor`         | string                  | Pagination cursor from previous response     |
| `page_size`      | integer (1–30)          | Max notes per page. **API default is 10.**   |

**Response shape:**

```json
{
  "notes": [
    {
      "id": "not_1d3tmYTlCICgjy",
      "object": "note",
      "title": "Quarterly yoghurt budget review",
      "owner": {
        "name": "Oat Benson",
        "email": "oat@granola.ai"
      },
      "created_at": "2026-01-27T15:30:00Z",
      "updated_at": "2026-01-27T16:45:00Z"
    }
  ],
  "hasMore": true,
  "cursor": "eyJjcmVkZW50aWFsfQ=="
}
```

### GET /v1/notes/{note_id} — Get Note

Returns the full note payload. Pass `?include=transcript` to include the transcript.

**Path parameter:** `note_id` — pattern: `^not_[a-zA-Z0-9]{14}$`

**Query parameter:** `include` — enum, only value is `transcript`

**Response shape (with `?include=transcript`):**

```json
{
  "id": "not_1d3tmYTlCICgjy",
  "object": "note",
  "title": "Quarterly yoghurt budget review",
  "owner": {
    "name": "Oat Benson",
    "email": "oat@granola.ai"
  },
  "created_at": "2026-01-27T15:30:00Z",
  "updated_at": "2026-01-27T16:45:00Z",
  "calendar_event": {
    "event_title": "Quarterly yoghurt budget review",
    "invitees": [{ "email": "raisin@granola.ai" }],
    "organiser": "oat@granola.ai",
    "calendar_event_id": "2su99n6iiik37iiknmb5t4fkfh_20260127T153000Z",
    "scheduled_start_time": "2026-01-27T15:30:00Z",
    "scheduled_end_time": "2026-01-27T16:30:00Z"
  },
  "attendees": [
    { "name": "Oat Benson", "email": "oat@granola.ai" },
    { "name": "Raisin Patel", "email": "raisin@granola.ai" }
  ],
  "folder_membership": [
    { "id": "fol_4y6LduVdwSKC27", "object": "folder", "name": "Top secret recipes" }
  ],
  "summary_text": "The quarterly yoghurt budget review was a success. We spent $100,000 on yoghurt and made $150,000 in profit.",
  "summary_markdown": "## Quarterly Yoghurt Budget Review\n\n...",
  "transcript": [
    {
      "speaker": { "source": "microphone" },
      "text": "I'm done pretending. Greek is the only yoghurt that deserves us.",
      "start_time": "2026-01-27T15:30:00Z",
      "end_time": "2026-01-27T16:30:00Z"
    },
    {
      "speaker": { "source": "speaker" },
      "text": "Finally. Regular yoghurt is just milk that gave up halfway.",
      "start_time": "2026-01-27T15:30:00Z",
      "end_time": "2026-01-27T16:30:00Z"
    }
  ]
}
```

**Nullability rules from the API schema:**

- Always present (required, non-null): `id`, `object`, `owner`, `created_at`, `updated_at`, `calendar_event`, `attendees`, `folder_membership`, `summary_text`
- Nullable: `title`, `summary_markdown`, `transcript`

---

## Context and environment

- API key stored at: `~/.config/granola/api_key.txt` (may be Personal or Enterprise — both work)
- Project directory: `~/Projects/github/granola_download/`
- Use `uv` to run the program and manage dependencies
- Use Python 3.11+
- Prefer minimal dependencies; use the standard library wherever practical
- `requests` is the only allowed third-party runtime dependency
- `pytest` is the only allowed test dependency

## Explicit constraints — do NOT:

- Do NOT use asyncio
- Do NOT use SQLAlchemy or any ORM
- Do NOT use click or typer — use argparse
- Do NOT create a separate `__main__.py` entrypoint
- Do NOT fetch external documentation URLs at build or runtime
- Do NOT add dependencies beyond `requests` and `pytest`

---

## High-level goal

Create a CLI program that:

1. Fetches Granola notes and transcripts from the API and stores them in a local SQLite database
2. Supports incremental sync by default, with the ability to re-fetch from a given date or from scratch
3. Provides lightweight local querying: listing, searching (FTS5), and single-note retrieval — all from the local DB, no API calls
4. Can bulk-export stored notes to disk as raw JSON, plain text summaries, and plain text transcripts
5. Is designed for both humans and shell-based AI agents, with output that adapts to context
6. Has unit tests covering core logic

---

## Design principles

This CLI is designed to be equally useful for humans at a terminal and for AI agents operating through a shell. The key design principles:

**1. Stdout is the data contract; stderr is for everything else.**
All data output (notes, search results, JSON) goes to stdout. All progress, logging, warnings, and diagnostics go to stderr. This means `granola_cli.py list 2>/dev/null` gives you clean data, and agents can capture stdout without noise.

**2. Output adapts to context via TTY detection.**
When stdout is a TTY (human at a terminal), subcommands produce human-friendly formatted output by default. When stdout is piped or redirected (agent, script, or `| jq`), subcommands default to machine-readable output (JSON or JSONL). The `--json` flag forces JSON regardless of TTY. The `--quiet` / `-q` flag forces bare values (e.g. just note IDs, one per line). This means humans never need to think about `--json`, and agents get structured data automatically.

**3. Summary-first, drill-down-later.**
`list` shows compact metadata. `search` finds relevant notes. `get` retrieves one note's content. `output` exports to disk. The agent (or human) moves from broad to narrow, consuming only the tokens or screen space they need at each step.

**4. Errors are structured and actionable.**
Error output includes an error code, the failing input, and whether the failure is retryable. Exit codes have semantic meaning. See the "Error contract" section.

**5. Transcript fetching is explicit, never implicit.**
The `fetch` subcommand always fetches transcripts (since it's building a local archive). But `list` and `search` never return transcript content. `get` requires `--transcript` or `--json` to include transcript content. This prevents accidental token bloat when an agent just needs metadata.

---

## CLI design

Use `argparse` with subcommands.

### Global flags

These flags are available on all subcommands:

| Flag                                        | Description                                                    |
|---------------------------------------------|----------------------------------------------------------------|
| `--db-path <path>`                          | Override SQLite file (default: `./granola.sqlite3`)            |
| `--log-level <DEBUG\|INFO\|WARNING\|ERROR>` | Logging verbosity (default: INFO)                              |
| `--json`                                    | Force JSON/JSONL output regardless of TTY detection            |
| `--quiet` / `-q`                            | Bare minimal output (e.g. just note IDs, one per line)         |

`--json` and `--quiet` are mutually exclusive. If neither is specified, output format is determined by TTY detection: human-friendly if stdout is a TTY, JSON/JSONL if piped.

### Subcommand: `fetch`

Purpose: sync notes from the Granola API into the local SQLite database.

Options:

| Flag                                            | Description                                                                                  |
|-------------------------------------------------|----------------------------------------------------------------------------------------------|
| `--overwrite-from <ISO_DATE_OR_DATETIME\|all>`  | If ISO date/datetime: re-fetch and overwrite from that point. If `all`: re-fetch everything. |
| `--dry-run`                                     | Run the list/discovery phase only. Show what would be fetched. Do not call get-note or write to DB. |
| `--api-key-file <path>`                         | Override API key file (default: `~/.config/granola/api_key.txt`)                             |
| `--api-base-url <url>`                          | Override API base URL (default: `https://public-api.granola.ai`)                             |
| `--page-size <int>`                             | Page size for list requests (default: 30, capped to API max of 30)                           |

Behavior:
- Default: incremental sync using `updated_after` watermarking against the list endpoint
- Calls list endpoint for note discovery, then get-note with `?include=transcript` for each note
- Upserts fetched notes into SQLite (raw JSON + normalized metadata + transcript entries)
- If a previously stored note is fetched again and differs, overwrites stored data
- After upserting, rebuilds the FTS5 search index
- **Watermark update rule:** after all fetches complete, update the watermark to the max `updated_at` among *successfully* fetched notes. If *any* notes failed, do NOT advance the watermark — this prevents gaps.
- If a note fetch fails after retries, log the failure and continue to the next note
- Exit code 6 (partial failure) if some notes failed, exit code 0 if all succeeded

**`--dry-run` output:** a list of note IDs and titles that would be fetched. Respects `--json`/`--quiet`/TTY detection.

**Completion report:** after a non-dry-run fetch, emit a summary to stderr showing notes discovered, fetched, failed, and the new watermark. If `--json` is set, also emit a structured summary to stdout:

```json
{"notes_discovered": 47, "notes_fetched": 47, "notes_failed": 0, "watermark": "2026-04-01T18:30:00Z"}
```

**Important: `fetch` uses `updated_after` (API-side filtering) to discover notes. This is intentionally different from `list`/`output`/`search`, which filter on `created_at` locally. The CLI help text must state which date field each subcommand operates on.**

### Subcommand: `list`

Purpose: list notes in the local database. No API calls.

Options:

| Flag                                        | Description                                                                                              |
|---------------------------------------------|----------------------------------------------------------------------------------------------------------|
| `--date-start <ISO_DATE_OR_DATETIME>`       | Inclusive lower bound on **`created_at`**                                                                |
| `--date-end <ISO_DATE_OR_DATETIME>`         | Inclusive upper bound on **`created_at`**                                                                |
| `--limit <int>`                             | Max notes to show (default: 50)                                                                          |
| `--detailed`                                | Show extended metadata (owner, attendees, folder, word counts)                                           |

**Human-friendly output (TTY):**

```
2026-01-27  Quarterly yoghurt budget review           not_1d3tmYTlCICgjy
2026-01-15  Team standup                              not_2x8abCDeFGHijk
2026-01-10  Product roadmap sync                      not_3y9bcEFgHIJklm
```

With `--detailed`, add columns for owner, attendee count, and whether transcript is available.

**JSON output (piped / `--json`):** JSONL, one object per line:

```json
{"note_id": "not_1d3tmYTlCICgjy", "title": "Quarterly yoghurt budget review", "created_at": "2026-01-27T15:30:00Z", "updated_at": "2026-01-27T16:45:00Z"}
```

With `--detailed`, add `owner_name`, `owner_email`, `attendee_count`, `has_transcript`, `summary_word_count`, `transcript_word_count`.

**Quiet output (`--quiet` / `-q`):** bare note IDs, one per line.

**Help text for `--date-start`:** `"Inclusive lower bound on note creation date (created_at, UTC). Accepts YYYY-MM-DD or ISO datetime."`

### Subcommand: `get`

Purpose: retrieve a single note from the local database and print it to stdout. No API calls.

**Positional argument:** `note_id` — the Granola note ID.

Options:

| Flag            | Description                                                    |
|-----------------|----------------------------------------------------------------|
| `--summary`     | Print the summary text                                         |
| `--transcript`  | Print the transcript in `me:`/`them:` format                   |
| `--json`        | Print the full canonical JSON (overrides `--summary`/`--transcript`) |

If no flag is given, default to `--summary`.

**`--summary` output:** plain text summary, exactly as stored. Trailing newline.

**`--transcript` output:** transcript in `me:`/`them:` format (see "Required file contents" section). If transcript is null/empty, print nothing and exit 0.

**`--json` output:** the stored canonical JSON, pretty-printed.

If the note ID is not found in the local DB, exit with code 3 and an error message that includes the note ID.

### Subcommand: `search`

Purpose: full-text search across stored notes using SQLite FTS5. No API calls.

**Positional argument:** `query` — the search query string. Supports FTS5 query syntax (phrases, AND/OR/NOT, prefix matching with `*`).

Options:

| Flag                                        | Description                                                                                              |
|---------------------------------------------|----------------------------------------------------------------------------------------------------------|
| `--in <transcript\|summary>`                | Scope search to only transcript text or only summary text. If omitted, searches title + summary + transcript. |
| `--date-start <ISO_DATE_OR_DATETIME>`       | Inclusive lower bound on `created_at`                                                                    |
| `--date-end <ISO_DATE_OR_DATETIME>`         | Inclusive upper bound on `created_at`                                                                    |
| `--limit <int>`                             | Max results to return (default: 20)                                                                      |

**Human-friendly output (TTY):**

```
2026-01-27  Quarterly yoghurt budget review  not_1d3tmYTlCICgjy
  ...the [yoghurt] budget was reviewed and we decided...

2026-01-15  Team standup  not_2x8abCDeFGHijk
  ...mentioned the [yoghurt] supplier contract...
```

Use FTS5's `snippet()` with `[` and `]` as highlight markers.

**JSON output (piped / `--json`):** JSONL, one object per line:

```json
{"note_id": "not_1d3tmYTlCICgjy", "title": "Quarterly yoghurt budget review", "created_at": "2026-01-27T15:30:00Z", "snippet": "...the [yoghurt] budget was reviewed and we decided...", "rank": -12.5}
```

**Quiet output (`--quiet` / `-q`):** bare note IDs of matches, one per line.

**Help text for `--in`:** `"Scope search to 'transcript' or 'summary' only. If omitted, searches across title, summary, and transcript."`

Behavior:
- Results ranked by FTS5 relevance (use `rank`)
- If no results, print a message to stderr and exit 0
- If the FTS index doesn't exist, print a clear error suggesting `fetch` and exit 1

### Subcommand: `output`

Purpose: bulk-export notes from the local database to files on disk. No API calls.

Options:

| Flag                                        | Description                                                                                          |
|---------------------------------------------|------------------------------------------------------------------------------------------------------|
| `--date-start <ISO_DATE_OR_DATETIME>`       | Inclusive lower bound on **`created_at`**                                                            |
| `--date-end <ISO_DATE_OR_DATETIME>`         | Inclusive upper bound on **`created_at`**                                                            |
| `--note-id <id>`                            | Export only this note (repeatable for multiple notes)                                                 |
| `--summary`                                 | Output summary text files                                                                            |
| `--transcript`                              | Output transcript text files                                                                         |
| `--all`                                     | Output raw JSON files                                                                                |
| `--artifacts-dir <path>`                    | Override destination directory (default: `./artifacts`)                                              |

Behavior:
- If no date filters or note IDs given, export all notes in the database
- If neither `--summary`, `--transcript`, nor `--all` is specified, default to writing all three
- Create the artifacts directory if it does not exist
- Overwrite existing files deterministically
- Log files written to stderr
- If `--json` is set, emit a structured summary to stdout listing the file paths written
- If `--quiet` is set, emit just the file paths, one per line

---

## Output contract: TTY detection

Implement a helper that checks `sys.stdout.isatty()` and sets the output mode:

| Condition                    | Output mode       |
|------------------------------|-------------------|
| `--json` flag passed         | JSON / JSONL      |
| `--quiet` / `-q` flag passed | Bare values       |
| stdout is a TTY              | Human-friendly    |
| stdout is not a TTY          | JSON / JSONL      |

This means agents piping output get structured data by default. Humans at a terminal get readable output by default. Both can override with explicit flags.

---

## Error contract

### Exit codes

| Code | Meaning                                       |
|------|-----------------------------------------------|
| 0    | Success                                       |
| 1    | General / unexpected failure                  |
| 2    | Usage error (bad arguments, missing required) |
| 3    | Resource not found (note ID not in DB)        |
| 4    | Authentication failure (bad/missing API key)  |
| 5    | Rate limited (after exhausting retries)       |
| 6    | Partial failure (some notes failed in fetch)  |

### Error output

- Human mode (TTY): print a concise error message to stderr.
- JSON mode (piped or `--json`): emit a JSON object to stderr:

```json
{"error": "not_found", "message": "Note not_1d3tmYTlCICgjy not found in local database", "note_id": "not_1d3tmYTlCICgjy", "retryable": false}
```

Error fields:
- `error`: machine-readable error code (e.g. `not_found`, `auth_failed`, `rate_limited`, `fetch_failed`)
- `message`: human-readable description
- `retryable`: boolean — whether retrying the same command might succeed
- Additional context fields as appropriate (e.g. `note_id`, `retry_after_seconds`)

### Retryable vs permanent errors

| Error             | Retryable | Notes                                    |
|-------------------|-----------|------------------------------------------|
| `rate_limited`    | Yes       | Include `retry_after_seconds` if known   |
| `server_error`    | Yes       | 5xx responses                            |
| `network_error`   | Yes       | Connection failures, timeouts            |
| `auth_failed`     | No        | 401/403                                  |
| `not_found`       | No        | Note ID not in DB or API returns 404     |
| `usage_error`     | No        | Bad arguments                            |

---

## Fetch semantics

1. Call the list endpoint with pagination to discover note IDs
2. For each discovered note ID, call get-note with `?include=transcript` for the canonical payload
3. The list endpoint is for discovery only (it does not return summaries, transcripts, or attendees). The get-note endpoint provides the canonical data for storage.
4. If `--overwrite-from <date>` is used, pass that date as `updated_after` to the list endpoint
5. If `--overwrite-from all` is used, do not pass any date filter to the list endpoint
6. For normal incremental mode, use the last successful watermark from `sync_state` as `updated_after`

---

## Date filtering: which field, where

This is intentionally different across subcommands. The CLI help text for each must be explicit.

| Subcommand | Date field used | Where filtering happens | Why                                    |
|------------|-----------------|------------------------|----------------------------------------|
| `fetch`    | `updated_at`    | API-side (list endpoint) | Catch updated older notes, not just new ones |
| `list`     | `created_at`    | Local DB               | "Show me meetings from last week"      |
| `search`   | `created_at`    | Local DB               | Scope search to a time range           |
| `output`   | `created_at`    | Local DB               | Export a date range of meetings        |

Date semantics:
- `--date-start` is inclusive, `--date-end` is inclusive
- Accept either `YYYY-MM-DD` or full ISO datetime
- If only a date is passed, interpret it as `YYYY-MM-DDT00:00:00Z` for start and `YYYY-MM-DDT23:59:59Z` for end

---

## Output filename requirements

For each note exported by `output`, create filenames in this format:

```
./artifacts/[DATE]_note_[TITLE_SLUG]_[NOTE_ID].json
./artifacts/[DATE]_summary_[TITLE_SLUG]_[NOTE_ID].txt
./artifacts/[DATE]_transcript_[TITLE_SLUG]_[NOTE_ID].txt
```

- `[DATE]`: the note's `created_at` in UTC, formatted as `YYYY-MM-DD`
- `[TITLE_SLUG]`: filesystem-safe slug from the note title (see slugging requirements)
- `[NOTE_ID]`: the Granola note ID, e.g. `not_1d3tmYTlCICgjy`

Examples:
- `2026-01-27_note_quarterly-yoghurt-budget-review_not_1d3tmYTlCICgjy.json`
- `2026-01-27_summary_quarterly-yoghurt-budget-review_not_1d3tmYTlCICgjy.txt`
- `2026-01-27_transcript_quarterly-yoghurt-budget-review_not_1d3tmYTlCICgjy.txt`

---

## Required file contents

### Raw JSON (`--all` on `output`, `--json` on `get`)
- The stored canonical JSON payload, written/printed as pretty-printed JSON
- Preserve API field names and structure exactly

### Summary (`--summary` on `output` and `get`)
- Plain text using `summary_text`
- Trailing newline
- If `summary_text` is empty, write an empty file / print nothing

### Transcript (`--transcript` on `output` and `get`)
- Plain text, each entry formatted as:
  ```
  me: [TEXT]
  them: [TEXT]
  ```
- `speaker.source == "microphone"` → `me`
- All other values of `speaker.source` (e.g. `"speaker"`) → `them`
- If `speaker` is null or `speaker.source` is null → `them`
- Preserve transcript order from the API
- Separate entries with a newline
- If transcript is null, write an empty file / print nothing

Example:
```
me: I think we should ship this next week.
them: That works for me as long as we fix onboarding first.
```

---

## Slugging requirements

Implement a title slug function that:
- Lowercases
- Trims whitespace
- Replaces runs of spaces/punctuation with `-`
- Removes characters that are problematic on filesystems (e.g. `/\:*?"<>|`)
- Collapses repeated dashes
- Strips leading/trailing dashes
- Falls back to `untitled` if the title is null, empty, or becomes empty after processing

---

## SQLite requirements

Use `sqlite3` from the standard library directly. No ORM.

### Schema

**`notes` table:**

| Column            | Type    | Constraints        |
|-------------------|---------|--------------------|
| `note_id`         | TEXT    | PRIMARY KEY        |
| `object_type`     | TEXT    | NOT NULL           |
| `title`           | TEXT    | NULL               |
| `owner_name`      | TEXT    | NULL               |
| `owner_email`     | TEXT    | NULL               |
| `created_at`      | TEXT    | NOT NULL           |
| `updated_at`      | TEXT    | NOT NULL           |
| `summary_text`    | TEXT    | NULL               |
| `summary_markdown`| TEXT    | NULL               |
| `raw_json`        | TEXT    | NOT NULL           |
| `fetched_at`      | TEXT    | NOT NULL           |

**`transcript_entries` table:**

| Column           | Type    | Constraints                           |
|------------------|---------|---------------------------------------|
| `note_id`        | TEXT    | NOT NULL                              |
| `entry_index`    | INTEGER | NOT NULL                              |
| `speaker_source` | TEXT    | NULL                                  |
| `text`           | TEXT    | NOT NULL                              |
| `start_time`     | TEXT    | NULL                                  |
| `end_time`       | TEXT    | NULL                                  |

Primary key: `(note_id, entry_index)`

**`sync_state` table:**

| Column | Type | Constraints  |
|--------|------|--------------|
| `key`  | TEXT | PRIMARY KEY  |
| `value`| TEXT | NOT NULL     |

Use `sync_state` to persist:
- `last_watermark`: latest successful incremental `updated_at` watermark
- `schema_version`: for future migrations

### FTS5 full-text search index

```sql
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
    note_id UNINDEXED,
    title,
    summary_text,
    transcript_text,
    content='',
    tokenize='unicode61'
);
```

- `note_id` is `UNINDEXED` — stored for joining, not searchable
- `transcript_text` is the full transcript concatenated per-note (entries joined by newlines, in order)
- `content=''` makes this contentless — canonical data stays in `notes` and `transcript_entries`

**Population:** rebuild at the end of every `fetch` run:
```sql
DELETE FROM notes_fts;
INSERT INTO notes_fts (note_id, title, summary_text, transcript_text)
SELECT
    n.note_id,
    COALESCE(n.title, ''),
    COALESCE(n.summary_text, ''),
    COALESCE(
        (SELECT GROUP_CONCAT(te.text, char(10))
         FROM transcript_entries te
         WHERE te.note_id = n.note_id
         ORDER BY te.entry_index),
        ''
    )
FROM notes n;
```

**Query implementation:**
- `--in transcript`: FTS5 column filter `transcript_text: <query>`
- `--in summary`: FTS5 column filter `summary_text: <query>`
- No `--in` flag: search all columns
- Use `snippet(notes_fts, <col_index>, '[', ']', '...', 32)` for match excerpts
- Join to `notes` for `created_at` date filtering
- Order by `rank`

---

## Rate limiter requirements

Implement **both** proactive throttling and reactive retry handling in a dedicated component/class.

**Proactive throttling:**
- Enforce at most 25 requests in any rolling 5-second window
- Also enforce a minimum inter-request spacing consistent with staying under 5 req/s
- A `collections.deque` of recent request timestamps is acceptable

**Reactive retry handling:**
- On 429: honor `Retry-After` header if present; otherwise exponential backoff with jitter
- Also retry on transient network errors and 5xx responses
- Cap retries at 5
- Log retries clearly to stderr

**Implementation preference:** sequential requests. No aggressive parallelism. Prioritize correctness and politeness over speed.

---

## Code structure

Split into a small package:

```
granola_download/
├── pyproject.toml
├── README.md
├── granola_cli.py            # entrypoint, argparse CLI
├── granola/
│   ├── __init__.py
│   ├── client.py             # API client, requests.Session, auth
│   ├── ratelimit.py          # rate limiter (proactive + reactive)
│   ├── db.py                 # SQLite repository/storage layer
│   ├── export.py             # file export logic (output subcommand)
│   ├── search.py             # FTS5 search logic
│   ├── formatter.py          # TTY detection, output formatting, error formatting
│   └── util.py               # slugging, date helpers
└── tests/
    ├── __init__.py
    ├── test_slug.py
    ├── test_ratelimit.py
    ├── test_db.py
    ├── test_export.py
    ├── test_search.py
    ├── test_formatter.py
    └── test_cli.py
```

Configure the entrypoint in `pyproject.toml` so `uv run granola_cli.py` works.

---

## Unit tests

Use `pytest`. Tests are a required deliverable.

### What to test

**`test_slug.py` — title slugging:**
- Normal titles → correct slug
- Titles with special characters, runs of punctuation, unicode
- Empty / None → `untitled`
- Leading/trailing whitespace and dashes

**`test_ratelimit.py` — rate limiter logic:**
- Proactive throttle delays when burst limit is approached
- That the deque correctly tracks the rolling window

**`test_db.py` — database operations:**
- Schema creation on fresh DB
- Upsert: insert new note, then upsert with changed data and verify overwrite
- Watermark read/write round-trip
- Transcript entry storage and retrieval
- Date filtering for queries (`created_at` range, inclusive bounds)
- Use an in-memory SQLite DB (`:memory:`)

**`test_export.py` — file export:**
- Summary file content from a known note dict
- Transcript file content: microphone → `me`, speaker → `them`, null speaker → `them`
- Transcript with null transcript field → empty file
- Raw JSON round-trip (pretty-printed, structure preserved)
- Filename generation: correct date, slug, note ID
- Use `tmp_path` fixture

**`test_search.py` — FTS5 search:**
- Index rebuild, then search finds inserted notes
- Scoped search: `--in transcript` matches transcript only, not summary; `--in summary` matches summary only
- Unscoped search matches across all columns
- Date filtering combined with search
- Snippet generation includes `[` `]` markers
- Empty results

**`test_formatter.py` — output formatting and TTY detection:**
- Human-friendly formatting for list and search results
- JSON formatting for list and search results
- Quiet mode: bare note IDs
- Error JSON formatting with correct fields (`error`, `message`, `retryable`)
- TTY detection logic (mock `sys.stdout.isatty`)

**`test_cli.py` — CLI argument parsing:**
- Verify defaults and overrides
- `--json` and `--quiet` are mutually exclusive
- `--date-start` / `--date-end` parsing
- `--overwrite-from all` handled distinctly from a date
- `search` parses `--in transcript` and `--in summary`
- `get` requires `note_id` positional arg
- `output --note-id` is repeatable

### What NOT to test

- Do not write integration tests that hit the real Granola API
- Do not mock the full fetch pipeline end-to-end

---

## README.md

The project must include a `README.md` at the root of the repository. This is the primary document for anyone — human or agent — discovering the project.

### Required sections

**1. What this is**
One clear paragraph: a CLI tool for downloading, searching, and exporting Granola meeting notes and transcripts to a local SQLite database. Works with both Personal and Enterprise API keys.

**2. Design philosophy**
Explain the dual-use design:
- Built for humans and AI agents equally. The same commands work at a terminal and in automated pipelines.
- Output adapts to context: human-friendly tables at a terminal, structured JSON when piped. No flags needed — TTY detection handles it. Override with `--json` or `--quiet` for explicit control.
- Summary-first, drill-down-later: `list` → `search` → `get` → `output`. Move from broad to narrow, fetching only what you need at each step.
- Local-first: after the initial `fetch`, all querying happens against the local SQLite database — no API calls. Full-text search via FTS5.
- Errors are structured and include enough context for a script or agent to decide whether to retry or give up.

**3. Quickstart**
Minimal steps:
- Where to put the API key (`~/.config/granola/api_key.txt`)
- `uv run granola_cli.py fetch` to sync
- `uv run granola_cli.py list` to see what's in the local DB
- `uv run granola_cli.py search "topic"` to find a meeting
- `uv run granola_cli.py get <note_id> --transcript` to read a transcript

**4. Commands**
Concise reference for each subcommand (`fetch`, `list`, `get`, `search`, `output`) with the most important flags and one realistic example each. Not a full man page — point to `--help` for details.

**5. Agent usage**
A short section with 2–3 pipeline examples showing how an agent would chain commands. Explain TTY auto-detection, `--json`, and `--quiet`.

**6. How it works**
Brief explanation of: the two-phase fetch (list → get), incremental sync via `updated_after` watermarking, local SQLite storage, FTS5 search index. Explain that `fetch` filters by `updated_at` (to catch edits) while `list`/`search`/`output` filter by `created_at` (to answer "meetings from last week").

**7. Exit codes**
Table of exit codes and their meanings (copy from error contract).

**8. Configuration**
API key location, `--api-base-url`, `--db-path`. Note that both Personal and Enterprise API keys work — the difference is only in what notes are visible.

**9. Development**
How to run tests: `uv run -m pytest`. Debug logging: `--log-level DEBUG`.

### README tone and style
- Technical audience: developers reading on GitHub and agents reading the file for context
- Concise — quickstart fits on one screen, details below
- Code blocks for all commands
- No badges, no marketing language

---

## Implementation details

- Read the API key from the configured file path; strip whitespace/newlines
- Use a `requests.Session` for connection reuse
- Centralize API calls in a client class that accepts `api_base_url` as a constructor parameter
- Centralize rate limiting in a dedicated class
- Centralize DB operations in a repository/storage layer
- Centralize output formatting (TTY detection, JSON, quiet, human, error formatting) in a dedicated module
- Centralize FTS5 search logic in a dedicated module
- Centralize file export logic in a dedicated module
- All logging goes to stderr via Python's `logging` module
- Use transactions for DB writes
- Type hints where helpful
- Reasonable docstrings
- No dead code

---

## Robustness requirements

- Handle null/missing titles
- Handle null transcripts
- Handle null `summary_markdown`
- Handle null `speaker` or null `speaker.source` in transcript entries (treat as `them`)
- Be robust if optional nested fields are absent
- Continue past individual note failures during fetch
- Exit with the correct exit code per the error contract
- Avoid corrupting the DB if interrupted (use transactions)
- Make repeated runs idempotent

---

## Deliverables

1. Python CLI package as described in the code structure section
2. `pyproject.toml` for `uv`, with `requests` as runtime dep and `pytest` as dev dep
3. Unit tests as described above
4. `README.md` as described above

## Quality bar

- Production-quality, not a sketch
- Clear structure and naming
- Type hints where helpful
- Reasonable docstrings
- No dead code
- Minimal dependencies
- Should run cleanly with `uv run`
- All tests pass with `uv run -m pytest`

---

When coding, make sensible decisions rather than asking clarifying questions unless absolutely necessary.
