# Task #145 Phase 2 — Extraction Implementation Plan (TDD)

> **Blueprint**: [`2026-08-21-task145-phase2-extraction-blueprint.md`](../specs/2026-08-21-task145-phase2-extraction-blueprint.md) (v0.2).
> **Decisions**: [`2026-08-21-task145-phase2-extraction-architecture.md`](../specs/2026-08-21-task145-phase2-extraction-architecture.md) (v0.3).
> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Steps use `- [ ]` checkbox syntax; each task is failing-tests-first.

**Goal:** give `kdb_fts` its extraction pass — one structured LLM call per triggered article
(accept-rule ∪ exploration) producing source-grounded `idea_mentions` + `lesson_cards` with proven evidence
spans — plus the 3-model pool registration that powers the pilot bake-off.

**Architecture:** `extract.py` (pure prompt/parse/salvage half + `run_extract` runner, mirroring `gate.py`),
`spans.py` (pure anchor-slice + fallback ladder), migration 3 (four tables), and a per-article **atomic**
commit. The D10 proof is enforced twice: `spans.py` produces only source slices, and `insert_span` re-verifies
at the last write boundary.

**Tech Stack:** Python 3.10+ stdlib + `common.call_model` / `common.model_pool` / `common.atomic_io`; SQLite
migration 3; no new dependencies.

## Global Constraints

- `kdb_fts` imports `common` **only**; nothing internal imports `kdb_fts` (`tools/tests/test_package_boundaries.py`).
- Write-boundary guard: `sqlite3.connect`, `mkdir`, `Path` mutators allowed **only in `ledger.py`**; every other
  file write goes through `common.atomic_io`. `spans.py` is **pure** (no I/O).
- **No new dependencies.**
- Default model `deepseek-v4-flash` via `common.model_pool.resolve_models_json` (D19); overridable with `--model`.
- `--dry-run` performs LLM calls but commits **nothing** (D20).
- Extraction is **resumable at article granularity** — correct because one article's whole extraction commits
  atomically (blueprint §5.4).
- Deterministic order everywhere (`article_id` ASC); no wall-clock-dependent selection.
- Run tests with `.venv/bin/python -m pytest` (plain `pytest` uses system Python).
- Commit style: `feat(kdb-fts): #145 P2 — …` with task ref. Per-task commits pre-authorized by plan approval;
  **push waits for Joseph's word.**

## Blueprint deviations recorded up front

*(none — the blueprint v0.2 already absorbed the Kimi review; deviations surface here only if a task forces one.)*

---

### Task 1: Migration 3 — extraction tables

**Files:**
- Modify: `kdb_fts/schema.py` (append migration 3; bump `SCHEMA_VERSION` to 3)
- Test: `kdb_fts/tests/test_schema.py` (append)

**Interfaces:**
- Produces: `SCHEMA_VERSION == 3`; tables `extraction_runs`, `idea_mentions`, `lesson_cards`, `evidence_spans`
  with the exact column sets below; `evidence_spans` cascades on article delete; `migrate` stays txn-wrapped.

- [ ] **Step 1: Write the failing tests**

Append to `kdb_fts/tests/test_schema.py`:

```python
def test_migration_3_creates_extraction_tables(tmp_path):
    conn = ledger.connect(tmp_path)
    assert schema.current_version(conn) == 3
    expect = {
        "extraction_runs": {"article_id", "run_id", "schema_version", "model",
                            "prompt_version", "status", "expect_ideas",
                            "expect_lessons", "chunk_index", "n_chunks",
                            "n_mentions", "n_cards", "input_tokens", "output_tokens"},
        "idea_mentions": {"mention_id", "article_id", "run_id", "schema_version",
                          "company", "stance", "thesis", "ticker",
                          "valuation_premise", "catalyst", "risks", "horizon",
                          "expires_on", "extraction_uncertainty", "idea_id", "dedupe_key"},
        "lesson_cards": {"card_id", "article_id", "run_id", "schema_version",
                         "principle", "context", "reusable_application",
                         "failure_mode", "lesson_type", "framework_id", "dedupe_key"},
        "evidence_spans": {"span_id", "article_id", "record_type", "record_id",
                           "field", "paragraph_id", "exact_quote"},
    }
    for table, cols in expect.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        assert cols <= have, (table, cols - have)


def test_evidence_spans_cascade_on_article_delete(tmp_path):
    from kdb_fts import intake

    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "a.md").write_text(
        "---\ntitle: T\nauthor: A\ngmail_message_id: gid1\n---\n\n" + "body " * 60,
        encoding="utf-8")
    conn = ledger.connect(tmp_path)
    intake.run_intake(conn, raw, "run-1", state_root=tmp_path)
    conn.execute(
        "INSERT INTO evidence_spans (article_id, record_type, record_id, field, paragraph_id, exact_quote)"
        " VALUES ('gid1', 'idea', 1, 'thesis', 'p0001', 'body')")
    conn.commit()
    conn.execute("DELETE FROM articles WHERE article_id = 'gid1'")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM evidence_spans").fetchone()[0] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

`.venv/bin/python -m pytest kdb_fts/tests/test_schema.py -q` → FAIL: `current_version` == 2; the four tables
don't exist.

- [ ] **Step 3: Implement**

In `kdb_fts/schema.py`, set `SCHEMA_VERSION = 3` and append `3: """…"""` to `MIGRATIONS` using the exact DDL
from blueprint §4 (reproduced for reference — `extraction_runs` status `ok|empty|failed|skipped`; 0-based
`chunk_index`; `idea_mentions` `dedupe_key` = `sha256(company\0stance\0thesis)`; `lesson_cards` `dedupe_key` =
`sha256(principle\0(context or ''))`; `evidence_spans` with `article_id … ON DELETE CASCADE` and
`idx_spans_record`).

- [ ] **Step 4: Run tests to verify they pass**

`.venv/bin/python -m pytest kdb_fts/tests/ -q` → PASS (all).

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/schema.py kdb_fts/tests/test_schema.py
git commit -m "feat(kdb-fts): #145 P2 — migration 3 extraction tables (runs/mentions/cards/spans)"
```

---

### Task 2: Ledger access + the D10 re-check

**Files:**
- Modify: `kdb_fts/ledger.py` (append access functions)
- Test: `kdb_fts/tests/test_ledger.py` (append)

**Interfaces:**
- Produces (exact signatures in blueprint §5.3):
  - `triggered_articles(conn) -> list[dict]` — accept-rule ∪ exploration, `article_id` ASC, with
    `expect_ideas`/`expect_lessons` from the latest verdict.
  - `article_paragraphs(conn, article_id) -> list[tuple[str, str]]` — ordered `(paragraph_id, body)`.
  - `insert_mention(…) -> int | None`, `insert_card(…) -> int | None` (`None` on `INSERT OR IGNORE` dedupe).
  - `SpanProofError(ValueError)`; `insert_span(…)` — **re-verifies** the substring proof, raises on failure.
  - `commit_extraction_article(…)` — one `BEGIN…COMMIT` across all chunks.
  - `latest_extractions(conn) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

Append to `kdb_fts/tests/test_ledger.py`:

```python
def _seed_gated(conn, tmp_path, articles):
    """articles: list of (gid, topic, signal, exploration, extract_ideas, extract_lessons)."""
    from kdb_fts import intake
    raw = tmp_path / "raw"; raw.mkdir(exist_ok=True)
    for (gid, topic, sig, exp, ei, el) in articles:
        (raw / f"{gid}.md").write_text(
            f"---\ntitle: {gid}\nauthor: A\ngmail_message_id: {gid}\n---\n\n" + "body " * 60,
            encoding="utf-8")
    intake.run_intake(conn, raw, "seed", state_root=tmp_path)
    for (gid, topic, sig, exp, ei, el) in articles:
        ledger.insert_gate_verdict(conn, article_id=gid, run_id="r1", topic=topic,
                                   signal=sig, extract_ideas=ei, extract_lessons=el,
                                   exploration=exp, confidence=None, rationale="",
                                   model="m", prompt_version="gate_v1",
                                   input_tokens=0, output_tokens=0)


