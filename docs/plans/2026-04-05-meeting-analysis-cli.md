# Meeting Analysis CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone analysis CLI that extracts transcript-derived meeting metrics through `granola_cli.py`, stores analysis results in a separate SQLite database, classifies exchange pairs through local Claude CLI or Codex CLI subprocesses, and produces text, JSON, and HTML chart reports.

**Architecture:** Keep the analysis tool isolated from the main Granola CLI by adding a separate `analysis_cli.py` entrypoint and a new `analysis/` package. Extraction shells out to `uv run granola_cli.py list/get` for normalized `me:`/`them:` transcript text, persistence lives in `analysis.db`, and classification is a local subprocess adapter around Claude CLI or Codex CLI with strict JSON validation before writes.

**Tech Stack:** Python 3.11+, argparse, sqlite3, subprocess, json, statistics, pathlib, requests already present but not required for LLM transport, pytest, ruff

---

## File Structure

- Create: `analysis_cli.py`
- Create: `analysis/__init__.py`
- Create: `analysis/db.py`
- Create: `analysis/util.py`
- Create: `analysis/extract.py`
- Create: `analysis/classify.py`
- Create: `analysis/llm.py`
- Create: `analysis/report.py`
- Create: `tests/test_analysis_cli.py`
- Create: `tests/test_analysis_db.py`
- Create: `tests/test_analysis_extract.py`
- Create: `tests/test_analysis_classify.py`
- Create: `tests/test_analysis_report.py`
- Modify: `pyproject.toml`
- Modify: `docs/progress.md`

## Execution Rules

- The active beads issue is `granola-cli-ivj`.
- After each completed implementation task, append a dated entry to `docs/progress.md` with: what changed, tests run, manual QA run, and the next step.
- Do not commit or push unless explicitly requested by the user.
- Follow TDD strictly: test first, verify failure, implement minimally, verify pass.

### Task 1: CLI entrypoint and parser wiring

**Files:**
- Create: `analysis_cli.py`
- Modify: `pyproject.toml`
- Test: `tests/test_analysis_cli.py`
- Modify: `docs/progress.md`

- [ ] **Step 1: Write the failing parser tests**

```python
from analysis_cli import build_parser


def test_extract_subcommand_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["extract"])
    assert args.command == "extract"
    assert args.from_date is None
    assert args.coding_agent is None


def test_classify_requires_supported_engine() -> None:
    parser = build_parser()
    args = parser.parse_args(["classify", "--engine", "claude"])
    assert args.command == "classify"
    assert args.engine == "claude"


def test_report_flags_parse() -> None:
    parser = build_parser()
    args = parser.parse_args(["report", "--json", "--chart"])
    assert args.command == "report"
    assert args.json is True
    assert args.chart is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/test_analysis_cli.py -v`
Expected: FAIL with `ModuleNotFoundError` or missing `build_parser`

- [ ] **Step 3: Write minimal implementation**

```python
import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Meeting analysis CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract")
    extract_parser.add_argument("--from", dest="from_date")
    extract_parser.add_argument("--coding-agent")

    classify_parser = subparsers.add_parser("classify")
    classify_parser.add_argument("--from", dest="from_date")
    classify_parser.add_argument("--engine", choices=["claude", "codex"], default="claude")
    classify_parser.add_argument("--model")
    classify_parser.add_argument("--reclassify", action="store_true")
    classify_parser.add_argument("--coding-agent")

    report_parser = subparsers.add_parser("report")
    report_parser.add_argument("--from", dest="from_date")
    report_parser.add_argument("--to", dest="to_date")
    report_parser.add_argument("--json", action="store_true")
    report_parser.add_argument("--chart", action="store_true")
    report_parser.add_argument("--coding-agent")
    return parser
```

- [ ] **Step 4: Add the console entrypoint**

```toml
[project.scripts]
granola-cli = "granola_cli:main"
analysis-cli = "analysis_cli:main"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run -m pytest tests/test_analysis_cli.py -v`
Expected: PASS

- [ ] **Step 6: Append progress log entry**

Append to `docs/progress.md`:

```markdown
## 2026-04-05 Task 1
- Issue: granola-cli-ivj
- Changed: added analysis_cli parser scaffold and console script wiring
- Verification: `uv run -m pytest tests/test_analysis_cli.py -v`
- Manual QA: `uv run analysis_cli.py --help`
- Next: add analysis database schema and provenance writes
```

### Task 2: Analysis database schema and run tracking

**Files:**
- Create: `analysis/db.py`
- Create: `tests/test_analysis_db.py`
- Modify: `docs/progress.md`

