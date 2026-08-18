# Task #145 Phase 1 — Gate + Labeling Web App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `kdb_fts` its first LLM stage — the relevance/topic gate (blueprint §7.2) — and the stdlib review web app (D22) so Joseph can hand-label the 150-article `calibration-p1` batch and we can measure gate precision/recall (blueprint §9 Phase 1 gate).

**Architecture:** One cheap `deepseek-v4-flash` JSON-mode call per `ok`-cleanliness article → salvaged, fail-closed verdict → `gate_verdicts` table (migration 2, resumable per article). Feedback is append-only `feedback/events.jsonl` (the irreplaceable asset, D18) — **no SQLite feedback table in Phase 1** (YAGNI; the ranker consumes it in Phase 3). The review app freezes a batch JSON (the D13 exposure record), serves one static page via `http.server`, and stamps exposure context server-side from the frozen batch on every event write-back.

**Tech Stack:** Python 3.10+ stdlib (`http.server`, `json`, `sqlite3`), `common.call_model` / `common.model_pool` / `common.atomic_io`, one static HTML page (no framework, no build step, no new dependencies — D22).

## Global Constraints

- `kdb_fts` imports `common` **only**; nothing internal imports `kdb_fts` (guarded by `tools/tests/test_package_boundaries.py`).
- Write-boundary guard (same file): `sqlite3.connect`, `mkdir`, and `Path.write_text`/`unlink`/`rename` are allowed **only in `ledger.py`**; all other file writes in `kdb_fts` go through `common.atomic_io` (`atomic_write_text` / `atomic_write_json` — a plain `Name` call, guard-clean). Reads (`read_text`) are unrestricted.
- **No new dependencies.** The server is stdlib-only; the page is one static file.
- Default model `deepseek-v4-flash` via `common.model_pool.resolve_models_json` (D19); overridable per run with `--model`.
- `--dry-run` on `gate` performs LLM calls but commits **nothing** (no verdict rows, no journal — D20).
- Gate is **resumable**: an article with an existing verdict for the same `(model, prompt_version)` is skipped. Re-gating = bump the prompt version.
- Skip-by-rule classes (`media`, `short`, `digest-stub`, `bleed`) are never sent to the LLM (D16). Only `cleanliness = 'ok'` articles are gated in Phase 1.
- Unknown/invalid model output **fails closed**: unknown topic → `other` + both extract flags false (§7.2); unparseable JSON → one retry, then journal `failed` and move on (no verdict row).
- Deterministic sampling everywhere: fixed seeds, explicit sort keys. No wall-clock-dependent selection.
- Run tests with `.venv/bin/python -m pytest` (plain `pytest` uses the system Python and fails on missing deps).
- Commit style: conventional commits with task ref, e.g. `feat(kdb-fts): #145 P1 — ...`. Per-task commits are pre-authorized by plan approval (#143 convention); **push waits for Joseph's word**.

## Blueprint deviations recorded up front (additive only)

1. `gate_verdicts` gains three columns beyond blueprint §6's list: `exploration` (marks the §7.2 5%-of-ineligible sample for Phase 2 extraction — §6 lists no home for it), `input_tokens` / `output_tokens` (so `status` can report cost-to-date without parsing journals), and `rationale` (§7.2's one-line rationale output needs a column). All additive; no §6 column renamed or dropped.
2. Feedback events land in `feedback/events.jsonl` **only** in Phase 1 (D18's irreplaceable asset). The §6 `feedback_events` SQLite mirror table arrives with the ranker that consumes it (Phase 3).
3. Run journal is `runs/<run_id>/journal.jsonl` written **once at run end** via `atomic_write_text` (accumulated in memory). Durability during the run comes from per-article committed `gate_verdicts` rows; the journal is the completion artifact. §5's append-only semantics preserved (the file, once written, is never rewritten).
4. `migrate()` gains explicit transaction wrapping (per-migration `BEGIN…COMMIT` + rollback-on-error) — the Phase 0 final-review note deferred this to "when migration 2 lands"; it lands now.
5. `rebuild_fts` now indexes the **canonical** author name (falling back to raw) instead of always `raw_author` — the Phase 0 final-review Phase-1 note.
6. Author GC (orphaned canonical authors after a yaml repoint): **no GC in Phase 1** — orphans are cosmetic and visible via `kdb-fts status`. This is the §6 "author GC is a Phase-1 decision" decision: defer to post-v1.
7. Cost reality check (2026-08-16 repricing, commit `7b5fc64`): blueprint §11's "<$0.5" gate estimate was computed at the old flash price (0.14/0.28). At the new peak cache-miss rates (0.44/1.32) the full-corpus gate is ≈ **$2–3**. Still trivial; noted so the live gate's reported cost isn't a surprise.
8. Freezer stratification is **topic-only** (surfaced by the final whole-branch review; §9's letter says "stratified by author, date, length, topic guess"). Within each topic stratum, even-spacing over `(author, published_date, article_id)` spreads author and date; **length is genuinely unstratified** — the calibration matrix may carry a length bias. Ratified implicitly by plan approval; Joseph to confirm on review.
9. §7.5's "20% of batch slots reserved for exploration" is absent from freezer v0 — deliberate for `calibration-p1` (calibration wants unbiased stock, and the §7.2 gate-pass exploration sample is already marked in `gate_verdicts`); the quota arrives with queue-kind batches in Phase 4.

---

### Task 1: Migration 2 — `gate_verdicts` + txn-wrapped migrations + state subdirs

**Files:**
- Modify: `kdb_fts/schema.py` (whole file below)
- Modify: `kdb_fts/ledger.py:32-39` (`connect` creates subdirs)
- Test: `kdb_fts/tests/test_schema.py`

**Interfaces:**
- Consumes: existing migration 1 tables.
- Produces: `gate_verdicts` table (see DDL); `schema.SCHEMA_VERSION == 2`; `ledger.connect(root)` guarantees `runs/ feedback/ review/ exports/` exist under the root. Later tasks rely on the exact column names in the DDL.

- [ ] **Step 1: Write the failing tests**

Append to `kdb_fts/tests/test_schema.py`:

```python
import sqlite3

import pytest

from kdb_fts import ledger, schema


def test_migration_2_creates_gate_verdicts(tmp_path):
    conn = ledger.connect(tmp_path)
    assert schema.current_version(conn) == 2
    cols = {r[1] for r in conn.execute("PRAGMA table_info(gate_verdicts)")}
    assert cols == {
        "article_id", "run_id", "topic", "signal",
        "extract_ideas", "extract_lessons", "exploration",
        "confidence", "rationale", "model", "prompt_version",
        "input_tokens", "output_tokens",
    }


def test_migrate_failure_rolls_back_and_keeps_version(tmp_path, monkeypatch):
    """A broken migration must not advance schema_version or leave the DB
    wedged (executescript txn-wrapping, migration-2-era hardening)."""
    conn = ledger.connect(tmp_path)
    broken = "CREATE TABLE boom(x); CREATE TABLE boom(x);"  # dup → error mid-script
    monkeypatch.setitem(schema.MIGRATIONS, 3, broken)
    monkeypatch.setattr(schema, "SCHEMA_VERSION", 3)
    with pytest.raises(sqlite3.OperationalError):
        schema.migrate(conn)
    assert schema.current_version(conn) == 2  # unchanged
    # DB still usable: a well-known table answers a query.
    assert conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 0


def test_connect_creates_state_subdirs(tmp_path):
    ledger.connect(tmp_path)
    for sub in ("runs", "feedback", "review", "exports"):
        assert (tmp_path / sub).is_dir(), sub
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_schema.py -q`
Expected: FAIL — `current_version` returns 1, no `gate_verdicts`, no subdirs.

- [ ] **Step 3: Implement**

Replace `kdb_fts/schema.py` in full:

```python
"""schema — SQLite DDL + numbered migrations for the kdb_fts ledger.

Phase 0 (migration 1): articles / paragraphs / authors / author_aliases /
articles_fts. Phase 1 (migration 2): gate_verdicts (§7.2; additive cols
exploration/rationale/tokens beyond §6's list — plan deviation 1).
Extraction, feedback-mirror, and ranker tables arrive as later migrations
in their own phases (D14: re-extraction never rewrites identity).
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

MIGRATIONS: dict[int, str] = {
    1: """
    CREATE TABLE meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE articles (
        article_id     TEXT PRIMARY KEY,  -- gmail_message_id else 'sha256:'+hash (D17)
        path           TEXT NOT NULL,      -- mutable attribute, never identity
        content_sha256 TEXT NOT NULL,
        title          TEXT,
        raw_author     TEXT,
        author_id      INTEGER REFERENCES authors(author_id),
        published_date TEXT,
        source_url     TEXT,
        content_kind   TEXT,
        word_count     INTEGER NOT NULL,
        cleanliness    TEXT NOT NULL,      -- ok|short|media|digest-stub|bleed|repaired
        first_seen_run TEXT NOT NULL,
        last_seen_run  TEXT NOT NULL
    );
    CREATE TABLE paragraphs (
        article_id   TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
        paragraph_id TEXT NOT NULL,          -- p0001… stable within one content hash
        body         TEXT NOT NULL,
        PRIMARY KEY (article_id, paragraph_id)
    );
    CREATE TABLE authors (
        author_id       INTEGER PRIMARY KEY,
        canonical_name  TEXT NOT NULL UNIQUE,
        publication     TEXT,
        explicit_rating REAL,              -- nullable; wins when set (D9a)
        derived_score   REAL
    );
    CREATE TABLE author_aliases (
        raw_string TEXT PRIMARY KEY,
        author_id  INTEGER NOT NULL REFERENCES authors(author_id)
    );
    CREATE VIRTUAL TABLE articles_fts USING fts5(
        article_id UNINDEXED,
        title,
        author,
        body
    );
    """,
    2: """
    CREATE TABLE gate_verdicts (
        article_id      TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
        run_id          TEXT NOT NULL,
        topic           TEXT NOT NULL,       -- 6 closed labels; unknown fails closed to 'other'
        signal          REAL NOT NULL,       -- 0..1
        extract_ideas   INTEGER NOT NULL,    -- bool
        extract_lessons INTEGER NOT NULL,    -- bool
        exploration     INTEGER NOT NULL DEFAULT 0,  -- §7.2: 5%-of-ineligible sample for Phase 2
        confidence      REAL,                -- nullable, model-reported 0..1
        rationale       TEXT,                -- §7.2 one-liner
        model           TEXT NOT NULL,
        prompt_version  TEXT NOT NULL,
        input_tokens    INTEGER NOT NULL DEFAULT 0,
        output_tokens   INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (article_id, run_id)
    );
    """,
}


def current_version(conn: sqlite3.Connection) -> int:
    """Schema version of an open connection; 0 for a brand-new database."""
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.OperationalError:  # meta table does not exist yet
        return 0
    return int(row[0]) if row else 0


def migrate(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations in order. Idempotent.

    Each migration's DDL runs inside an explicit transaction (a failing
    migration rolls back and never advances schema_version). executescript
    commits any already-open transaction first, so the BEGIN must live
    inside the script text.
    """
    for version in range(current_version(conn) + 1, SCHEMA_VERSION + 1):
        try:
            conn.executescript(f"BEGIN;\n{MIGRATIONS[version]}\nCOMMIT;")
        except sqlite3.Error:
            conn.rollback()
            raise
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
            (str(version),),
        )
        conn.commit()
```

In `kdb_fts/ledger.py`, extend `connect`:

```python
def connect(root: Path | None = None) -> sqlite3.Connection:
    """Open (creating if needed) the ledger under the state root; migrate.

    Also guarantees the §5 state layout subdirs exist — ledger.py is the
    write-guard's mkdir allowlist, so all directory creation lives here.
    """
    root = (root or state.state_root())
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("runs", "feedback", "review", "exports"):
        (root / sub).mkdir(exist_ok=True)
    conn = sqlite3.connect(root / _DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON")
    schema.migrate(conn)
    return conn
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_fts/tests/ tools/tests/test_package_boundaries.py -q`
Expected: PASS (all — including the write-boundary guard; the mkdir stays inside ledger.py).

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/schema.py kdb_fts/ledger.py kdb_fts/tests/test_schema.py
git commit -m "feat(kdb-fts): #145 P1 — migration 2 gate_verdicts, txn-wrapped migrations, state subdirs"
```

---

### Task 2: Canonical author name in the FTS index

**Files:**
- Modify: `kdb_fts/ledger.py:93-103` (`rebuild_fts`)
- Test: `kdb_fts/tests/test_ledger.py`

**Interfaces:**
- Consumes: `authors.canonical_name`, `author_aliases` (Phase 0), `author_map.resolve` (Phase 0).
- Produces: `rebuild_fts` behavior change only — signature unchanged. `ledger.search` unchanged.

- [ ] **Step 1: Write the failing test**

Append to `kdb_fts/tests/test_ledger.py`:

```python
def test_fts_indexes_canonical_author_name(tmp_path):
    """Final-review Phase-1 note: FTS author column is the canonical name
    (falling back to raw when unmapped), not always the raw string."""
    from kdb_fts import author_map, intake

    (tmp_path / "author_map.yaml").write_text(
        'John Q. Puberman: {canonical: "John Puberman"}\n', encoding="utf-8"
    )
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.md").write_text(
        "---\ntitle: Zebra Thesis\nauthor: John Q. Puberman\n---\n\n"
        + "word " * 60, encoding="utf-8")
    conn = ledger.connect(tmp_path)
    intake.run_intake(conn, raw, "run-1", state_root=tmp_path)
    hits = ledger.search(conn, "Puberman")
    assert hits and hits[0]["author"] == "John Puberman"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_ledger.py::test_fts_indexes_canonical_author_name -q`
Expected: FAIL — `author` comes back as `John Q. Puberman`.

- [ ] **Step 3: Implement**

In `kdb_fts/ledger.py`, replace the `INSERT INTO articles_fts` SELECT inside `rebuild_fts`:

```python
def rebuild_fts(conn: sqlite3.Connection) -> None:
    """Full FTS5 repopulation (cheap at 4.2M words; keeps index logic trivial).

    The author column is the CANONICAL name when the alias is mapped
    (falling back to raw_author) — searching a curated name must work.
    """
    conn.execute("DELETE FROM articles_fts")
    conn.execute(
        """INSERT INTO articles_fts(article_id, title, author, body)
           SELECT a.article_id, COALESCE(a.title, ''),
                  COALESCE((SELECT au.canonical_name FROM authors au
                            WHERE au.author_id = a.author_id),
                           a.raw_author, ''),
                  COALESCE((SELECT GROUP_CONCAT(p.body, char(10)||char(10))
                            FROM paragraphs p WHERE p.article_id = a.article_id), '')
           FROM articles a"""
    )
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_fts/tests/ -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/ledger.py kdb_fts/tests/test_ledger.py
git commit -m "fix(kdb-fts): #145 P1 — FTS author column indexes the canonical name"
```

---

### Task 3: Gate prompt + response parsing (pure, no LLM)

**Files:**
- Create: `kdb_fts/prompts/gate_v1.md`
- Create: `kdb_fts/gate.py` (parsing half only — runner lands in Task 4)
- Test: `kdb_fts/tests/test_gate.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure text in → dataclass out).
- Produces (Task 4 and the review freezer rely on these):
  - `gate.TOPICS: tuple[str, ...]` — `("investment", "finance-econ", "geopolitics", "china-econ", "ai-tech", "other")`
  - `gate.GATE_PROMPT_VERSION: str` — `"gate_v1"` (must equal the prompt filename stem)
  - `gate.MAX_BODY_WORDS: int` — `4000`
  - `gate.GateVerdict` dataclass: `topic: str, signal: float, extract_ideas: bool, extract_lessons: bool, confidence: float | None, rationale: str, raw_topic: str | None`
  - `gate.GateParseError(ValueError)`
  - `gate.build_prompt(*, title: str | None, author: str | None, published_date: str | None, body: str) -> str`
  - `gate.parse_verdict(text: str) -> GateVerdict` — raises `GateParseError` on invalid JSON / non-object; fail-closes unknown topics.