def test_triggered_articles_union_exploration(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_gated(conn, tmp_path, [
        ("inv", "investment", 0.5, 0, True, False),   # accepted (topic clause)
        ("fe",  "finance-econ", 0.5, 0, False, True), # accepted (topic clause)
        ("sig", "other", 0.9, 0, False, False),       # accepted (signal clause)
        ("geo", "geopolitics", 0.1, 0, False, False), # ineligible, no exploration
        ("exp", "geopolitics", 0.1, 1, False, False), # ineligible + exploration
    ])
    got = {r["article_id"] for r in ledger.triggered_articles(conn)}
    assert got == {"inv", "fe", "sig", "exp"}   # geo excluded


def test_article_paragraphs_ordered(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_gated(conn, tmp_path, [("inv", "investment", 0.5, 0, True, False)])
    paras = ledger.article_paragraphs(conn, "inv")
    assert [p[0] for p in paras] == ["p0001"]


def test_insert_span_refuses_non_substring(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_gated(conn, tmp_path, [("inv", "investment", 0.5, 0, True, False)])
    with pytest.raises(ledger.SpanProofError):
        ledger.insert_span(conn, article_id="inv", record_type="idea", record_id=1,
                           field="thesis", paragraph_id="p0001", exact_quote="NOT IN SOURCE")


def test_commit_extraction_article_atomic_rolls_back(tmp_path):
    conn = ledger.connect(tmp_path)
    _seed_gated(conn, tmp_path, [("inv", "investment", 0.5, 0, True, False)])
    bad_spans = [{"article_id": "inv", "record_type": "idea", "record_id": 1,
                  "field": "thesis", "paragraph_id": "p0001", "exact_quote": "bogus"}]
    with pytest.raises(ledger.SpanProofError):
        ledger.commit_extraction_article(
            conn, article_id="inv", run_id="r1", schema_version="extract_v1", model="m",
            prompt_version="extract_v1",
            statuses=[{"status": "ok", "chunk_index": 0, "n_chunks": 1, "n_mentions": 1,
                       "n_cards": 0, "expect_ideas": True, "expect_lessons": False,
                       "input_tokens": 0, "output_tokens": 0}],
            mentions=[{"company": "X", "stance": "long", "thesis": "buy"}],
            cards=[], spans=bad_spans)
    # rollback: no extraction_runs row, no mention row survived the failed txn
    assert conn.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM idea_mentions").fetchone()[0] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

`.venv/bin/python -m pytest kdb_fts/tests/test_ledger.py -q` → FAIL: `triggered_articles` / `article_paragraphs`
/ `insert_span` / `commit_extraction_article` / `SpanProofError` missing.

- [ ] **Step 3: Implement**

Append the access functions to `kdb_fts/ledger.py` with the exact signatures from blueprint §5.3. Load-bearing
detail — `insert_span`'s re-check is the invariant's structural home:

```python
class SpanProofError(ValueError):
    """A span whose exact_quote is not a substring of its source paragraph."""

def insert_span(conn, *, article_id, record_type, record_id, field,
                paragraph_id, exact_quote) -> None:
    row = conn.execute(
        "SELECT body FROM paragraphs WHERE article_id = ? AND paragraph_id = ?",
        (article_id, paragraph_id),
    ).fetchone()
    if row is None or exact_quote not in row[0]:
        raise SpanProofError(f"{record_type}:{field} — quote not a substring of {paragraph_id}")
    conn.execute(
        "INSERT INTO evidence_spans (article_id, record_type, record_id, field, paragraph_id, exact_quote)"
        " VALUES (?,?,?,?,?,?)",
        (article_id, record_type, record_id, field, paragraph_id, exact_quote),
    )
```

`triggered_articles` joins `latest_verdicts` (the existing `JOIN (… MAX(run_id) …)` shape) on `articles` and
filters `topic IN ('investment','finance-econ') OR signal >= 0.75 OR exploration = 1`. `commit_extraction_article`
wraps the whole insert set in `BEGIN`/`COMMIT` with `rollback()` + re-raise on any exception. `insert_mention`
and `insert_card` use `INSERT OR IGNORE` and return the PK or `None`.

- [ ] **Step 4: Run tests to verify they pass**

`.venv/bin/python -m pytest kdb_fts/tests/test_ledger.py tools/tests/test_package_boundaries.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/ledger.py kdb_fts/tests/test_ledger.py
git commit -m "feat(kdb-fts): #145 P2 — ledger access (trigger set, paragraphs, span-proof, atomic article commit)"
```

---

### Task 3: `spans.py` — anchor validation + source slice + fallback ladder

**Files:**
- Create: `kdb_fts/spans.py` (pure)
- Test: `kdb_fts/tests/test_spans.py` (create)

**Interfaces:**
- Produces (blueprint §5.1): `validate_anchor(paragraph, anchor) -> int`, `slice_span(paragraph, head, tail)
  -> str | None`, `locate_quote(paragraph, quote) -> str | None`, and the private `_fold`, `_fold_with_offsets`,
  `_slice_by_offsets`, `_fuzzy_snap`.

- [ ] **Step 1: Write the failing tests**

Create `kdb_fts/tests/test_spans.py`:

```python
import pytest

from kdb_fts import spans


def test_validate_anchor_counts():
    p = "the quick brown fox jumps over the lazy dog"
    assert spans.validate_anchor(p, "quick brown") == 1
    assert spans.validate_anchor(p, "the") == 2
    assert spans.validate_anchor(p, "absent") == 0


def test_slice_span_valid_and_invalid():
    p = "the quick brown fox jumps over the lazy dog"
    assert spans.slice_span(p, "quick", "lazy") == "quick brown fox jumps over the lazy"
    assert spans.slice_span(p, "the", "lazy") is None       # head not unique
    assert spans.slice_span(p, "quick", "brown") is None    # tail before head end
    assert spans.slice_span(p, "quick", "absent") is None   # tail missing
    assert spans.slice_span(p, "", "lazy") is None          # empty anchor


def test_locate_quote_exact_first():
    p = "Buffett bought Coca-Cola in 1988."
    assert spans.locate_quote(p, "Coca-Cola in 1988") == "Coca-Cola in 1988"


def test_locate_quote_folded_and_fuzzy_still_substring():
    p = "Buffett bought Coca-Cola in 1988."
    # folded: unicode compatibility chars collapse to the same source text
    got = spans.locate_quote(p, "CocaCola in 1988")  # removed hyphen → fuzzy/folded path
    assert got is None or got in p
    assert spans.locate_quote(p, "totally absent phrase") is None


def test_property_result_is_none_or_substring():
    """Every ladder rung returns a verbatim source substring or None (Finding 5)."""
    import random
    rng = random.Random(0)
    for _ in range(200):
        words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]
        n = rng.randint(5, 30)
        para = " ".join(rng.choice(words) for _ in range(n))
        # a quote built from a random window, sometimes perturbed
        a, b = sorted(rng.sample(range(len(para)), 2))
        quote = para[a:b]
        if rng.random() < 0.5:
            quote = quote.replace(" ", "", rng.randint(0, 1))  # perturb
        result = spans.locate_quote(para, quote)
        assert result is None or result in para
```

- [ ] **Step 2: Run tests to verify they fail**

`.venv/bin/python -m pytest kdb_fts/tests/test_spans.py -q` → FAIL: `ModuleNotFoundError: kdb_fts.spans`.

- [ ] **Step 3: Implement**

Create `kdb_fts/spans.py` with the exact pure functions from blueprint §5.1. Load-bearing: `_fold_with_offsets`
folds char-by-char recording source offsets (NFKC is not length-preserving), `_slice_by_offsets` maps a folded
index span back to the source substring, and `locate_quote` re-verifies `_fold(candidate) == folded_q` before
returning. `_fuzzy_snap` returns a verbatim source substring or `None`.

- [ ] **Step 4: Run tests to verify they pass**

`.venv/bin/python -m pytest kdb_fts/tests/test_spans.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/spans.py kdb_fts/tests/test_spans.py
git commit -m "feat(kdb-fts): #145 P2 — spans: anchor slice + fallback ladder (pure, D10 proof)"
```

---

### Task 4: `extract_v1.j2` + pure parse/salvage

**Files:**
- Create: `kdb_fts/prompts/extract_v1.j2`
- Create: `kdb_fts/extract.py` (pure half only — runner lands in Task 5)
- Test: `kdb_fts/tests/test_extract.py` (create)

**Interfaces:**
- Produces (blueprint §5.2): `EXTRACT_PROMPT_VERSION = "extract_v1"`, `MAX_BODY_WORDS = 8000`,
  `CHUNK_TARGET_WORDS = 6000`, `STANCES`, `LESSON_TYPES`, `ExtractParseError(ValueError)`,
  `RawMention`/`RawCard`/`ExtractionResult` dataclasses, `build_prompt(*, title, author, published_date,
  paragraphs) -> str`, `parse_extraction(text) -> ExtractionResult`.

- [ ] **Step 1: Write the failing tests**

Create `kdb_fts/tests/test_extract.py`:

```python
import json

import pytest

from kdb_fts import extract


def _payload(**over):
    base = {
        "ideas": [{
            "company": "Alibaba", "stance": "long", "thesis": "Cloud re-acceleration",
            "evidence": {"paragraph_id": "p0001", "head_anchor": "Cloud revenue", "tail_anchor": "grew"},
        }],
        "lessons": [],
        "downgraded": False,
    }
    base.update(over)
    return json.dumps(base)


def test_political_fixture_zero_mentions():
    r = extract.parse_extraction(json.dumps({"ideas": [], "lessons": [], "downgraded": True}))
    assert r.mentions == [] and r.cards == [] and r.downgraded is True


def test_thesis_fixture_one_mention_with_span():
    r = extract.parse_extraction(_payload())
    assert len(r.mentions) == 1
    m = r.mentions[0]
    assert m.company == "Alibaba" and m.stance == "long"
    assert m.evidence["head_anchor"] == "Cloud revenue"


def test_unknown_stance_drops_mention():
    r = extract.parse_extraction(_payload(ideas=[{
        "company": "X", "stance": "yolo", "thesis": "t",
        "evidence": {"paragraph_id": "p0001", "head_anchor": "a", "tail_anchor": "b"}}]))
    assert r.mentions == []


def test_invalid_json_raises():
    with pytest.raises(extract.ExtractParseError):
        extract.parse_extraction("not json {")


def test_build_prompt_numbers_paragraphs_and_no_truncation():
    paras = [(f"p{i:04d}", "word " * 100) for i in range(1, 10)]  # 900 words total
    p = extract.build_prompt(title="T", author="A", published_date="d", paragraphs=paras)
    assert "[p0001]" in p and "[p0009]" in p and "word" in p


def test_prompt_version_matches_filename():
    from pathlib import Path
    prompts = Path(__file__).parents[1] / "prompts"
    assert (prompts / f"{extract.EXTRACT_PROMPT_VERSION}.j2").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

`.venv/bin/python -m pytest kdb_fts/tests/test_extract.py -q` → FAIL: `ModuleNotFoundError: kdb_fts.extract`.

- [ ] **Step 3: Implement**

Create `kdb_fts/prompts/extract_v1.j2` (the anchors contract — zero-is-success, `stance`/`lesson_type` enums,
`ticker`-only-if-present, per-field `paragraph_id`+`head_anchor`+`tail_anchor`), and `kdb_fts/extract.py` with
the pure half: `build_prompt` (single-pass `str.replace` over `{{TITLE}}`/`{{AUTHOR}}`/`{{PUBLISHED}}`/`{{BODY}}`,
body = numbered paragraphs; **no word truncation** — chunking is the caller's job), the dataclasses, and
`parse_extraction` (JSON-object envelope; per-record salvage: unknown `stance` → drop mention; unknown
`lesson_type` → null field; `downgraded` coerced to bool). The span-slice step is NOT in this module — the
runner applies `spans.slice_span` in Task 5; `RawMention.evidence` here is the *raw* anchor dict.

- [ ] **Step 4: Run tests to verify they pass**

`.venv/bin/python -m pytest kdb_fts/tests/test_extract.py -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/extract.py kdb_fts/prompts/extract_v1.j2 kdb_fts/tests/test_extract.py
git commit -m "feat(kdb-fts): #145 P2 — extraction prompt v1 + fail-closed parse/salvage"
```

---

### Task 5: Chunking + runner + CLI

**Files:**
- Modify: `kdb_fts/extract.py` (append the runner half)
- Modify: `kdb_fts/cli.py` (add `extract` subcommand; extend `status`)
- Test: `kdb_fts/tests/test_extract.py` (append runner tests)

**Interfaces:**
- Produces: `chunk_paragraphs(paragraphs) -> list[list[tuple[str, str]]]`; `run_extract(conn, *, state_root,
  run_id, model_id="deepseek-v4-flash", max_n=None, dry_run=False, call_fn=call_model) -> dict` (stats
  `{extracted, empty, failed, skipped, mentions, cards, input_tokens, output_tokens, cost_usd,
  dropped_records, dropped_fields}`).

- [ ] **Step 1: Write the failing tests**

Append to `kdb_fts/tests/test_extract.py`:

```python
from common.call_model import ModelResponse

from kdb_fts import ledger


def _fake_call_factory(payloads):
    """payloads: {title_suffix: response_text}. call_fn(req) picks by the Title line."""
    calls = []
    def _call(req):
        calls.append(req)
        for key, text in payloads.items():
            if f"Title: {key}" in req.prompt:
                return ModelResponse(text=text, input_tokens=100, output_tokens=20,
                                     latency_ms=5, model=req.model, provider=req.provider)
        raise AssertionError(f"no payload for prompt: {req.prompt[:200]}")
    _call.calls = calls
    return _call


def test_chunk_paragraphs_paragraph_atomic_and_long_own_chunk():
    paras = [(f"p{i:04d}", "word " * 2000) for i in range(1, 5)]   # 2000 words each
    chunks = extract.chunk_paragraphs(paras)
    assert [len(c) for c in chunks] == [3, 1]  # 3×2000=6000 then the 4th
    big = [("p0001", "word " * 9000)]  # > CHUNK_TARGET → its own chunk, never split
    assert [len(c) for c in extract.chunk_paragraphs(big)] == [1]


def test_run_extract_dry_run_commits_nothing(tmp_path):
    conn = ledger.connect(tmp_path)
    ledger.insert_gate_verdict(conn, article_id="a1", run_id="r1", topic="investment",
                               signal=0.5, extract_ideas=True, extract_lessons=False,
                               exploration=False, confidence=None, rationale="",
                               model="m", prompt_version="gate_v1",
                               input_tokens=0, output_tokens=0)
    conn.execute("INSERT INTO articles (article_id, path, content_sha256, title, raw_author,"
                 " published_date, source_url, content_kind, word_count, cleanliness,"
                 " first_seen_run, last_seen_run) VALUES ('a1','p','h','A1','x',null,null,"
                 "'article',100,'ok','r1','r1')")
    conn.execute("INSERT INTO paragraphs (article_id, paragraph_id, body) VALUES ('a1','p0001','body text here')")
    conn.commit()
    fake = _fake_call_factory({"A1": json.dumps({"ideas": [], "lessons": [], "downgraded": True})})
    stats = extract.run_extract(conn, state_root=tmp_path, run_id="r2", dry_run=True, call_fn=fake)
    assert stats["extracted"] >= 1
    assert conn.execute("SELECT COUNT(*) FROM extraction_runs").fetchone()[0] == 0


def test_run_extract_resume_skips_extracted_article(tmp_path):
    # (a minimal happy path) run once, then re-run with the same schema/model/prompt → skipped
    conn = ledger.connect(tmp_path)
    ledger.insert_gate_verdict(conn, article_id="a1", run_id="r1", topic="investment",
                               signal=0.5, extract_ideas=True, extract_lessons=False,
                               exploration=False, confidence=None, rationale="",
                               model="m", prompt_version="gate_v1", input_tokens=0, output_tokens=0)
    conn.execute("INSERT INTO articles (article_id, path, content_sha256, title, raw_author,"
                 " published_date, source_url, content_kind, word_count, cleanliness,"
                 " first_seen_run, last_seen_run) VALUES ('a1','p','h','A1','x',null,null,"
                 "'article',100,'ok','r1','r1')")
    conn.execute("INSERT INTO paragraphs (article_id, paragraph_id, body) VALUES ('a1','p0001','body text here')")
    conn.commit()
    payload = json.dumps({"ideas": [{"company": "X", "stance": "long", "thesis": "buy",
        "evidence": {"paragraph_id": "p0001", "head_anchor": "body", "tail_anchor": "here"}}],
        "lessons": [], "downgraded": False})
    fake = _fake_call_factory({"A1": payload})
    s1 = extract.run_extract(conn, state_root=tmp_path, run_id="r2", call_fn=fake)
    assert s1["mentions"] == 1
    s2 = extract.run_extract(conn, state_root=tmp_path, run_id="r3", call_fn=fake)
    assert s2["skipped"] == 1 and s2["mentions"] == 0
    # the span was source-sliced (head..tail) and proven at insert
    assert conn.execute("SELECT exact_quote FROM evidence_spans").fetchone()[0] == "body text here"
```

- [ ] **Step 2: Run tests to verify they fail**

`.venv/bin/python -m pytest kdb_fts/tests/test_extract.py -q` → FAIL: `chunk_paragraphs` / `run_extract` missing.

- [ ] **Step 3: Implement**

Append to `kdb_fts/extract.py` the runner half (blueprint §5.4): `chunk_paragraphs` (greedy paragraph-atomic
≤ `CHUNK_TARGET_WORDS`, 0-based chunks, a >target paragraph is its own chunk); `run_extract` (resolve spec →
`ledger.triggered_articles` → per article: skip if already extracted at `(schema_version, model,
prompt_version)`; `article_paragraphs`; chunk; per chunk `build_prompt` + `_call_once` + `parse_extraction` +
per-field `spans.slice_span` salvage; accumulate in memory; `ledger.commit_extraction_article` once per article
if not dry-run; raw+salvaged output per chunk to `runs/<run_id>/extractions/<article_id>/<ci>.json` via
`atomic_write_text`). Salvage rules: required-core span fail → drop record; optional span fail → null field;
track `dropped_records`/`dropped_fields`.

Add to `kdb_fts/cli.py` an `extract` subcommand mirroring `gate`'s (`--max`, `--model` default
`deepseek-v4-flash`, `--dry-run`, `--state`; pass `call_fn=extract.call_model`) and extend `_cmd_status` with an
extraction summary (counts by model/prompt_version, cost-to-date, dropped-records).

- [ ] **Step 4: Run tests to verify they pass**

`.venv/bin/python -m pytest kdb_fts/tests/test_extract.py tools/tests/test_package_boundaries.py -q` → PASS
(write-guard included: `mkdir`/`sqlite3.connect` stay in `ledger.py`; `spans.py` has no I/O).

- [ ] **Step 5: Commit**

```bash
git add kdb_fts/extract.py kdb_fts/cli.py kdb_fts/tests/test_extract.py
git commit -m "feat(kdb-fts): #145 P2 — extraction runner (chunking, atomic article commit, resume, dry-run) + CLI"
```

---

### Task 6: Model pool registration (3 additions)

**Files:**
- Modify: `common/models.json` (append 3 entries)
- Test: `common/tests/test_model_pool.py` (append; locate the existing pool test file first)

**Interfaces:**
- Produces: `gpt-5.6-luna`, `qwen3.8-max`, `glm-5.3` resolve via `resolve_models_json`; reasoning config lands
  in `spec.extra_body` per blueprint §6.

- [ ] **Step 1: Write the failing tests**

```python
def test_new_extraction_models_resolve_and_reasoning():
    from common.model_pool import resolve_models_json
    luna = resolve_models_json("gpt-5.6-luna")
    assert luna.extra_body == {"reasoning_effort": "low"}
    qwen = resolve_models_json("qwen3.8-max")
    assert qwen.extra_body.get("reasoning_effort") == "low"
    assert "enable_thinking" not in qwen.extra_body   # thinking stays ENABLED (not disabled)
    glm = resolve_models_json("glm-5.3")
    assert glm.extra_body.get("reasoning_effort") == "low"
    assert "thinking" not in glm.extra_body or glm.extra_body.get("thinking") != {"type": "disabled"}
```

- [ ] **Step 2: Run tests to verify they fail**

`.venv/bin/python -m pytest common/tests/test_model_pool.py -q` → FAIL: `UnknownModelError` for the three ids.

- [ ] **Step 3: Implement**

Append the three entries to `common/models.json` exactly per blueprint §6 (provider `zai` for `glm-5.3`,
`thinking: "enabled"` for both `qwen3.8-max` and `glm-5.3`, `extra_body: {"reasoning_effort": "low"}` for all
three; `"temperature": null` for the reasoning-family entries). Before committing, **ping**
`https://api.z.ai/api/paas/v4` to confirm GLM-5.3 API availability (blueprint §6 — if down, still register the
entry but mark the bake-off as a 6-candidate fallback in the journal).

- [ ] **Step 4: Run tests to verify they pass**

`.venv/bin/python -m pytest common/tests/test_model_pool.py kdb_fts/tests/ -q` → PASS.

- [ ] **Step 5: Commit**

```bash
git add common/models.json common/tests/test_model_pool.py
git commit -m "feat(kdb-fts): #145 P2 — register gpt-5.6-luna / qwen3.8-max / glm-5.3 (min-reasoning)"
```

---

## Pilot gate (P2.4 — Joseph-fired, not a TDD task)

After Tasks 1–6 are green, run the two-stage pilot (blueprint §7):

1. **Bake-off** — freeze the 20-file probe (idea-only / lesson-only / both / long-tail) and run it through all
   7 candidates at min-reasoning. Compute per model: span-validity (hard gate 100% on landed), anchor-dropout,
   field-fill, flag-divergence, cost-per-landed-record, plus Joseph's audit.
2. **100-file eligible-set audit — on the winner** — with the 95 flag-disagreement articles oversampled
   additively.

**Gate:** span-validity 100% on landed records; zero-idea rate on the political holdout reported; the bake-off
decision recorded in `docs/TASKS.md` + the ADR. Full-suite `.venv/bin/python -m pytest` green before the
100-file audit.