- [ ] **Step 1: Write the failing database tests**

```python
from analysis.db import AnalysisDatabase


def test_initialize_creates_analysis_tables(tmp_path) -> None:
    db = AnalysisDatabase(str(tmp_path / "analysis.db"))
    db.initialize()
    assert db.has_table("meeting_metrics") is True
    assert db.has_table("exchange_pairs") is True
    assert db.has_table("classifications") is True
    assert db.has_table("analysis_runs") is True


def test_start_and_finish_run_round_trip(tmp_path) -> None:
    db = AnalysisDatabase(str(tmp_path / "analysis.db"))
    db.initialize()
    run_id = db.start_run(command="extract", coding_agent="opencode/gpt-5.4")
    db.finish_run(run_id, notes_processed=2, pairs_classified=0)
    run = db.get_run(run_id)
    assert run["command"] == "extract"
    assert run["notes_processed"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/test_analysis_db.py -v`
Expected: FAIL with missing module or missing `AnalysisDatabase`

- [ ] **Step 3: Write minimal implementation**

```python
class AnalysisDatabase:
    def __init__(self, path: str) -> None:
        self.path = path
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row

    def initialize(self) -> None:
        self.connection.executescript(SCHEMA_SQL)
        self.connection.commit()

    def start_run(self, *, command: str, coding_agent: str | None, classification_model: str | None = None) -> str:
        run_id = str(uuid.uuid4())
        self.connection.execute(
            "INSERT INTO analysis_runs (run_id, command, started_at, coding_agent, classification_model, tool_version) VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, command, utc_now(), coding_agent, classification_model, "0.1.0"),
        )
        self.connection.commit()
        return run_id
```

- [ ] **Step 4: Add idempotent upsert helpers**

Implement methods for:
- `upsert_meeting_metric(row: dict)`
- `replace_exchange_pairs(note_id: str, pairs: list[dict])`
- `upsert_classification(row: dict)`
- `unclassified_pairs(from_date: str | None, limit: int)`

Use `INSERT ... ON CONFLICT DO UPDATE` for idempotency.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run -m pytest tests/test_analysis_db.py -v`
Expected: PASS

- [ ] **Step 6: Append progress log entry**

Append to `docs/progress.md`:

```markdown
## 2026-04-05 Task 2
- Issue: granola-cli-ivj
- Changed: added analysis SQLite schema, run provenance, and idempotent write helpers
- Verification: `uv run -m pytest tests/test_analysis_db.py -v`
- Manual QA: open the temporary DB in a test and confirm expected tables exist
- Next: implement transcript extraction and mechanical metrics
```

### Task 3: Extraction pipeline and mechanical metrics

**Files:**
- Create: `analysis/util.py`
- Create: `analysis/extract.py`
- Create: `tests/test_analysis_extract.py`
- Modify: `docs/progress.md`

- [ ] **Step 1: Write the failing extraction tests**

```python
from analysis.extract import parse_transcript_lines, compute_meeting_metrics, extract_exchange_pairs


def test_parse_transcript_lines_keeps_me_and_them_turns() -> None:
    text = "me: How are we thinking about scope?\nthem: Keep it small\nme: Maybe we start with reporting?\n"
    turns = parse_transcript_lines(text)
    assert turns == [
        {"speaker": "me", "text": "How are we thinking about scope?"},
        {"speaker": "them", "text": "Keep it small"},
        {"speaker": "me", "text": "Maybe we start with reporting?"},
    ]


def test_compute_meeting_metrics_counts_questions_and_hedges() -> None:
    turns = [
        {"speaker": "me", "text": "How are we thinking about scope?"},
        {"speaker": "them", "text": "Keep it small"},
        {"speaker": "me", "text": "Maybe we start with reporting"},
    ]
    metrics = compute_meeting_metrics(turns)
    assert metrics["questions_me"] == 1
    assert metrics["statements_me"] == 1
    assert metrics["words_me"] > 0
    assert metrics["hedges_per_100_words"] > 0


def test_extract_exchange_pairs_builds_them_to_me_pairs() -> None:
    turns = [
        {"speaker": "them", "text": "Why now?"},
        {"speaker": "me", "text": "Because usage is growing."},
    ]
    pairs = extract_exchange_pairs(note_id="n1", created_at="2026-04-05T00:00:00Z", title="Title", turns=turns)
    assert pairs[0]["pair_id"] == "n1:0"
    assert pairs[0]["them_text"] == "Why now?"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/test_analysis_extract.py -v`
Expected: FAIL with missing parse or metric helpers

- [ ] **Step 3: Write minimal implementation**

```python
QUESTION_OPENERS = {"what", "how", "why", "when", "where", "who", "could", "would", "can", "is", "are", "do", "does", "did"}
HEDGES = ["maybe", "perhaps", "i think", "i wonder", "it seems", "possibly", "probably", "might", "could be", "i'm not sure", "i feel like"]