- [ ] **Step 1: Write the failing tests**

Create `kdb_fts/tests/test_gate.py`:

```python
import json

import pytest

from kdb_fts import gate


def _payload(**over):
    base = {
        "topic": "investment",
        "signal": 0.8,
        "extract_ideas": True,
        "extract_lessons": False,
        "confidence": 0.9,
        "rationale": "specific thesis with valuation anchor",
    }
    base.update(over)
    return json.dumps(base)


@pytest.mark.parametrize("topic", list(gate.TOPICS))
def test_every_topic_label_roundtrips(topic):
    v = gate.parse_verdict(_payload(topic=topic))
    assert v.topic == topic
    assert v.raw_topic == topic


@pytest.mark.parametrize("topic", list(gate.TOPICS))
@pytest.mark.parametrize("ideas,lessons", [(True, True), (True, False),
                                           (False, True), (False, False)])
def test_all_topic_x_eligibility_combinations(topic, ideas, lessons):
    """§9 Phase-1 fixture matrix: 6 topics × 4 eligibility combos, all parsed."""
    v = gate.parse_verdict(_payload(topic=topic, extract_ideas=ideas,
                                    extract_lessons=lessons))
    assert v.topic == topic
    assert v.extract_ideas is ideas and v.extract_lessons is lessons


def test_unknown_label_fails_closed():
    v = gate.parse_verdict(_payload(topic="sports", extract_ideas=True,
                                    extract_lessons=True))
    assert v.topic == "other"
    assert v.extract_ideas is False and v.extract_lessons is False
    assert v.raw_topic == "sports"  # raw preserved for the journal


def test_invalid_json_raises():
    with pytest.raises(gate.GateParseError):
        gate.parse_verdict("not json {")
    with pytest.raises(gate.GateParseError):
        gate.parse_verdict(json.dumps([1, 2, 3]))  # not an object


def test_salvage_coercion():
    # string booleans fail closed to False; out-of-range signal clamps;
    # missing confidence → None; missing rationale → "".
    v = gate.parse_verdict(_payload(extract_ideas="true", signal=1.7,
                                    confidence=None, rationale=None))
    assert v.extract_ideas is False
    assert v.signal == 1.0
    assert v.confidence is None
    assert v.rationale == ""
    v2 = gate.parse_verdict(_payload(signal=-0.5))
    assert v2.signal == 0.0


def test_unparseable_signal_defaults_zero():
    v = gate.parse_verdict(_payload(signal="high"))
    assert v.signal == 0.0


def test_build_prompt_truncates_body_at_word_cap():
    body = " ".join(f"w{i}" for i in range(gate.MAX_BODY_WORDS + 500))
    p = gate.build_prompt(title="T", author="A", published_date="2026-01-01",
                          body=body)
    assert f"w{gate.MAX_BODY_WORDS - 1}" in p
    assert f"w{gate.MAX_BODY_WORDS}" not in p
    assert "T" in p and "A" in p and "2026-01-01" in p


def test_prompt_version_matches_filename():
    from pathlib import Path

    prompts = Path(__file__).parents[1] / "prompts"
    assert (prompts / f"{gate.GATE_PROMPT_VERSION}.md").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_gate.py -q`
Expected: FAIL — `ModuleNotFoundError: kdb_fts.gate` (collection error).

- [ ] **Step 3: Implement**

Create `kdb_fts/prompts/gate_v1.md`:

```markdown
You are the relevance gate for one investor's personal knowledge system.
Decide what an article IS and whether it deserves deep extraction.

TOPIC (exactly one):
- "investment": a specific, actionable investment idea — a named company/asset
  with a stance, thesis, valuation, or catalyst. Company deep-dives, pitches,
  portfolio moves with reasoning.
- "finance-econ": markets, macro, asset classes, rates, sectors — analysis
  WITHOUT a specific actionable idea.
- "geopolitics": politics, elections, war, policy, regulation with no
  market mechanism as the point of the article.
- "china-econ": China-specific economics, markets, companies, policy.
- "ai-tech": AI/tech industry, models, companies, products.
- "other": anything else, or unsure. When in doubt, choose "other".

SIGNAL (float 0..1): information density for an investor — specificity
(numbers, names, mechanisms), argument quality, conviction backed by
reasoning. Puff pieces and pure opinion score low.

EXTRACT_IDEAS (boolean): true only if the article contains at least one
SPECIFIC investment idea (named company/asset + thesis or stance).
EXTRACT_LESSONS (boolean): true only if the article teaches a reusable
lesson: framework, mental model, process, mistake post-mortem, risk lesson.
Both false is a NORMAL answer — most articles deserve neither.

Return ONE JSON object, no prose:
{"topic": ..., "signal": ..., "extract_ideas": ..., "extract_lessons": ...,
 "confidence": <float 0..1>, "rationale": "<one line>"}

ARTICLE
Title: {{TITLE}}
Author: {{AUTHOR}}
Published: {{PUBLISHED}}
---
{{BODY}}
```

Create `kdb_fts/gate.py`:

```python
"""gate — relevance/topic gate (blueprint §7.2): one cheap LLM call per article.

This module is split in two layers:
  - pure: build_prompt / parse_verdict (this file, top) — no I/O, no LLM
  - runner: run_gate (bottom, Task 4) — DB + call_model + journal

Fail-closed contract: unknown topic → 'other' + both extract flags False;
invalid JSON → GateParseError (the runner retries once, then journals
'failed' and writes NO verdict row).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

TOPICS: tuple[str, ...] = (
    "investment", "finance-econ", "geopolitics", "china-econ", "ai-tech", "other",
)
GATE_PROMPT_VERSION = "gate_v1"
MAX_BODY_WORDS = 4000  # §7.2 truncation (~p95 body length is 4,245 words)

_PROMPT_PATH = Path(__file__).parent / "prompts" / f"{GATE_PROMPT_VERSION}.md"


class GateParseError(ValueError):
    """Response text is not a usable verdict JSON object."""


@dataclass
class GateVerdict:
    topic: str
    signal: float
    extract_ideas: bool
    extract_lessons: bool
    confidence: float | None
    rationale: str
    raw_topic: str | None  # model's verbatim topic (== topic when known)


def build_prompt(*, title: str | None, author: str | None,
                 published_date: str | None, body: str) -> str:
    """Render the versioned prompt template; body truncated to MAX_BODY_WORDS.

    Single-pass sequential str.replace (the #123 P10 rule: substituted
    content is never re-scanned for further placeholders).
    """
    truncated = " ".join(body.split()[:MAX_BODY_WORDS])
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    for token, value in (
        ("{{TITLE}}", title or "(untitled)"),
        ("{{AUTHOR}}", author or "(unknown)"),
        ("{{PUBLISHED}}", published_date or "(unknown)"),
        ("{{BODY}}", truncated),
    ):
        template = template.replace(token, value)
    return template


def _clamp01(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0.0, min(1.0, float(value)))


def parse_verdict(text: str) -> GateVerdict:
    """Parse + salvage one gate response. Raises GateParseError when the
    envelope itself is unusable; field-level problems fail closed."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise GateParseError(f"invalid JSON: {e}") from e
    if not isinstance(data, dict):
        raise GateParseError("response is not a JSON object")
    raw_topic = data.get("topic") if isinstance(data.get("topic"), str) else None
    if raw_topic in TOPICS:
        topic = raw_topic
        extract_ideas = data.get("extract_ideas") is True
        extract_lessons = data.get("extract_lessons") is True
    else:  # unknown/missing label fails closed (§7.2)
        topic = "other"
        extract_ideas = False
        extract_lessons = False
    signal = _clamp01(data.get("signal"))
    rationale = data.get("rationale")
    return GateVerdict(
        topic=topic,
        signal=signal if signal is not None else 0.0,
        extract_ideas=extract_ideas,
        extract_lessons=extract_lessons,
        confidence=_clamp01(data.get("confidence")),
        rationale=str(rationale)[:280] if rationale is not None else "",
        raw_topic=raw_topic,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_gate.py -q`
Expected: PASS (all 11).

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/gate.py kdb_fts/prompts/gate_v1.md kdb_fts/tests/test_gate.py
git commit -m "feat(kdb-fts): #145 P1 — gate prompt v1 + fail-closed verdict parsing"
```

---

### Task 4: Gate runner + `kdb-fts gate` CLI

**Files:**
- Modify: `kdb_fts/gate.py` (append the runner half)
- Modify: `kdb_fts/ledger.py` (append gate access functions)
- Modify: `kdb_fts/cli.py` (add `gate` subcommand)
- Test: `kdb_fts/tests/test_gate.py` (append runner tests)

**Interfaces:**
- Consumes: Task 1 `gate_verdicts` table + subdirs; Task 3 `GateVerdict` / `GateParseError` / `build_prompt` / `GATE_PROMPT_VERSION`; `common.model_pool.resolve_models_json`; `common.call_model.{ModelRequest, call_model}`; `common.atomic_io.atomic_write_text`.
- Produces:
  - `ledger.ungated_articles(conn, model: str, prompt_version: str) -> list[dict]` — rows `{article_id, title, author, published_date, body}` for `cleanliness='ok'` articles lacking a verdict at `(model, prompt_version)`; `author` is canonical-else-raw; `body` is the paragraphs joined with `\n\n`. Order: `article_id` ASC (deterministic).
  - `ledger.insert_gate_verdict(conn, *, article_id, run_id, verdict: GateVerdict-import-side-stepped, model, prompt_version, exploration, input_tokens, output_tokens) -> None` — **to avoid ledger importing gate (layering), pass primitive fields**: exact signature below.
  - `ledger.latest_verdicts(conn) -> list[dict]` — latest-run verdict per article_id, all columns as dict keys.
  - `ledger.mark_exploration(conn, run_id: str, article_ids: list[str]) -> None`
  - `gate.run_gate(conn, *, state_root: Path, run_id: str, model_id: str = "deepseek-v4-flash", max_n: int | None = None, dry_run: bool = False, call_fn=call_model) -> dict` — stats: `{gated, failed, skipped, by_topic, input_tokens, output_tokens, cost_usd, exploration_marked}`.

- [ ] **Step 1: Write the failing tests**

Append to `kdb_fts/tests/test_gate.py`:

```python
from common.call_model import ModelResponse

from kdb_fts import ledger


def _seed_articles(conn, tmp_path, n=6):
    """n ok-cleanliness articles a0..a(n-1), authored round-robin by a{i}%2."""
    from kdb_fts import intake

    raw = tmp_path / "raw"
    raw.mkdir(exist_ok=True)
    for i in range(n):
        (raw / f"a{i}.md").write_text(
            f"---\ntitle: T{i}\nauthor: Au{i % 2}\ngmail_message_id: gid{i}\n---\n\n"
            + f"topic {i} " * 60, encoding="utf-8")
    intake.run_intake(conn, raw, "seed-run", state_root=tmp_path)


def _fake_call_factory(payloads):
    """payloads: dict article-title-suffix → response text. Returns a
    call_fn(req) that picks the payload by the title line in the prompt."""
    calls = []

    def _call(req):
        calls.append(req)
        for key, text in payloads.items():
            if f"Title: {key}" in req.prompt:
                return ModelResponse(text=text, input_tokens=100,
                                     output_tokens=20, latency_ms=5,
                                     model=req.model, provider=req.provider)
        raise AssertionError(f"no payload for prompt: {req.prompt[:200]}")

    _call.calls = calls
    return _call


def test_run_gate_happy_path_and_resume(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=4)
    payloads = {f"T{i}": json.dumps({
        "topic": "investment", "signal": 0.5 + i / 10,
        "extract_ideas": True, "extract_lessons": False,
        "confidence": 0.9, "rationale": f"r{i}"}) for i in range(4)}
    fake = _fake_call_factory(payloads)
    stats = gate.run_gate(conn, state_root=tmp_path, run_id="run-1",
                          model_id="deepseek-v4-flash", call_fn=fake)
    assert stats["gated"] == 4 and stats["failed"] == 0
    assert stats["input_tokens"] == 400 and stats["output_tokens"] == 80
    assert stats["cost_usd"] > 0
    assert stats["by_topic"] == {"investment": 4}
    # 4 eligible (extract_ideas=true) → no ineligible → no exploration marks.
    assert stats["exploration_marked"] == 0
    rows = ledger.latest_verdicts(conn)
    assert len(rows) == 4 and rows[0]["model"] == "deepseek-v4-flash"
    assert rows[0]["prompt_version"] == gate.GATE_PROMPT_VERSION
    # journal written under runs/
    journal = (tmp_path / "runs" / "run-1" / "journal.jsonl")
    assert journal.exists() and "gated" in journal.read_text()
    # resume: second run with same model+prompt version gates nothing.
    stats2 = gate.run_gate(conn, state_root=tmp_path, run_id="run-2",
                           model_id="deepseek-v4-flash", call_fn=fake)
    assert stats2["gated"] == 0 and stats2["skipped"] == 4


def test_run_gate_retry_then_fail_closed(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=2)
    payloads = {"T0": "garbage{",  # invalid JSON both attempts
                "T1": json.dumps({"topic": "sports", "signal": 0.9,
                                  "extract_ideas": True, "extract_lessons": True,
                                  "confidence": 1.0, "rationale": "x"})}
    fake = _fake_call_factory(payloads)
    stats = gate.run_gate(conn, state_root=tmp_path, run_id="run-1",
                          model_id="deepseek-v4-flash", call_fn=fake)
    assert stats["failed"] == 1 and stats["gated"] == 1
    rows = {r["article_id"]: r for r in ledger.latest_verdicts(conn)}
    assert len(rows) == 1  # the failed one left NO verdict row
    v = next(iter(rows.values()))
    assert v["topic"] == "other" and v["extract_ideas"] == 0  # fail-closed


def test_exploration_sample_marks_five_percent_min_ten(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=6)
    payloads = {f"T{i}": json.dumps({
        "topic": "geopolitics", "signal": 0.1,
        "extract_ideas": False, "extract_lessons": False,
        "confidence": 0.5, "rationale": "politics"}) for i in range(6)}
    stats = gate.run_gate(conn, state_root=tmp_path, run_id="run-1",
                          model_id="deepseek-v4-flash",
                          call_fn=_fake_call_factory(payloads))
    # 6 ineligible → min-10 rule caps at population: all 6 marked.
    assert stats["exploration_marked"] == 6
    rows = ledger.latest_verdicts(conn)
    assert all(r["exploration"] == 1 for r in rows)