def is_question(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized.endswith("?") or normalized.split(" ", 1)[0] in QUESTION_OPENERS


def hedge_count(text: str) -> int:
    lowered = text.lower()
    return sum(1 for phrase in HEDGES if phrase in lowered)
```

- [ ] **Step 4: Add CLI-backed extraction orchestration**

Implement an `Extractor` that runs:

```python
subprocess.run(["uv", "run", "granola_cli.py", "list", "--quiet"], check=True, capture_output=True, text=True)
subprocess.run(["uv", "run", "granola_cli.py", "get", note_id, "--transcript"], check=True, capture_output=True, text=True)
subprocess.run(["uv", "run", "granola_cli.py", "get", note_id, "--json"], check=True, capture_output=True, text=True)
```

Parse note IDs, transcript lines, and metadata. Filter by `--from` using metadata `created_at`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run -m pytest tests/test_analysis_extract.py -v`
Expected: PASS

- [ ] **Step 6: Manual QA and progress update**

Run: `uv run analysis_cli.py extract --help`
Expected: help output shows `extract` command and flags

Append to `docs/progress.md`:

```markdown
## 2026-04-05 Task 3
- Issue: granola-cli-ivj
- Changed: implemented transcript parsing, metric computation, and CLI-backed extraction helpers
- Verification: `uv run -m pytest tests/test_analysis_extract.py -v`
- Manual QA: `uv run analysis_cli.py extract --help`
- Next: add local Claude/Codex classification pipeline
```

### Task 4: Local Claude CLI / Codex CLI classification

**Files:**
- Create: `analysis/llm.py`
- Create: `analysis/classify.py`
- Create: `tests/test_analysis_classify.py`
- Modify: `docs/progress.md`

- [ ] **Step 1: Write the failing classification tests**

```python
from analysis.classify import build_classification_prompt, classify_pairs


def test_build_classification_prompt_mentions_required_schema() -> None:
    prompt = build_classification_prompt([{"pair_id": "n1:0", "them_text": "No", "me_text": "Why not?"}])
    assert '"pair_id"' in prompt
    assert '"friction"' in prompt
    assert '"response_type"' in prompt


def test_classify_pairs_parses_json_array(monkeypatch) -> None:
    monkeypatch.setattr(
        "analysis.llm.run_model_cli",
        lambda **kwargs: '[{"pair_id":"n1:0","friction":true,"response_type":"question","question_type":"clarifying","topic_initiator":false,"reason":"asked for detail"}]',
    )
    rows = classify_pairs(engine="claude", model="default", pairs=[{"pair_id": "n1:0", "them_text": "No", "me_text": "Why not?"}])
    assert rows[0]["pair_id"] == "n1:0"
    assert rows[0]["response_type"] == "question"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/test_analysis_classify.py -v`
Expected: FAIL with missing classification functions

- [ ] **Step 3: Write minimal implementation**

```python
def run_model_cli(*, engine: str, model: str | None, prompt: str) -> str:
    if engine == "claude":
        command = ["claude"]
        if model:
            command.extend(["--model", model])
        command.extend(["--print", prompt])
    elif engine == "codex":
        command = ["codex"]
        if model:
            command.extend(["--model", model])
        command.extend(["exec", "--json", prompt])
    else:
        raise ValueError(f"Unsupported engine: {engine}")
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return result.stdout.strip()
```

- [ ] **Step 4: Add validation and batching**

Implement:
- `build_classification_prompt(pairs: list[dict]) -> str`
- `validate_classification_rows(rows: list[dict], expected_pair_ids: set[str]) -> list[dict]`
- `classify_unclassified_pairs(db, engine, model, reclassify, from_date)`

Validation rules:
- response must parse as JSON
- top-level value must be a list
- every item must include `pair_id`, `friction`, `response_type`, `question_type`, `topic_initiator`, `reason`
- pair IDs must match the requested batch exactly

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run -m pytest tests/test_analysis_classify.py -v`
Expected: PASS

- [ ] **Step 6: Manual QA and progress update**

Run: `uv run analysis_cli.py classify --help`
Expected: help output shows engine/model/reclassify flags

Append to `docs/progress.md`:

```markdown
## 2026-04-05 Task 4
- Issue: granola-cli-ivj
- Changed: added local Claude/Codex subprocess adapter, prompt builder, and JSON-validated classification writes
- Verification: `uv run -m pytest tests/test_analysis_classify.py -v`
- Manual QA: `uv run analysis_cli.py classify --help`
- Next: aggregate monthly reporting and HTML charts
```

### Task 5: Text, JSON, and chart reporting

**Files:**
- Create: `analysis/report.py`
- Create: `tests/test_analysis_report.py`
- Modify: `docs/progress.md`

- [ ] **Step 1: Write the failing report tests**

```python
from analysis.report import monthly_trends, render_text_report


def test_monthly_trends_groups_by_month() -> None:
    rows = [
        {"created_at": "2026-01-10T00:00:00Z", "speaking_proportion": 0.4},
        {"created_at": "2026-01-20T00:00:00Z", "speaking_proportion": 0.6},
    ]
    report = monthly_trends(rows)
    assert report[0]["month"] == "2026-01"
    assert report[0]["speaking_proportion"] == 0.5


def test_render_text_report_lists_metric_names() -> None:
    text = render_text_report([
        {"month": "2026-01", "speaking_proportion": 0.5, "question_ratio": 0.25}
    ])
    assert "Speaking proportion" in text
    assert "Question ratio" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/test_analysis_report.py -v`
Expected: FAIL with missing report functions

- [ ] **Step 3: Write minimal implementation**

```python
def monthly_trends(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["created_at"][:7]].append(row)
    return [
        {
            "month": month,
            "speaking_proportion": mean(item["speaking_proportion"] for item in items),
        }
        for month, items in sorted(grouped.items())
    ]
```

- [ ] **Step 4: Add chart output**

Implement `write_chart_report(rows, output_dir="charts")` to produce `charts/report.html` containing:
- one `<canvas>` per required metric
- Chart.js via CDN
- monthly series data plus an overlaid linear trend line
- stacked bar data for response type distribution

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run -m pytest tests/test_analysis_report.py -v`
Expected: PASS

- [ ] **Step 6: Manual QA and progress update**

Run: `uv run analysis_cli.py report --help`
Expected: help output shows `--json` and `--chart`

Append to `docs/progress.md`:

```markdown
## 2026-04-05 Task 5
- Issue: granola-cli-ivj
- Changed: added monthly aggregation, text/JSON report rendering, and HTML chart generation
- Verification: `uv run -m pytest tests/test_analysis_report.py -v`
- Manual QA: `uv run analysis_cli.py report --help`
- Next: wire end-to-end command execution and run full verification
```

### Task 6: End-to-end command wiring and verification

**Files:**
- Modify: `analysis_cli.py`
- Modify: `analysis/db.py`
- Modify: `analysis/extract.py`
- Modify: `analysis/classify.py`
- Modify: `analysis/report.py`
- Modify: `tests/test_analysis_cli.py`
- Modify: `docs/progress.md`

- [ ] **Step 1: Write the failing integration tests**

```python
def test_main_runs_extract(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("analysis_cli.run_extract", lambda args: 0)
    assert main(["extract", "--db-path", str(tmp_path / "analysis.db")]) == 0


def test_main_runs_report(monkeypatch) -> None:
    monkeypatch.setattr("analysis_cli.run_report", lambda args: 0)
    assert main(["report", "--json"]) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run -m pytest tests/test_analysis_cli.py -v`
Expected: FAIL until dispatch functions exist

- [ ] **Step 3: Implement dispatch and exits minimally**

```python
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "extract":
        return run_extract(args)
    if args.command == "classify":
        return run_classify(args)
    if args.command == "report":
        return run_report(args)
    raise SystemExit(2)
```

- [ ] **Step 4: Run focused verification**

Run:
- `uv run -m pytest tests/test_analysis_cli.py tests/test_analysis_db.py tests/test_analysis_extract.py tests/test_analysis_classify.py tests/test_analysis_report.py -v`
- `uv run ruff check .`

Expected: all PASS, lint exits 0

- [ ] **Step 5: Run manual QA commands**

Run:
- `uv run analysis_cli.py extract --help`
- `uv run analysis_cli.py classify --help`
- `uv run analysis_cli.py report --help`

Expected: all exit 0 and print command usage with the expected flags

- [ ] **Step 6: Append final progress entry**

Append to `docs/progress.md`:

```markdown
## 2026-04-05 Task 6
- Issue: granola-cli-ivj
- Changed: wired extract/classify/report command execution end-to-end
- Verification: full analysis pytest set + `uv run ruff check .`
- Manual QA: `uv run analysis_cli.py extract --help`, `uv run analysis_cli.py classify --help`, `uv run analysis_cli.py report --help`
- Next: ready for user review or execution
```