def test_dry_run_commits_nothing(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=2)
    payloads = {f"T{i}": json.dumps({
        "topic": "other", "signal": 0.2, "extract_ideas": False,
        "extract_lessons": False, "confidence": 0.5,
        "rationale": "x"}) for i in range(2)}
    stats = gate.run_gate(conn, state_root=tmp_path, run_id="run-dry",
                          model_id="deepseek-v4-flash", dry_run=True,
                          call_fn=_fake_call_factory(payloads))
    assert stats["gated"] == 2  # calls happened
    assert ledger.latest_verdicts(conn) == []
    assert not (tmp_path / "runs" / "run-dry").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_gate.py -q`
Expected: FAIL — `AttributeError: module 'kdb_fts.gate' has no attribute 'run_gate'` / `ledger.ungated_articles` missing.

- [ ] **Step 3: Implement**

Append to `kdb_fts/ledger.py`:

```python
def ungated_articles(conn: sqlite3.Connection, model: str,
                     prompt_version: str) -> list[dict]:
    """ok-cleanliness articles lacking a verdict at (model, prompt_version).

    author = canonical name when mapped, else raw string. Deterministic
    order (article_id ASC) so --max N slicing is stable across runs.
    """
    rows = conn.execute(
        """SELECT a.article_id, a.title,
                  COALESCE(au.canonical_name, a.raw_author) AS author,
                  a.published_date,
                  (SELECT GROUP_CONCAT(p.body, char(10)||char(10))
                   FROM paragraphs p WHERE p.article_id = a.article_id) AS body
           FROM articles a
           LEFT JOIN authors au ON au.author_id = a.author_id
           WHERE a.cleanliness = 'ok'
             AND NOT EXISTS (
                 SELECT 1 FROM gate_verdicts gv
                 WHERE gv.article_id = a.article_id
                   AND gv.model = ? AND gv.prompt_version = ?)
           ORDER BY a.article_id""",
        (model, prompt_version),
    ).fetchall()
    return [
        {"article_id": r[0], "title": r[1], "author": r[2],
         "published_date": r[3], "body": r[4] or ""}
        for r in rows
    ]


def insert_gate_verdict(
    conn: sqlite3.Connection, *, article_id: str, run_id: str, topic: str,
    signal: float, extract_ideas: bool, extract_lessons: bool,
    exploration: bool, confidence: float | None, rationale: str,
    model: str, prompt_version: str, input_tokens: int, output_tokens: int,
) -> None:
    """One verdict row per (article, run); commits immediately (resume-safe)."""
    conn.execute(
        """INSERT OR REPLACE INTO gate_verdicts
           (article_id, run_id, topic, signal, extract_ideas, extract_lessons,
            exploration, confidence, rationale, model, prompt_version,
            input_tokens, output_tokens)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (article_id, run_id, topic, signal, int(extract_ideas),
         int(extract_lessons), int(exploration), confidence, rationale,
         model, prompt_version, input_tokens, output_tokens),
    )
    conn.commit()


def latest_verdicts(conn: sqlite3.Connection) -> list[dict]:
    """The routing view: each article's verdict from its latest run."""
    rows = conn.execute(
        """SELECT gv.article_id, gv.run_id, gv.topic, gv.signal,
                  gv.extract_ideas, gv.extract_lessons, gv.exploration,
                  gv.confidence, gv.rationale, gv.model, gv.prompt_version,
                  gv.input_tokens, gv.output_tokens
           FROM gate_verdicts gv
           JOIN (SELECT article_id, MAX(run_id) AS mr FROM gate_verdicts
                 GROUP BY article_id) t
             ON t.article_id = gv.article_id AND t.mr = gv.run_id
           ORDER BY gv.article_id"""
    ).fetchall()
    cols = ("article_id", "run_id", "topic", "signal", "extract_ideas",
            "extract_lessons", "exploration", "confidence", "rationale",
            "model", "prompt_version", "input_tokens", "output_tokens")
    return [dict(zip(cols, r)) for r in rows]


def mark_exploration(conn: sqlite3.Connection, run_id: str,
                     article_ids: list[str]) -> None:
    conn.executemany(
        "UPDATE gate_verdicts SET exploration = 1 WHERE article_id = ? AND run_id = ?",
        [(a, run_id) for a in article_ids],
    )
    conn.commit()
```

Append to `kdb_fts/gate.py`:

```python
# --- runner half (Task 4): DB + call_model + journal ------------------------

import math
from datetime import datetime

from common.atomic_io import atomic_write_text
from common.call_model import ModelRequest, ModelResponse, call_model
from common.model_pool import resolve_models_json

from kdb_fts import ledger

_GATE_MAX_OUTPUT_TOKENS = 1024
_EXPLORATION_FRACTION = 0.05  # §7.2: of the ineligible set
_EXPLORATION_MIN = 10


def _exploration_sample(ineligible: list[dict]) -> list[str]:
    """5% (min 10, capped at population) of ineligible articles, stratified
    by author. Deterministic: groups sorted by (-size, author), ids sorted,
    round-robin."""
    k = min(len(ineligible),
            max(_EXPLORATION_MIN, math.ceil(_EXPLORATION_FRACTION * len(ineligible))))
    by_author: dict[str, list[str]] = {}
    for row in ineligible:
        by_author.setdefault(row["author"] or "(unknown)", []).append(row["article_id"])
    groups = [sorted(ids) for _, ids in
              sorted(by_author.items(), key=lambda kv: (-len(kv[1]), kv[0]))]
    picked: list[str] = []
    idx = 0
    while len(picked) < k and any(groups):
        group = groups[idx % len(groups)]
        if group:
            picked.append(group.pop(0))
        idx += 1
    return picked


def _call_once(spec, prompt: str, call_fn) -> ModelResponse:
    return call_fn(ModelRequest(
        provider=spec.provider, model=spec.model, prompt=prompt,
        json_mode=True, max_tokens=_GATE_MAX_OUTPUT_TOKENS,
        temperature=spec.temperature, extra_body=spec.extra_body,
        use_completion_tokens=spec.use_completion_tokens, route=spec.route,
    ))


def run_gate(conn, *, state_root: Path, run_id: str,
             model_id: str = "deepseek-v4-flash", max_n: int | None = None,
             dry_run: bool = False, call_fn=call_model) -> dict:
    """Gate every ungated ok article; one verdict row per call; resumable.

    dry_run: LLM calls happen, NOTHING is committed (D20) — no verdict
    rows, no exploration marks, no journal.
    """
    spec = resolve_models_json(model_id)
    todo = ledger.ungated_articles(conn, spec.model, GATE_PROMPT_VERSION)
    skipped = conn.execute(
        "SELECT COUNT(*) FROM gate_verdicts WHERE model = ? AND prompt_version = ?",
        (spec.model, GATE_PROMPT_VERSION),
    ).fetchone()[0]
    if max_n is not None:
        todo = todo[:max_n]

    stats = {"gated": 0, "failed": 0, "skipped": skipped, "by_topic": {},
             "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
             "exploration_marked": 0}
    journal: list[dict] = []
    ineligible: list[dict] = []
    gated_ids: list[str] = []

    for row in todo:
        prompt = build_prompt(title=row["title"], author=row["author"],
                              published_date=row["published_date"],
                              body=row["body"])
        verdict = None
        resp = None
        for _attempt in range(2):  # initial + one retry
            resp = _call_once(spec, prompt, call_fn)
            stats["input_tokens"] += resp.input_tokens
            stats["output_tokens"] += resp.output_tokens
            try:
                verdict = parse_verdict(resp.text)
                break
            except GateParseError:
                continue
        if verdict is None:
            stats["failed"] += 1
            journal.append({"article_id": row["article_id"], "status": "failed"})
            continue
        stats["gated"] += 1
        stats["by_topic"][verdict.topic] = stats["by_topic"].get(verdict.topic, 0) + 1
        journal.append({"article_id": row["article_id"], "status": "gated",
                        "topic": verdict.topic, "signal": verdict.signal,
                        "raw_topic": verdict.raw_topic})
        gated_ids.append(row["article_id"])
        if not (verdict.extract_ideas or verdict.extract_lessons):
            ineligible.append(row)
        if not dry_run:
            ledger.insert_gate_verdict(
                conn, article_id=row["article_id"], run_id=run_id,
                topic=verdict.topic, signal=verdict.signal,
                extract_ideas=verdict.extract_ideas,
                extract_lessons=verdict.extract_lessons, exploration=False,
                confidence=verdict.confidence, rationale=verdict.rationale,
                model=spec.model, prompt_version=GATE_PROMPT_VERSION,
                input_tokens=resp.input_tokens, output_tokens=resp.output_tokens)

    marks = _exploration_sample(ineligible) if ineligible else []
    stats["exploration_marked"] = len(marks)
    stats["cost_usd"] = (spec.price_in / 1e6 * stats["input_tokens"]
                         + spec.price_out / 1e6 * stats["output_tokens"])
    if not dry_run:
        if marks:
            ledger.mark_exploration(conn, run_id, marks)
        journal.append({"summary": True, **stats,
                        "model": spec.model,
                        "prompt_version": GATE_PROMPT_VERSION,
                        "finished": datetime.now().astimezone().isoformat(timespec="seconds")})
        run_dir = Path(state_root) / "runs" / run_id
        run_dir.mkdir(exist_ok=True)  # state_root/runs itself exists via connect()
        atomic_write_text(
            run_dir / "journal.jsonl",
            "".join(json.dumps(line, sort_keys=True) + "\n" for line in journal),
        )
    return stats
```

Wait — the write guard bans `mkdir` outside `ledger.py`. The `run_dir.mkdir` above **violates R3**. Fix in implementation: create the run dir without mkdir by having `ledger` own it. Add to `kdb_fts/ledger.py` (append with the other functions):

```python
def run_dir_for(root: Path, run_id: str) -> Path:
    """Create (idempotently) and return runs/<run_id> — mkdir lives only here
    (write-guard R3)."""
    path = Path(root) / "runs" / run_id
    path.mkdir(exist_ok=True)
    return path
```

and in `run_gate` replace the two `run_dir` lines with:

```python
        run_dir = ledger.run_dir_for(Path(state_root), run_id)
```

In `kdb_fts/cli.py`: add the import (`from kdb_fts import gate` — extend the existing import line) and the subcommand:

```python
def _cmd_gate(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    run_id = datetime.now().astimezone().isoformat(timespec="seconds")
    stats = gate.run_gate(
        conn, state_root=root, run_id=run_id, model_id=args.model,
        max_n=args.max, dry_run=args.dry_run,
    )
    tag = "DRY-RUN " if args.dry_run else ""
    print(f"{tag}gated={stats['gated']} failed={stats['failed']} skipped={stats['skipped']}")
    print(f"topics: {stats['by_topic']}")
    print(f"exploration_marked={stats['exploration_marked']}")
    print(f"tokens in={stats['input_tokens']} out={stats['output_tokens']} "
          f"cost=${stats['cost_usd']:.4f}")
    return 0
```

and in `main()`, after the `status` parser block:

```python
    p = sub.add_parser("gate", help="one LLM verdict per ok article (§7.2); resumable")
    p.add_argument("--max", type=int, default=None, dest="max")
    p.add_argument("--model", default="deepseek-v4-flash")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_gate)
```

Also extend `_cmd_status` (blueprint §8: counts by verdict/topic, cost to date). Append before `return 0`:

```python
    rows = conn.execute(
        """SELECT model, prompt_version, COUNT(*), SUM(input_tokens), SUM(output_tokens)
           FROM gate_verdicts GROUP BY 1, 2 ORDER BY 1"""
    ).fetchall()
    if rows:
        from common.model_pool import resolve_models_json
        print("gate verdicts:")
        total_cost = 0.0
        for model, pv, n, tin, tout in rows:
            spec = resolve_models_json(model)
            cost = spec.price_in / 1e6 * (tin or 0) + spec.price_out / 1e6 * (tout or 0)
            total_cost += cost
            print(f"  {model} {pv}: {n} verdicts, {tin or 0}+{tout or 0} tok, ${cost:.4f}")
        print(f"  cost to date: ${total_cost:.4f}")
        for topic, n in conn.execute(
            "SELECT topic, COUNT(*) FROM gate_verdicts GROUP BY 1 ORDER BY 2 DESC"
        ):
            print(f"  topic {topic}: {n}")
```

(Note: the status extension is exercised indirectly — the CLI smoke test below covers the print path; per-model cost resolution uses the pool default prices.)

Append a CLI smoke test to `kdb_fts/tests/test_gate.py`:

```python
def test_cli_gate_dry_run(tmp_path, monkeypatch, capsys):
    from kdb_fts import cli

    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=1)
    conn.close()
    fake = _fake_call_factory({"T0": json.dumps({
        "topic": "other", "signal": 0.1, "extract_ideas": False,
        "extract_lessons": False, "confidence": 0.5, "rationale": "x"})})
    monkeypatch.setattr(gate, "call_model", fake)
    rc = cli.main(["gate", "--state", str(tmp_path), "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out and "gated=1" in out
```

(`gate.run_gate` defaults `call_fn=call_model` — the default is bound at def time, so the monkeypatch above only works if `run_gate`'s default is evaluated per call. To keep the smoke test honest, in `_cmd_gate` pass `call_fn=gate.call_model` explicitly:

```python
    stats = gate.run_gate(
        conn, state_root=root, run_id=run_id, model_id=args.model,
        max_n=args.max, dry_run=args.dry_run, call_fn=gate.call_model,
    )
```

This reads the module attribute at call time, so `monkeypatch.setattr(gate, "call_model", fake)` takes effect.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_fts/tests/ tools/tests/test_package_boundaries.py -q`
Expected: PASS (all — write guard included; `mkdir` appears only in `ledger.py`).

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/gate.py kdb_fts/ledger.py kdb_fts/cli.py kdb_fts/tests/test_gate.py
git commit -m "feat(kdb-fts): #145 P1 — gate runner (resume, retry, exploration marks, dry-run) + kdb-fts gate"
```

---

### Task 5: `feedback.py` — immutable event log + `kdb-fts feedback` CLI

**Files:**
- Create: `kdb_fts/feedback.py`
- Modify: `kdb_fts/cli.py` (add `feedback` subcommand)
- Test: `kdb_fts/tests/test_feedback.py`

**Interfaces:**
- Consumes: `common.atomic_io.atomic_write_text`; `feedback/` subdir from Task 1.
- Produces (review.py in Task 7 and calibrate.py in Task 8 rely on these):
  - `feedback.ACTIONS: frozenset[str]` — `{"strong","interesting","weak","noise","accept","reject","helpful","not-helpful","save","skip","wrong-extraction","promote-to-extract"}` (§6 vocabulary)
  - `feedback.TARGET_TYPES: frozenset[str]` — `{"article","idea","lesson","author"}`
  - `feedback.append_event(root: Path, *, action: str, target_type: str, target_id: str, reason_text: str | None = None, reason_tags: list[str] | None = None, ranker_version: str | None = None, score_shown: float | None = None, position_shown: int | None = None, batch_id: str | None = None, exploration: bool = False) -> dict` — validates closed sets, stamps `ts`, appends one JSON line to `<root>/feedback/events.jsonl` (read + atomic rewrite; crash-safe and guard-clean), returns the event.
  - `feedback.load_events(root: Path, *, batch_id: str | None = None) -> list[dict]`
  - **No update/delete functions exist, by design (D13/D18).**

- [ ] **Step 1: Write the failing tests**

Create `kdb_fts/tests/test_feedback.py`:

```python
import json

import pytest

from kdb_fts import feedback, ledger


def test_append_and_load_roundtrip(tmp_path):
    ledger.connect(tmp_path)  # creates feedback/ subdir
    e1 = feedback.append_event(tmp_path, action="strong", target_type="article",
                               target_id="a1", reason_text="great thesis",
                               batch_id="calibration-p1", position_shown=0,
                               score_shown=0.8)
    e2 = feedback.append_event(tmp_path, action="noise", target_type="article",
                               target_id="a2", batch_id="calibration-p1",
                               position_shown=1)
    assert e1["ts"] and e1["action"] == "strong"
    events = feedback.load_events(tmp_path)
    assert [e["target_id"] for e in events] == ["a1", "a2"]
    assert feedback.load_events(tmp_path, batch_id="calibration-p1") == events
    assert feedback.load_events(tmp_path, batch_id="nope") == []
    # file is real JSONL, one event per line
    lines = (tmp_path / "feedback" / "events.jsonl").read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["action"] == "strong"


def test_closed_sets_enforced(tmp_path):
    ledger.connect(tmp_path)
    with pytest.raises(ValueError):
        feedback.append_event(tmp_path, action="amazing", target_type="article",
                              target_id="a1")
    with pytest.raises(ValueError):
        feedback.append_event(tmp_path, action="strong", target_type="page",
                              target_id="a1")


def test_no_mutation_api_and_append_only_file(tmp_path):
    ledger.connect(tmp_path)
    feedback.append_event(tmp_path, action="weak", target_type="article",
                          target_id="a1")
    assert not hasattr(feedback, "update_event")
    assert not hasattr(feedback, "delete_event")
    first = (tmp_path / "feedback" / "events.jsonl").read_text()
    feedback.append_event(tmp_path, action="strong", target_type="article",
                          target_id="a1")  # same target re-labeled = new event
    second = (tmp_path / "feedback" / "events.jsonl").read_text()
    assert second.startswith(first)  # prior bytes untouched
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_feedback.py -q`
Expected: FAIL — `ModuleNotFoundError: kdb_fts.feedback`.

- [ ] **Step 3: Implement**

Create `kdb_fts/feedback.py`:

```python
"""feedback — Joseph's immutable event log (D13/D18): the irreplaceable asset.

One JSONL file: <state_root>/feedback/events.jsonl. Append = read + atomic
rewrite via common.atomic_io (crash-safe, write-guard-clean; fine at
Phase-1 scale — thousands of events, low MB). There is deliberately NO
update or delete path. The SQLite mirror table arrives with the ranker
that consumes it (Phase 3; plan deviation 2).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from common.atomic_io import atomic_write_text

ACTIONS = frozenset({
    "strong", "interesting", "weak", "noise",          # article buckets ≙ 3/2/1/0
    "accept", "reject",                                 # ideas (D21)
    "helpful", "not-helpful",                           # lessons (D21)
    "save", "skip", "wrong-extraction", "promote-to-extract",
})
TARGET_TYPES = frozenset({"article", "idea", "lesson", "author"})

_EVENTS_NAME = "events.jsonl"


def _events_path(root: Path) -> Path:
    return Path(root) / "feedback" / _EVENTS_NAME


def append_event(root: Path, *, action: str, target_type: str, target_id: str,
                 reason_text: str | None = None,
                 reason_tags: list[str] | None = None,
                 ranker_version: str | None = None,
                 score_shown: float | None = None,
                 position_shown: int | None = None,
                 batch_id: str | None = None,
                 exploration: bool = False) -> dict:
    """Validate + stamp + append one immutable event. Returns the event."""
    if action not in ACTIONS:
        raise ValueError(f"unknown feedback action {action!r} (allowed: {sorted(ACTIONS)})")
    if target_type not in TARGET_TYPES:
        raise ValueError(f"unknown target_type {target_type!r}")
    event = {
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "reason_text": reason_text,
        "reason_tags": reason_tags,
        "ranker_version": ranker_version,
        "score_shown": score_shown,
        "position_shown": position_shown,
        "batch_id": batch_id,
        "exploration": bool(exploration),
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    path = _events_path(root)
    prior = path.read_text(encoding="utf-8") if path.exists() else ""
    atomic_write_text(path, prior + json.dumps(event, sort_keys=True) + "\n")
    return event


def load_events(root: Path, *, batch_id: str | None = None) -> list[dict]:
    path = _events_path(root)
    if not path.exists():
        return []
    events = [json.loads(line) for line in
              path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if batch_id is not None:
        events = [e for e in events if e.get("batch_id") == batch_id]
    return events
```

In `kdb_fts/cli.py` — extend the import line with `feedback`, and add:

```python
def _cmd_feedback(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    ledger.connect(root)  # guarantees feedback/ exists
    event = feedback.append_event(
        root, action=args.action, target_type=args.target_type,
        target_id=args.target_id, reason_text=args.reason,
        reason_tags=args.tags.split(",") if args.tags else None,
    )
    print(f"event appended: {event['action']} {event['target_type']}:{event['target_id']} @ {event['ts']}")
    return 0
```

```python
    p = sub.add_parser("feedback", help="append one immutable event (scripting path)")
    p.add_argument("target_type", choices=sorted(feedback.TARGET_TYPES))
    p.add_argument("target_id")
    p.add_argument("action", choices=sorted(feedback.ACTIONS))
    p.add_argument("--reason", default=None)
    p.add_argument("--tags", default=None, help="comma-separated")
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_feedback)
```

Note this orders args `target_type target_id action` (argparse positional order); blueprint §8's `kdb-fts feedback <target> <action>` shorthand is realized as `kdb-fts feedback article <id> strong [--reason ...]`.

Add a CLI test to `test_feedback.py`:

```python
def test_cli_feedback_appends(tmp_path, capsys):
    from kdb_fts import cli

    rc = cli.main(["feedback", "article", "a9", "interesting",
                   "--reason", "solid", "--state", str(tmp_path)])
    assert rc == 0
    events = feedback.load_events(tmp_path)
    assert len(events) == 1 and events[0]["reason_text"] == "solid"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_feedback.py -q`
Expected: PASS (all 4).

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/feedback.py kdb_fts/cli.py kdb_fts/tests/test_feedback.py
git commit -m "feat(kdb-fts): #145 P1 — immutable feedback event log + kdb-fts feedback"
```

---

### Task 6: `review.py` batch freezer (calibration stratified sampling)

**Files:**
- Create: `kdb_fts/review.py` (freezer half; server lands in Task 7)
- Test: `kdb_fts/tests/test_review.py`

**Interfaces:**
- Consumes: `ledger.latest_verdicts` (Task 4), `articles`/`paragraphs` via `ledger`, `common.atomic_io.atomic_write_json`.
- Produces:
  - `review.freeze_batch(conn, root: Path, *, batch_id: str, kind: str = "calibration", n: int = 150) -> Path` — deterministic stratified sample over **gated** articles; writes `<root>/review/<batch_id>.json`; **refuses to overwrite** (frozen = immutable exposure record, D13).
  - Frozen JSON shape (Task 7's server and the page rely on it):

```json
{
  "batch_id": "calibration-p1",
  "kind": "calibration",
  "created": "<iso ts>",
  "ranker_version": null,
  "items": [
    {"article_id": "...", "title": "...", "author": "...", "published_date": "...",
     "topic": "...", "signal": 0.0, "position": 0, "exploration": false,
     "body": "..."}
  ]
}
```

- [ ] **Step 1: Write the failing tests**

Create `kdb_fts/tests/test_review.py`:

```python
import json

import pytest

from kdb_fts import ledger, review
from kdb_fts.tests.test_gate import _seed_articles


def _gate_all(conn, tmp_path):
    """Give every seeded article a verdict without an LLM: 3 topics cycling."""
    topics = ["investment", "finance-econ", "geopolitics",
              "china-econ", "ai-tech", "other"]
    for i, row in enumerate(conn.execute(
            "SELECT article_id FROM articles ORDER BY article_id")):
        ledger.insert_gate_verdict(
            conn, article_id=row[0], run_id="r1", topic=topics[i % 6],
            signal=0.1 * (i % 10), extract_ideas=(i % 6 == 0),
            extract_lessons=False, exploration=False, confidence=0.5,
            rationale="t", model="m", prompt_version="gate_v1",
            input_tokens=1, output_tokens=1)


def test_freeze_batch_stratified_and_frozen(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=12)
    _gate_all(conn, tmp_path)
    path = review.freeze_batch(conn, tmp_path, batch_id="calibration-p1", n=9)
    batch = json.loads(path.read_text())
    assert batch["batch_id"] == "calibration-p1"
    assert batch["ranker_version"] is None
    assert len(batch["items"]) == 9
    topics = {it["topic"] for it in batch["items"]}
    assert len(topics) >= 4  # stratified across topic guesses, not top-N
    positions = [it["position"] for it in batch["items"]]
    assert positions == list(range(9))
    assert all(it["body"] for it in batch["items"])  # full body for labeling
    # determinism: same inputs → same article_ids
    ids1 = [it["article_id"] for it in batch["items"]]
    path2 = review.freeze_batch(conn, tmp_path, batch_id="calibration-p2", n=9)
    ids2 = [it["article_id"] for it in json.loads(path2.read_text())["items"]]
    assert ids1 == ids2


def test_freeze_refuses_overwrite(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=4)
    _gate_all(conn, tmp_path)
    review.freeze_batch(conn, tmp_path, batch_id="b1", n=2)
    with pytest.raises(FileExistsError):
        review.freeze_batch(conn, tmp_path, batch_id="b1", n=2)


def test_freeze_rejects_unknown_kind(tmp_path):
    conn = ledger.connect(tmp_path)
    with pytest.raises(ValueError):
        review.freeze_batch(conn, tmp_path, batch_id="b1", kind="research")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_review.py -q`
Expected: FAIL — `ModuleNotFoundError: kdb_fts.review`.

- [ ] **Step 3: Implement**

Create `kdb_fts/review.py`:

```python
"""review — batch freezer + local labeling web app (D22, §7.5).

Freezer (this file, top): pick a deterministic stratified sample of gated
articles and freeze it to review/<batch_id>.json — the frozen payload IS
the D13 exposure record (positions/scores shown are stamped from it
server-side on every event). A frozen batch is never overwritten.

Server (Task 7, bottom): stdlib http.server serving one static page;
POST /event writes back through feedback.py and nothing else.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from common.atomic_io import atomic_write_json

from kdb_fts import ledger

_KINDS = frozenset({"calibration"})  # v0: calibration only; queue kinds land
                                     # with the ranker (Phase 3+)
_MIN_PER_STRATUM = 2


def _stratified_sample(rows: list[dict], n: int) -> list[dict]:
    """Proportional-by-topic allocation (min _MIN_PER_STRATUM where stock
    allows), even-spacing within each topic ordered by
    (author, published_date, article_id). Deterministic."""
    by_topic: dict[str, list[dict]] = {}
    for r in rows:
        by_topic.setdefault(r["topic"], []).append(r)
    for group in by_topic.values():
        group.sort(key=lambda r: (r["author"] or "", r["published_date"] or "",
                                  r["article_id"]))
    total = len(rows)
    picked: list[dict] = []
    for topic in sorted(by_topic):
        group = by_topic[topic]
        k = round(n * len(group) / total) if total else 0
        k = min(len(group), max(_MIN_PER_STRATUM, k) if len(group) >= _MIN_PER_STRATUM else len(group))
        step = len(group) / k
        picked.extend(group[int(i * step)] for i in range(k))
    # trim or backfill to n deterministically
    if len(picked) > n:
        picked = sorted(picked, key=lambda r: r["article_id"])[:n]
    elif len(picked) < n:
        have = {r["article_id"] for r in picked}
        rest = sorted((r for r in rows if r["article_id"] not in have),
                      key=lambda r: r["article_id"])
        picked.extend(rest[: n - len(picked)])
    return picked[:n]


def freeze_batch(conn: sqlite3.Connection, root: Path, *, batch_id: str,
                 kind: str = "calibration", n: int = 150) -> Path:
    """Freeze a review batch to review/<batch_id>.json. Refuses overwrite."""
    if kind not in _KINDS:
        raise ValueError(f"kind {kind!r} not served by review v0 (have: {sorted(_KINDS)})")
    path = Path(root) / "review" / f"{batch_id}.json"
    if path.exists():
        raise FileExistsError(f"batch already frozen (immutable, D13): {path}")
    verdicts = {v["article_id"]: v for v in ledger.latest_verdicts(conn)}
    rows = []
    for a in conn.execute(
            """SELECT a.article_id, a.title,
                      COALESCE(au.canonical_name, a.raw_author),
                      a.published_date
               FROM articles a LEFT JOIN authors au ON au.author_id = a.author_id
               ORDER BY a.article_id"""):
        v = verdicts.get(a[0])
        if v is None:
            continue  # ungated articles are not calibration stock
        body = conn.execute(
            "SELECT GROUP_CONCAT(body, char(10)||char(10)) FROM paragraphs "
            "WHERE article_id = ?", (a[0],)).fetchone()[0] or ""
        rows.append({"article_id": a[0], "title": a[1], "author": a[2],
                     "published_date": a[3], "topic": v["topic"],
                     "signal": v["signal"], "body": body})
    sample = _stratified_sample(rows, min(n, len(rows)))
    items = [{**r, "position": i, "exploration": False}
             for i, r in enumerate(sample)]
    atomic_write_json(path, {
        "batch_id": batch_id, "kind": kind,
        "created": datetime.now().astimezone().isoformat(timespec="seconds"),
        "ranker_version": None,
        "items": items,
    })
    return path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_review.py -q`
Expected: PASS (all 3).

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/review.py kdb_fts/tests/test_review.py
git commit -m "feat(kdb-fts): #145 P1 — review batch freezer (stratified, immutable, D13 exposure record)"
```

---

### Task 7: Review server + the one static page + event write-back

**Files:**
- Modify: `kdb_fts/review.py` (append server half)
- Create: `kdb_fts/assets/review.html`
- Modify: `kdb_fts/cli.py` (add `review` subcommand)
- Test: `kdb_fts/tests/test_review.py` (append server tests)

**Interfaces:**
- Consumes: Task 6 frozen batch JSON; Task 5 `feedback.append_event`; `assets/review.html`.
- Produces:
  - `review.make_server(root: Path, batch_id: str, port: int = 0) -> http.server.ThreadingHTTPServer` — routes: `GET /` and `GET /review.html` → the static page; `GET /batch` → frozen JSON bytes; `POST /event` with JSON `{article_id, action, reason_text?}` → stamps exposure context (`batch_id`, `position_shown`, `score_shown`, `ranker_version`, `exploration`) **from the frozen batch** (never trusted from the client), appends via `feedback.append_event`, returns `200 {"ok": true}`; `400` unknown article/action; `404` anything else.
  - `review.serve(root: Path, batch_id: str) -> None` — binds `127.0.0.1:0`, prints the URL, `webbrowser.open`s it, `serve_forever` until Ctrl-C.
  - HTML element/id + endpoint contract the page and tests share: `#title`, `#meta`, `#body`, `#progress`, `#reason`, buttons `data-action` ∈ {strong, interesting, weak, noise}, endpoints `/batch` and `/event`.

- [ ] **Step 1: Write the failing tests**

Append to `kdb_fts/tests/test_review.py`:

```python
import http.client
import threading

from kdb_fts import feedback


def _serve(tmp_path, batch_id):
    server = review.make_server(tmp_path, batch_id)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def _req(server, method, path, payload=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1])
    body = json.dumps(payload) if payload is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    conn.request(method, path, body=body, headers=headers)
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_server_roundtrip_event_writeback(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=4)
    _gate_all(conn, tmp_path)
    review.freeze_batch(conn, tmp_path, batch_id="b1", n=3)
    conn.close()
    server = _serve(tmp_path, "b1")
    try:
        status, html = _req(server, "GET", "/")
        assert status == 200 and b'id="title"' in html
        status, batch = _req(server, "GET", "/batch")
        assert status == 200
        item = json.loads(batch)["items"][0]
        status, out = _req(server, "POST", "/event",
                           {"article_id": item["article_id"], "action": "strong",
                            "reason_text": "compelling"})
        assert status == 200 and json.loads(out)["ok"] is True
    finally:
        server.shutdown()
    events = feedback.load_events(tmp_path, batch_id="b1")
    assert len(events) == 1
    e = events[0]
    # exposure context stamped server-side from the frozen batch (D13)
    assert e["target_id"] == item["article_id"]
    assert e["position_shown"] == item["position"]
    assert e["score_shown"] == item["signal"]
    assert e["ranker_version"] is None
    assert e["reason_text"] == "compelling"
    assert e["exploration"] is False


def test_server_rejects_unknown_article_and_action(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=4)
    _gate_all(conn, tmp_path)
    review.freeze_batch(conn, tmp_path, batch_id="b1", n=2)
    conn.close()
    server = _serve(tmp_path, "b1")
    try:
        status, _ = _req(server, "POST", "/event",
                         {"article_id": "ghost", "action": "strong"})
        assert status == 400
        batch = json.loads(_req(server, "GET", "/batch")[1])
        status, _ = _req(server, "POST", "/event",
                         {"article_id": batch["items"][0]["article_id"],
                          "action": "bogus"})
        assert status == 400
        assert _req(server, "GET", "/nope")[0] == 404
    finally:
        server.shutdown()
    assert feedback.load_events(tmp_path) == []  # nothing written
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_review.py -q`
Expected: FAIL — `AttributeError: ... 'make_server'`.

- [ ] **Step 3: Implement**

Append to `kdb_fts/review.py`:

```python
# --- server half (Task 7): stdlib http.server + one static page (D22) ------

import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from kdb_fts import feedback

_PAGE_PATH = Path(__file__).parent / "assets" / "review.html"


def make_server(root: Path, batch_id: str,
                port: int = 0) -> ThreadingHTTPServer:
    """Build (not start) the review server for one frozen batch."""
    root = Path(root)
    batch_path = root / "review" / f"{batch_id}.json"
    frozen_text = batch_path.read_text(encoding="utf-8")  # missing → FileNotFoundError, good
    frozen = json.loads(frozen_text)
    by_id = {item["article_id"]: item for item in frozen["items"]}
    page_bytes = _PAGE_PATH.read_bytes()
    batch_bytes = frozen_text.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path in ("/", "/review.html"):
                self._send(200, page_bytes, "text/html; charset=utf-8")
            elif self.path == "/batch":
                self._send(200, batch_bytes, "application/json")
            else:
                self._send(404, b"not found", "text/plain")

        def do_POST(self) -> None:
            if self.path != "/event":
                self._send(404, b"not found", "text/plain")
                return
            try:
                length = int(self.headers["Content-Length"])
                data = json.loads(self.rfile.read(length))
                item = by_id[data["article_id"]]  # KeyError → 400 below
                action = data["action"]
                reason = data.get("reason_text") or None
                if action not in feedback.ACTIONS:
                    raise ValueError(f"bad action {action!r}")
            except (KeyError, ValueError, json.JSONDecodeError, TypeError):
                self._send(400, b"bad event", "text/plain")
                return
            feedback.append_event(
                root, action=action, target_type="article",
                target_id=item["article_id"], reason_text=reason,
                ranker_version=frozen.get("ranker_version"),
                score_shown=item.get("signal"),
                position_shown=item["position"],
                batch_id=batch_id, exploration=bool(item.get("exploration", False)))
            self._send(200, b'{"ok": true}', "application/json")

        def log_message(self, *args) -> None:  # quiet
            pass

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(root: Path, batch_id: str) -> None:
    """Start the app for a frozen batch until Ctrl-C."""
    server = make_server(root, batch_id)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"review batch {batch_id!r} at {url}  (Ctrl-C to stop)")
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
```

Create `kdb_fts/assets/review.html` (complete file — no framework, no build):

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>kdb-fts review</title>
<style>
  body { font-family: system-ui, sans-serif; max-width: 860px; margin: 2rem auto; padding: 0 1rem; color: #222; }
  #meta { color: #666; font-size: .9rem; margin: .25rem 0 1rem; }
  #body { white-space: pre-wrap; background: #fafafa; border: 1px solid #ddd; padding: 1rem; max-height: 55vh; overflow-y: auto; }
  #bar { margin: 1rem 0; display: flex; gap: .5rem; align-items: center; flex-wrap: wrap; }
  button { font-size: 1rem; padding: .5rem 1rem; cursor: pointer; }
  button.strong { background: #d7f0d7; } button.noise { background: #f0d7d7; }
  #reason { width: 100%; min-height: 3rem; margin-top: .5rem; display: none; }
  #progress { color: #666; }
  #saved { color: #2a7; margin-left: .5rem; }
  kbd { background: #eee; border-radius: 3px; padding: 0 4px; }
</style>
</head>
<body>
<h2 id="title">loading…</h2>
<div id="meta"></div>
<div id="bar">
  <button data-action="strong" class="strong">strong <kbd>1</kbd></button>
  <button data-action="interesting">interesting <kbd>2</kbd></button>
  <button data-action="weak">weak <kbd>3</kbd></button>
  <button data-action="noise" class="noise">noise <kbd>4</kbd></button>
  <span id="progress"></span><span id="saved"></span>
</div>
<textarea id="reason" placeholder="why? (extremes teach the rubric — optional but valuable)"></textarea>
<div id="body"></div>
<script>
let batch = null, idx = 0, pendingAction = null;
const labeled = new Set();

async function init() {
  batch = await (await fetch('/batch')).json();
  document.title = 'kdb-fts review — ' + batch.batch_id;
  show(0);
}

function show(i) {
  idx = i;
  const it = batch.items[i];
  document.getElementById('title').textContent = it.title || '(untitled)';
  document.getElementById('meta').textContent =
    (it.author || '?') + ' · ' + (it.published_date || '?') +
    ' · topic guess: ' + it.topic + ' · signal ' + it.signal.toFixed(2);
  document.getElementById('body').textContent = it.body;
  document.getElementById('reason').style.display = 'none';
  document.getElementById('reason').value = '';
  document.getElementById('saved').textContent = labeled.has(it.article_id) ? '✓ labeled' : '';
  updateProgress();
}

function updateProgress() {
  document.getElementById('progress').textContent =
    (idx + 1) + ' / ' + batch.items.length + '  ·  labeled ' + labeled.size;
}

function next() { if (idx + 1 < batch.items.length) show(idx + 1); }

async function label(action) {
  const it = batch.items[idx];
  // extremes (strong/noise) invite a reason first (D13); Enter/again submits.
  const box = document.getElementById('reason');
  if ((action === 'strong' || action === 'noise') &&
      box.style.display === 'none' && pendingAction !== action) {
    pendingAction = action;
    box.style.display = 'block';
    box.focus();
    return;
  }
  const resp = await fetch('/event', {method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({article_id: it.article_id, action: action,
                          reason_text: box.value || null})});
  if (resp.ok) {
    labeled.add(it.article_id);
    pendingAction = null;
    next();
  } else {
    document.getElementById('saved').textContent = 'SAVE FAILED — ' + resp.status;
  }
}

document.querySelectorAll('button[data-action]').forEach(b =>
  b.addEventListener('click', () => label(b.dataset.action)));
document.getElementById('reason').addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && pendingAction) label(pendingAction);
});
document.addEventListener('keydown', e => {
  const keys = {'1': 'strong', '2': 'interesting', '3': 'weak', '4': 'noise'};
  if (e.target.tagName !== 'TEXTAREA' && keys[e.key]) label(keys[e.key]);
});
init();
</script>
</body>
</html>
```

In `kdb_fts/cli.py` — extend the import line with `review`, and add:

```python
def _cmd_review(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    batch_path = root / "review" / f"{args.batch}.json"
    if not batch_path.exists():
        review.freeze_batch(conn, root, batch_id=args.batch, kind=args.kind, n=args.n)
        print(f"froze batch {args.batch} ({args.kind}, n={args.n})")
    conn.close()
    review.serve(root, args.batch)
    return 0
```

```python
    p = sub.add_parser("review", help="freeze a batch (if new) and serve the labeling app (D22)")
    p.add_argument("--batch", default="calibration-p1")
    p.add_argument("--kind", default="calibration",
                   choices=["calibration"])
    p.add_argument("--n", type=int, default=150)
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_review)
```

(Freeze-if-absent, serve-always: re-running `kdb-fts review --batch calibration-p1` resumes labeling an existing batch — events are append-only, latest label per target wins in the Task 8 report.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_review.py tools/tests/test_package_boundaries.py -q`
Expected: PASS (all 5 review tests + write guard — `atomic_write_json` in the freezer is a plain `Name` call, guard-clean).

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/review.py kdb_fts/assets/review.html kdb_fts/cli.py kdb_fts/tests/test_review.py
git commit -m "feat(kdb-fts): #145 P1 — review web app v0 (stdlib server, static page, server-stamped events)"
```

---

### Task 8: `calibrate.py` — gate precision/recall report + `kdb-fts calibration` CLI

**Files:**
- Create: `kdb_fts/calibrate.py`
- Modify: `kdb_fts/cli.py` (add `calibration` subcommand)
- Test: `kdb_fts/tests/test_calibrate.py`

**Interfaces:**
- Consumes: `feedback.load_events` (Task 5), `ledger.latest_verdicts` (Task 4).
- Produces:
  - `calibrate.RELEVANT_TOPICS: frozenset[str]` — `{"investment", "finance-econ"}` (§9 Phase-1 gate)
  - `calibrate.POSITIVE_ACTIONS: frozenset[str]` — `{"strong", "interesting"}` (Joseph's "worth my time" buckets)
  - `calibrate.report(conn, root: Path, batch_id: str) -> dict` — `{labeled, confusion: {tp, fp, fn, tn}, precision, recall, f1, by_topic: {topic: {pos, neg}}}`; latest event per `(batch_id, target_id)` wins (re-labeling is allowed).
  - Rule: gate-relevant ⇔ latest verdict topic ∈ RELEVANT_TOPICS; label-relevant ⇔ latest bucket ∈ POSITIVE_ACTIONS.

- [ ] **Step 1: Write the failing tests**

Create `kdb_fts/tests/test_calibrate.py`:

```python
from kdb_fts import calibrate, feedback, ledger
from kdb_fts.tests.test_gate import _seed_articles
from kdb_fts.tests.test_review import _gate_all


def test_report_confusion_matrix(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=6)
    _gate_all(conn, tmp_path)  # topics cycle: investment, finance-econ, geopolitics, ...
    ids = [r[0] for r in conn.execute(
        "SELECT article_id FROM articles ORDER BY article_id")]
    # gid0 investment, gid1 finance-econ, gid2 geopolitics,
    # gid3 china-econ, gid4 ai-tech, gid5 other
    feedback.append_event(tmp_path, action="strong", target_type="article",
                          target_id=ids[0], batch_id="b1")   # gate+ label+ → tp
    feedback.append_event(tmp_path, action="noise", target_type="article",
                          target_id=ids[1], batch_id="b1")   # gate+ label- → fp
    feedback.append_event(tmp_path, action="interesting", target_type="article",
                          target_id=ids[2], batch_id="b1")   # gate- label+ → fn
    feedback.append_event(tmp_path, action="weak", target_type="article",
                          target_id=ids[3], batch_id="b1")   # gate- label- → tn
    # ids[4], ids[5] unlabeled → excluded from the matrix
    # re-label: ids[3] upgraded → becomes fn
    feedback.append_event(tmp_path, action="strong", target_type="article",
                          target_id=ids[3], batch_id="b1")
    rep = calibrate.report(conn, tmp_path, "b1")
    assert rep["labeled"] == 4
    assert rep["confusion"] == {"tp": 1, "fp": 1, "fn": 2, "tn": 0}
    assert abs(rep["precision"] - 0.5) < 1e-9
    assert abs(rep["recall"] - 1 / 3) < 1e-9
    assert rep["by_topic"]["china-econ"] == {"pos": 1, "neg": 0}


def test_report_empty_batch(tmp_path):
    conn = ledger.connect(tmp_path)
    rep = calibrate.report(conn, tmp_path, "nobody-labeled")
    assert rep["labeled"] == 0 and rep["precision"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest kdb_fts/tests/test_calibrate.py -q`
Expected: FAIL — `ModuleNotFoundError: kdb_fts.calibrate`.

- [ ] **Step 3: Implement**

Create `kdb_fts/calibrate.py`:

```python
"""calibrate — gate precision/recall against Joseph's labels (§9 Phase-1 gate).

Label-relevant = latest bucket in {strong, interesting}; gate-relevant =
latest verdict topic in {investment, finance-econ}. Joseph sets the accept
threshold AFTER seeing this matrix — no invented number lives here.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from kdb_fts import feedback, ledger

RELEVANT_TOPICS = frozenset({"investment", "finance-econ"})
POSITIVE_ACTIONS = frozenset({"strong", "interesting"})
_BUCKET_ACTIONS = frozenset({"strong", "interesting", "weak", "noise"})


def report(conn: sqlite3.Connection, root: Path, batch_id: str) -> dict:
    latest_label: dict[str, str] = {}
    for e in feedback.load_events(root, batch_id=batch_id):
        if e["target_type"] == "article" and e["action"] in _BUCKET_ACTIONS:
            latest_label[e["target_id"]] = e["action"]  # file order = ts order
    verdicts = {v["article_id"]: v for v in ledger.latest_verdicts(conn)}
    confusion = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    by_topic: dict[str, dict[str, int]] = {}
    for article_id, action in sorted(latest_label.items()):
        v = verdicts.get(article_id)
        if v is None:
            continue
        gate_pos = v["topic"] in RELEVANT_TOPICS
        label_pos = action in POSITIVE_ACTIONS
        key = ("tp" if gate_pos else "fn") if label_pos else ("fp" if gate_pos else "tn")
        confusion[key] += 1
        bucket = by_topic.setdefault(v["topic"], {"pos": 0, "neg": 0})
        bucket["pos" if label_pos else "neg"] += 1
    tp, fp, fn, tn = (confusion[k] for k in ("tp", "fp", "fn", "tn"))
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall else (0.0 if precision == 0.0 or recall == 0.0 else None))
    return {"batch_id": batch_id, "labeled": len(latest_label),
            "confusion": confusion, "precision": precision,
            "recall": recall, "f1": f1, "by_topic": by_topic}
```

In `kdb_fts/cli.py` — extend the import line with `calibrate`, and add:

```python
def _cmd_calibration(args) -> int:
    root = Path(args.state).expanduser().resolve() if args.state else state.state_root()
    conn = ledger.connect(root)
    rep = calibrate.report(conn, root, args.batch)
    print(f"batch {rep['batch_id']}: {rep['labeled']} articles labeled")
    c = rep["confusion"]
    print(f"confusion (gate-relevant = investment ∪ finance-econ): "
          f"tp={c['tp']} fp={c['fp']} fn={c['fn']} tn={c['tn']}")
    if rep["precision"] is not None:
        print(f"precision={rep['precision']:.3f} recall={rep['recall']:.3f} f1={rep['f1']:.3f}")
    print("by topic (Joseph-positive / negative):")
    for topic, b in sorted(rep["by_topic"].items()):
        print(f"  {topic}: {b['pos']}/{b['neg']}")
    return 0
```

```python
    p = sub.add_parser("calibration", help="gate precision/recall vs labels for a batch")
    p.add_argument("--batch", default="calibration-p1")
    p.add_argument("--state", default=None)
    p.set_defaults(fn=_cmd_calibration)
```

Add a CLI test to `test_calibrate.py`:

```python
def test_cli_calibration(tmp_path, capsys):
    from kdb_fts import cli

    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=2)
    _gate_all(conn, tmp_path)
    conn.close()
    cli.main(["feedback", "article", "gid0", "strong", "--state", str(tmp_path)])
    rc = cli.main(["calibration", "--batch", "calibration-p1", "--state", str(tmp_path)])
    assert rc == 0
    assert "precision" in capsys.readouterr().out
```

Wait — the CLI feedback call above passes no `--batch`, so the event has `batch_id=None` and the calibration report over batch `calibration-p1` won't see it; the output then has `labeled=0` and **no** `precision` line, failing the assertion. Fix the test to append with the batch:

```python
def test_cli_calibration(tmp_path, capsys):
    from kdb_fts import cli

    conn = ledger.connect(tmp_path)
    _seed_articles(conn, tmp_path, n=2)
    _gate_all(conn, tmp_path)
    conn.close()
    feedback.append_event(tmp_path, action="strong", target_type="article",
                          target_id="gid0", batch_id="calibration-p1")
    rc = cli.main(["calibration", "--batch", "calibration-p1", "--state", str(tmp_path)])
    assert rc == 0
    assert "precision" in capsys.readouterr().out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest kdb_fts/tests/ -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/calibrate.py kdb_fts/cli.py kdb_fts/tests/test_calibrate.py
git commit -m "feat(kdb-fts): #145 P1 — calibration report (gate precision/recall vs Joseph's labels)"
```

---

### Task 9: Final review + Joseph-fired live gate

**No code in this task.** Steps:

- [ ] **Step 1: Whole-surface review** — dispatch a spec+quality reviewer over the Phase 1 diff (all Task 1–8 commits) against blueprint §7.2/§7.5/§9-Phase-1/D13/D16/D18/D19/D20/D22 and this plan's deviations 1–7. Fix waves as needed (per-task or one fixer, sized by findings).
- [ ] **Step 2: Full suite** — `.venv/bin/python -m pytest -q`; expect green, exit 0.
- [ ] **Step 3: Live gate (Joseph's word)** — on the real state root:
  1. `.venv/bin/kdb-fts gate --dry-run --max 5` — sanity: 5 verdicts printed, nothing committed (`status` unchanged).
  2. `.venv/bin/kdb-fts gate` — full run over the ~2,511 ok articles on `deepseek-v4-flash` (est. ~$2–3 at the 2026-08-16 prices, ~30–60 min; resumable if interrupted).
  3. `.venv/bin/kdb-fts review --batch calibration-p1` — freezes 150 stratified articles and opens the app; **Joseph labels 150** (strong/interesting/weak/noise, reasons at extremes).
  4. `.venv/bin/kdb-fts calibration` — the confusion matrix; **Joseph sets the accept threshold** (recorded in TASKS.md; threshold consumption is Phase 3's ranker).
  5. Fallback on record (§9): if the gate underperforms, extract-all is a ~$1–3 switch — D5 is policy, not structure.
- [ ] **Step 4: Docs close-out (after the live gate)** — TASKS.md #145 status line → P1 landed + threshold outcome; CODEBASE_OVERVIEW.md Milestone Changelog entry at Joseph's word; blueprint §11 cost note amended with the observed real gate cost; AGENTS.md `kdb-fts` line extended (`gate/review/feedback/calibration`) on disk.
- [ ] **Step 5: Commit + push (Joseph's word)**

```bash
git add docs/TASKS.md docs/CODEBASE_OVERVIEW.md docs/superpowers/specs/2026-08-16-task145-kdb-fts-blueprint-v0.1.md
git commit -m "docs: #145 P1 — live gate results, calibration matrix, threshold decision"
```
