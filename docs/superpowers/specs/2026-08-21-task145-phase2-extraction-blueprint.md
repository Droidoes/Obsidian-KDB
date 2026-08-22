# Task #145 Phase 2 — Extraction Technical Blueprint

> **Status**: v0.2 — review absorbed (2026-08-21).
> **Decisions**: [`2026-08-21-task145-phase2-extraction-architecture.md`](2026-08-21-task145-phase2-extraction-architecture.md) (D-P2-1…D-P2-6, v0.3).
> **Parent**: [`2026-08-16-task145-kdb-fts-blueprint-v0.1.md`](2026-08-16-task145-kdb-fts-blueprint-v0.1.md) (§6 data model, §7.3, §9 Phase-2 gate).
> **Review**: [`2026-08-21-task145-phase2-extraction-blueprint-review-kimi.md`](2026-08-21-task145-phase2-extraction-blueprint-review-kimi.md).
> **Scope**: `extract.py` + `spans.py` + migration 3 + per-record salvage + the 3-model pool registration. No `cluster.py` (post-Phase-2), no ranker, no review-app changes.

---

## 1. What this pass builds

One structured LLM call per triggered article → **0..N `idea_mentions`** + **0..N `lesson_cards`**, each
grounded in a **proven evidence span**. The pipeline:

```
triggered article (accept rule ∪ exploration, D-P2-1)
   │  ledger.article_paragraphs → [(paragraph_id, body), …]   (article-global map)
   ▼
chunk (D-P2-4): whole body if ≤8,000 words, else paragraph-atomic ≤6,000-word chunks
   │
   ▼
build_prompt (extract.j2): numbered paragraphs + anchors contract
   │
   ▼
LLM json_mode (candidate model, min-reasoning, D-P2-6)
   │
   ▼
parse + salvage (per-record; D-P2-5)
   │
   ▼
spans.slice_span per field (anchors → source substring, D-P2-3)
   │  optional-field span fail → null field; required-core span fail → drop record
   ▼
ledger.commit_extraction_article (ONE txn for the whole article, all chunks) →
   extraction_runs + idea_mentions/lesson_cards + evidence_spans (+ raw output journal)
```

The hard invariant — **zero unvalidated spans in the ledger** (D10) — holds *by construction* (the stored
`exact_quote` is sliced from the source) **and is re-verified at the last write boundary** (`insert_span`
raises on a non-substring quote, §5.3).

## 2. Decisions (binding — see ADR for the full argument)

| ID | Decision |
|---|---|
| D-P2-1 | Trigger = accept rule ∪ §7.2 exploration sample; gate flags advisory (expectations only) |
| D-P2-2 | One combined call (ideas + lessons) |
| D-P2-3 | Model *points* (`paragraph_id` + head/tail anchors); Python *cuts*; fallback ladder |
| D-P2-4 | Full body ≤8k; chunked >8k tail at paragraph boundaries; never silently truncate |
| D-P2-5 | Slim required core; optional-nullable; required-core span failure = record-drop, optional = null |
| D-P2-6 | Bake-off over 7 candidates decides the default; gate locked to `deepseek-v4-flash` |

## 3. Package layout (additions only)

```
kdb_fts/
  extract.py          # prompt build + parse/salvage + run_extract runner (mirrors gate.py split)
  spans.py            # PURE: anchor validation + source slice + fallback ladder (no I/O)
  prompts/extract.j2  # versioned extraction prompt (EXTRACT_PROMPT_VERSION == filename stem)
  schema.py           # + migration 3
  ledger.py           # + triggered_articles / article_paragraphs / insert_* / commit_extraction_article
  cli.py              # + extract subcommand; status extension
  tests/
    test_spans.py     # pure slice/validation/ladder (+ property test)
    test_extract.py   # prompt/parse/salvage/runner/chunking
    test_schema.py    # + migration 3 pins
    test_ledger.py    # + access-function + span-proof pins
```

**Boundaries (unchanged, still enforced by `tools/tests/test_package_boundaries.py`):** `kdb_fts` imports
`common` only; `ledger.py` is the only module that opens `sqlite3`/creates dirs; every other file write goes
through `common.atomic_io`. `spans.py` is **pure** (no I/O, no `common` needed) — the anchor-slice math is
deterministic and trivially testable.

## 4. Data model — migration 3

```sql
CREATE TABLE extraction_runs (
    article_id      TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
    run_id          TEXT NOT NULL,
    schema_version  TEXT NOT NULL,     -- extraction schema version (D14)
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    status          TEXT NOT NULL,     -- ok|empty|failed|skipped  (call OUTCOME; exploration is a TRIGGER, not an outcome)
    expect_ideas    INTEGER NOT NULL,  -- gate-flag expectation, advisory (D-P2-1)
    expect_lessons  INTEGER NOT NULL,
    chunk_index     INTEGER NOT NULL DEFAULT 0,  -- 0-based chunk ordinal (0 = whole body for ≤8k, else first chunk)
    n_chunks        INTEGER NOT NULL DEFAULT 1,
    n_mentions      INTEGER NOT NULL DEFAULT 0,
    n_cards         INTEGER NOT NULL DEFAULT 0,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (article_id, run_id, chunk_index)
);

CREATE TABLE idea_mentions (
    mention_id       INTEGER PRIMARY KEY,
    article_id       TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
    run_id           TEXT NOT NULL,
    schema_version   TEXT NOT NULL,
    company          TEXT NOT NULL,          -- required core
    stance           TEXT NOT NULL,          -- required core; long|short|pass|watch|unclear
    thesis           TEXT NOT NULL,          -- required core
    ticker           TEXT,                   -- optional; only if exact string in source
    valuation_premise TEXT,                  -- optional-nullable
    catalyst         TEXT,
    risks            TEXT,
    horizon          TEXT,
    expires_on       TEXT,
    extraction_uncertainty REAL,             -- nullable 0..1
    idea_id          INTEGER,                -- nullable until cluster.py (post-Phase-2)
    dedupe_key       TEXT NOT NULL,          -- sha256(company\0stance\0thesis) — chunk dedupe (D12-safe: stance in key)
    UNIQUE (article_id, run_id, dedupe_key)
);

CREATE TABLE lesson_cards (
    card_id          INTEGER PRIMARY KEY,
    article_id       TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,
    run_id           TEXT NOT NULL,
    schema_version   TEXT NOT NULL,
    principle        TEXT NOT NULL,          -- required core
    context          TEXT,                   -- optional-nullable
    reusable_application TEXT,
    failure_mode     TEXT,
    lesson_type      TEXT,                   -- framework|mental-model|mistake-postmortem|process|risk|behavioral
    framework_id     INTEGER,                -- nullable until cluster.py
    dedupe_key       TEXT NOT NULL,          -- sha256(principle\0(context or '')) — context included so distinct cards don't collapse
    UNIQUE (article_id, run_id, dedupe_key)
);

CREATE TABLE evidence_spans (
    span_id          INTEGER PRIMARY KEY,
    article_id       TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE,  -- cascade: spans die with their article
    record_type      TEXT NOT NULL,          -- idea|lesson
    record_id        INTEGER NOT NULL,       -- mention_id|card_id (FK enforced in code — polymorphic)
    field            TEXT NOT NULL,          -- company|stance|thesis|ticker|…|principle|context|…
    paragraph_id     TEXT NOT NULL,
    exact_quote      TEXT NOT NULL           -- substring-proven; RE-VERIFIED at insert (D10, §5.3)
);
CREATE INDEX idx_spans_record ON evidence_spans(record_type, record_id);
```

Notes:

- **`extraction_runs` keyed `(article_id, run_id, chunk_index)`** — one row per *chunk call*, so a 3-chunk
  long article records 3 rows and its tokens/cost are per-chunk auditable. `status` is the call-outcome
  vocabulary (`ok|empty|failed|skipped`); **exploration is a trigger attribute** (known from the verdict before
  any call), not an outcome, so it lives on `gate_verdicts.exploration`, not in this enum.
- **`dedupe_key`** is the byte-identical chunk dedupe (D-P2-4), **not** the D12 cluster key. Idea key is
  `company\0stance\0thesis` (stance-inclusive → opposite stances never collide); lesson key is
  `principle\0(context or '')` so two cards sharing principle text but differing context survive.
- **`evidence_spans.article_id`** does two jobs: the DDL cascade (spans are orphans no more — they die with
  their article on any #151/#152-style cleanup) and the insert-time re-check (Finding 2).
- **`record_id` is polymorphic** (idea vs lesson) — a plain FK can't span two tables, so the pairing is
  enforced in code (the runner inserts the parent row, takes its PK, then inserts its spans).

## 5. Processing contracts

### 5.1 `spans.py` (pure — the D10 proof)

```python
# PURE — no I/O, no common import.
def validate_anchor(paragraph: str, anchor: str) -> int:
    """Occurrence count of anchor in paragraph (exact match)."""
    return paragraph.count(anchor)

def slice_span(paragraph: str, head: str, tail: str) -> str | None:
    """Slice the source span between two anchors; None if either anchor is not
    unique or the head does not precede the tail. Anchor-inclusive."""
    if not head or not tail:
        return None
    if paragraph.count(head) != 1 or paragraph.count(tail) != 1:
        return None
    hi = paragraph.index(head)
    ti = paragraph.index(tail)
    if ti < hi + len(head):            # tail must start at/after head ends
        return None
    return paragraph[hi:ti + len(tail)]  # anchor-inclusive span

def locate_quote(paragraph: str, quote: str) -> str | None:
    """Fallback ladder (D-P2-3). EVERY rung returns a VERBATIM substring of
    `paragraph` or None — the verbatim invariant is what D10 protects, and it
    holds on every rung. Rungs 2–3 take the FIRST match without a uniqueness
    check, so the LOCATION may bind to a different occurrence — accepted."""
    if paragraph.count(quote) == 1:
        return quote
    folded, offsets = _fold_with_offsets(paragraph)   # fold char-by-char, keep source offsets
    folded_q = _fold(quote)                            # NFKC + collapse whitespace
    idx = folded.find(folded_q)
    if idx != -1:
        candidate = _slice_by_offsets(paragraph, offsets, idx, len(folded_q))
        if _fold(candidate) == folded_q:               # re-verify after unmapping (NFKC is not length-preserving)
            return candidate
    return _fuzzy_snap(paragraph, quote)               # tolerant token-gap match; still returns source text
```

- The **anchor path is primary**; the fallback ladder runs only if the pilot shows anchors are flaky.
- **`_fold_with_offsets` + `_slice_by_offsets` are mandatory** — NFKC folding is *not* length-preserving
  (ligatures, full-width forms, compatibility expansions), so mapping a folded index back to a source offset
  by arithmetic is ill-defined. Fold char-by-char, record each folded index's source offset, and **re-verify**
  `_fold(candidate) == folded_q` before returning.
- The fuzzy rung never reintroduces unproven text — it returns a substring of the paragraph or `None`.

### 5.2 `extract.py` — prompt + parse + salvage

- **Constants:** `EXTRACT_PROMPT_VERSION = "extract_v1"` (filename stem `prompts/extract_v1.j2`),
  `MAX_BODY_WORDS = 8000` (D-P2-4), `CHUNK_TARGET_WORDS = 6000`, `STANCES = ("long","short","pass","watch","unclear")`,
  `LESSON_TYPES = ("framework","mental-model","mistake-postmortem","process","risk","behavioral")`.
- **`build_prompt(*, title, author, published_date, paragraphs) -> str`** renders numbered paragraphs —
  each prefixed `[p0001]` … `[pNNNN]` so the model can state a `paragraph_id` — with the anchors contract:
  for every substantive field, emit `paragraph_id` + `head_anchor` + `tail_anchor` (3–8 words, verbatim,
  **unique within that paragraph**). Single-pass `str.replace` (the #123 P10 rule). No truncation — chunking
  is the caller's job (D-P2-4: never silently truncate).
- **`parse_extraction(text) -> ExtractionResult`** (dataclass: `mentions: list[RawMention]`,
  `cards: list[RawCard]`, `downgraded: bool`). JSON-object envelope required (`ExtractParseError` otherwise);
  field-level salvage is per-record: unknown `stance` → drop mention; unknown `lesson_type` → null the field.
  `downgraded` is true when the model says "neither" (logged, not an error).
- **Salvage (D-P2-5, cross-ref D-P2-3):** required-core span fails → drop the whole mention/card; optional-field
  span fails → null that field, keep the record; a malformed mention leaves the sibling mentions/cards intact
  (per-record salvage, the #123 R1 posture).

### 5.3 `ledger.py` — access functions (the only sqlite writer)

```python
def triggered_articles(conn, *, accepted: bool = True) -> list[dict]:
    """Extraction trigger set (D-P2-1): latest verdict where
    (topic ∈ {investment, finance-econ} OR signal ≥ 0.75) OR exploration = 1.
    Returns article_id, title, canonical author, published_date, and the
    gate-flag expectations (extract_ideas/extract_lessons) for the audit."""
    # JOIN latest_verdicts on articles; ORDER BY article_id (deterministic)

def article_paragraphs(conn, article_id: str) -> list[tuple[str, str]]:
    """[(paragraph_id, body), …] in paragraph order — the extraction input AND
    the span-validation source of truth (article-global, not per-chunk)."""

def insert_extraction_run(conn, *, article_id, run_id, schema_version, model,
                          prompt_version, status, expect_ideas, expect_lessons,
                          chunk_index, n_chunks, n_mentions, n_cards,
                          input_tokens, output_tokens) -> None: ...

def insert_mention(conn, *, article_id, run_id, schema_version, company, stance,
                   thesis, ticker=None, valuation_premise=None, catalyst=None,
                   risks=None, horizon=None, expires_on=None,
                   extraction_uncertainty=None) -> int | None: ...   # None on dedupe-ignore

def insert_card(conn, *, article_id, run_id, schema_version, principle, context=None,
                reusable_application=None, failure_mode=None, lesson_type=None) -> int | None: ...

class SpanProofError(ValueError):
    """A span whose exact_quote is not a substring of its source paragraph."""

def insert_span(conn, *, article_id, record_type, record_id, field,
                paragraph_id, exact_quote) -> None:
    """Insert one evidence span — and RE-VERIFY the D10 proof at the last write
    boundary (fail-closed, structural — not comment-grade)."""
    row = conn.execute(
        "SELECT body FROM paragraphs WHERE article_id = ? AND paragraph_id = ?",
        (article_id, paragraph_id),
    ).fetchone()
    if row is None or exact_quote not in row[0]:
        raise SpanProofError(f"{record_type}:{field} — quote not a substring of {paragraph_id}")
    conn.execute("INSERT INTO evidence_spans (article_id, record_type, record_id, field, "
                 "paragraph_id, exact_quote) VALUES (?,?,?,?,?,?)",
                 (article_id, record_type, record_id, field, paragraph_id, exact_quote))

def commit_extraction_article(conn, *, article_id, run_id, schema_version, model,
                              prompt_version, statuses: list[dict],
                              mentions: list[dict], cards: list[dict],
                              spans: list[dict]) -> None:
    """ONE BEGIN…COMMIT for an article's WHOLE extraction (all chunks) — atomic
    per-article (resume-fix (c)). Rollback on any error → the article re-runs on
    resume; no partial-article state can exist."""
    # BEGIN → insert_extraction_run × n_chunks → insert_mention/card/span → COMMIT

def latest_extractions(conn) -> list[dict]:
    """Routing view for the audit: per (article, latest run) → status + counts."""
```

### 5.4 `run_extract` (runner) + chunking

```python
def chunk_paragraphs(paragraphs: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Greedy paragraph-atomic grouping ≤ CHUNK_TARGET_WORDS; a single paragraph
    longer than the target is its own chunk (never split). 0-based chunks."""
    # paragraphs are the atomic evidence unit → no span is ever split (D-P2-4)

def run_extract(conn, *, state_root, run_id, model_id="deepseek-v4-flash",
                max_n=None, dry_run=False, call_fn=call_model) -> dict:
    # resolve spec → todo = ledger.triggered_articles(conn) → for each article:
    #   if already_extracted(conn, article_id, spec, EXTRACT_PROMPT_VERSION): skip   # article-level resume — valid b/c commit is atomic
    #   paragraphs = ledger.article_paragraphs(conn, aid)          # article-global map
    #   chunks = [paragraphs] if total ≤ MAX_BODY_WORDS else chunk_paragraphs(paragraphs)
    #   pending = {runs: [], mentions: [], cards: [], spans: []}    # accumulate in memory
    #   for ci, chunk in enumerate(chunks):                        # ci 0-based
    #       prompt = build_prompt(..., paragraphs=chunk)
    #       resp = _call_once(spec, prompt, call_fn)               # min-reasoning (spec.extra_body)
    #       result = parse_extraction(resp.text)   (2 attempts → journal failed)
    #       for mention in result.mentions:  salvage + spans.slice_span per field
    #           (span validation against the ARTICLE-GLOBAL paragraph map — a model citing a
    #            paragraph outside its chunk resolves or fails deterministically)
    #           → pending.mentions.append(...) + pending.spans.append(...) per proven field
    #       (same for cards); pending.runs.append(chunk stats)
    #   if not dry_run:
    #       ledger.commit_extraction_article(conn, ...)            # ONE txn, all chunks
    #       raw+salvaged output per chunk → runs/<run_id>/extractions/<article_id>/<ci>.json (atomic_io)
    # stats: {extracted, empty, failed, skipped, mentions, cards, input_tokens,
    #         output_tokens, cost_usd, dropped_records, dropped_fields}
```

**Resume is article-level and correct *because* the commit is atomic per-article** (resume-fix (c), Finding 3):
a crash mid-article leaves zero rows, so "has any `extraction_runs` row at `(schema_version, model,
prompt_version)` → skip" can never strand a half-extracted article. Re-extraction = bump `extract_v1` or the
schema (D14).

### 5.5 CLI additions

```
kdb-fts extract [--max N] [--model M] [--dry-run] [--state S]
kdb-fts status   # extended: extraction counts by model/prompt_version, cost-to-date, dropped-records
```

## 6. Model pool registration (3 additions)

| id | provider | api_call_type | endpoint | key env | ctx | max out | $ in/out | thinking | extra_body |
|---|---|---|---|---|---|---|---|---|---|
| `gpt-5.6-luna` | openai | openai_compat | null | `OPENAI_API_KEY` | 1050000 | 128000 | 0.20/1.20 | *(none)* | `{"reasoning_effort":"low"}` |
| `qwen3.8-max` | alibaba-sgp | openai_compat | *(same as qwen3.7-flash)* | `QWEN_SGP_API_KEY` | 1000000 | 65536 | 2.0/6.0 | enabled | `{"reasoning_effort":"low"}` |
| `glm-5.3` | zai | openai_compat | `https://api.z.ai/api/paas/v4` | `ZAI_API_KEY` | 1000000 | 128000 | 1.4/4.4 | enabled | `{"reasoning_effort":"low"}` |

**Reasoning mechanics (D-P2-6 "minimum reasoning") — per-provider, never guessed:**

- **`gpt-5.6-luna`** — OpenAI has **no verified disable param in `_THINKING_DISABLE_EXTRA_BODY`**, so use
  `extra_body.reasoning_effort = "low"` (supports `none|low|medium|…`); mirror `gpt-5.4-mini`'s
  `"temperature": null` (reasoning-family models 400 on non-default temperature).
- **`qwen3.8-max`** — keep thinking **on** (`thinking: enabled`, so the pool's alibaba-sgp
  `enable_thinking: False` is NOT sent) and trim cost via `extra_body.reasoning_effort = "low"` (thinking
  tokens bill as output, so effort is the cost lever — apidog).
- **`glm-5.3`** — **forced thinking, cannot be disabled** (GLM-5.3 overview + thinking-mode docs). Its
  `thinking.type` accepts **only `enabled`**; effort is a **sibling** param `reasoning_effort ∈ {low, high,
  max}` (default `max`). So the entry sets `thinking: enabled` (which keeps the pool's `zai` disable-param
  **unsent**) and `extra_body: {"reasoning_effort": "low"}`. **Gotcha (migration notice):** sending
  `thinking.type: "disabled"` to `glm-5.3` **fails the request** — which is exactly why the entry must NOT
  inherit the pool's default `thinking: disabled`.

⚠️ **Pre-bake-off checks (ADR §6):** ping the `glm-5.3` endpoint at `https://api.z.ai/api/paas/v4` (base URL
confirmed from the thinking-mode example; API *availability* is still unconfirmed — sources disagree on whether
it's publicly live); be prepared to run the bake-off with 6 candidates if GLM is down. Keep the model-ID
confirmation receipt with the pilot journal.

## 7. Pilot — two stages (ADR §5, D-P2-6)

1. **Bake-off** — freeze a **20-file probe** (idea-only / lesson-only / both / long-tail), run it through
   all 7 candidates with the *same* `extract_v1` + schema + `spans.py`. Per model, compute: span-validity
   (hard gate 100% on landed), anchor-dropout rate, field-fill, flag-divergence, cost-per-landed-record,
   plus Joseph's audit of a handful of records. **Decision rule:** clear the span gate, win on
   coverage+quality at acceptable cost.
2. **100-file eligible-set audit — on the winner only** (the blueprint §9 Phase-2 gate), with the 95
   flag-disagreement articles **oversampled additively** (ADR D-P2-1).

## 8. Phased delivery & TDD gates

Sequential; each gate is failing-tests-first. Live-LLM gates are Joseph-fired, never CI.

- **P2.0 — migration 3 + ledger access.** `extraction_runs`/`idea_mentions`/`lesson_cards`/`evidence_spans`;
  `triggered_articles`, `article_paragraphs`, the `insert_*` functions, `commit_extraction_article`,
  `latest_extractions`.
  *Gate:* `SCHEMA_VERSION == 3`; `triggered_articles` resolves on the **fixture** (293/33 split — the durable
  pin) and is *manually* confirmed at 326 on the real ledger (a one-time check, NOT a standing test — the
  corpus grows with every feeder run); the `evidence_spans` cascade + insert re-check round-trip on a fixture.
- **P2.1 — `spans.py` + `extract_v1.j2` + pure parse/salvage.** Anchor validation + slice + fallback ladder;
  the prompt template; `parse_extraction` + per-record salvage (no LLM, no DB).
  *Gate:* thesis fixture → ≥1 mention with a source-sliced span; political fixture → 0 mentions; quote-not-
  in-source → span refused; required-core fail → record dropped, optional fail → field nulled.
- **P2.2 — runner + chunking + CLI.** `run_extract`, `chunk_paragraphs`, `kdb-fts extract`, status extension.
  *Gate:* >8k fixture chunks paragraph-atomically ≤6k and dedupes byte-identical records across chunks;
  `--dry-run` commits nothing; resume skips fully-extracted articles only; downgrade-to-`neither` is journaled.
- **P2.3 — model pool registration.** The 3 new entries + their reasoning config.
  *Gate:* each resolves via `resolve_models_json`; `gpt-5.6-luna`/`qwen3.8-max`/`glm-5.3` all round-trip a
  live smoke call at min-reasoning (Joseph-fired; glm may be a 6-candidate fallback).
- **P2.4 — pilot.** The two-stage bake-off → winner → 100-file audit (§7).
  *Gate:* span-validity 100% on landed records; zero-idea rate on the political holdout reported; a bake-off
  decision produced and recorded in `docs/TASKS.md` + the ADR.

## 9. Test plan (TDD-first; system tests over mocks)

| Area | Must fail before code exists |
|---|---|
| Migration 3 | `SCHEMA_VERSION==3`; four tables exist; `migrate` idempotent + txn-wrapped (broken DDL rolls back, version unchanged); `evidence_spans` cascade deletes on article delete |
| Trigger set | `triggered_articles` = accept-rule ∪ exploration, pinned on a **fixture** (293/33 split — durable; the 326 real-ledger check is a manual gate step, not a committed test) |
| Anchors | `validate_anchor` counts 0/1/2; `slice_span` returns `None` on non-unique/mis-ordered anchors and the substring on valid ones |
| Fallback ladder | exact → folded → fuzzy, each rung returns a verbatim substring or `None`; **property test** `result is None or result in paragraph` over randomized paragraph/quote pairs, applied to `_unmap` AND `_fuzzy_snap` |
| Parse | political → 0 mentions (D11); thesis → mention with span; unknown `stance` → dropped; `ticker` only when exact string present |
| Salvage | required-core span fail → record dropped; optional span fail → field nulled; one bad mention doesn't sink its siblings |
| Chunking | paragraph-atomic; ≤6k/chunk; a >6k paragraph is its own chunk; byte-identical dedupe via `dedupe_key` (opposite stances never collide; lessons dedupe on `principle\0context`) |
| Runner | `--dry-run` leaves `idea_mentions` unchanged; article-level resume skips fully-extracted only; per-chunk journal + raw-output archive written atomically |
| Spans→ledger | a fabricated quote (not a source substring) raises `SpanProofError` at `insert_span` — **enforced structurally, not by comment** |
| Model pool | 3 new ids resolve; reasoning config lands in `spec.extra_body` (gpt effort; **qwen `enable_thinking` ABSENT** + effort; glm effort) |
| Boundary | `spans.py` has no I/O; `extract.py` imports `common` only; `ledger.py` remains the sole sqlite opener (existing guard) |

## 10. Cost & attention budget

- Extraction over the 326-article denominator ≈ **~$1.1** at `deepseek-v4-flash` prices (887,555 accepted
  words + exploration tail); the 100-file audit ≈ 35% of that.
- **Bake-off:** 7 models × 20 files < $1 total (the pricier candidates run on 20 files only).
- **Joseph's attention:** audit a handful of records per model in the bake-off (~1–2 hrs), plus the
  political-holdout read. That is the binding budget, unchanged.

## 11. Out of scope (this pass)

`cluster.py` (mentions→ideas, cards→frameworks) — post-Phase-2; ranker/decay/queues (Phase 3); the review-app
idea/lesson/outcome queues (Phase 4); `kdb-fts rebuild`; embeddings; re-gating the corpus with another model.

## 12. Open items / follow-ups (carried from ADR §6)

1. Workflow doc §11 — tag `cluster.py` post-Phase-2, drop from planned modules.
2. Blueprint §14 — correct the stale 922-mix line (607 verdicts; investment 195).
3. Confirm `glm-5.3` API **availability** before P2.3 (base URL and `reasoning_effort` shape are confirmed — §6).
4. Confirm the exact prompt-template filename convention (`extract_v1.j2` vs the gate's `.md`) during P2.1.

## 13. Review amendments (v0.2, 2026-08-21 — Kimi)

Absorbed from the blueprint review:

1. **`evidence_spans.article_id` + cascade** — spans are no longer orphaned on article deletion (Finding 1).
2. **D10 re-verified at insert** — `insert_span` raises `SpanProofError` on a non-substring quote; enforcement
   is structural, not comment-grade (Finding 2).
3. **Per-article atomic commit** (`commit_extraction_article`, one txn across all chunks) — the article-level
   resume rule is now correct, and a crash mid-article strands nothing (Finding 3, option (c)).
4. **Cross-chunk dedupe consequences stated** — lost corroborating spans is an accepted tradeoff; the lesson
   `dedupe_key` now includes `context` so distinct cards don't collapse (Finding 4).
5. **`spans.py` fallback hardened** — `_fold_with_offsets` + `_slice_by_offsets` (NFKC is not length-preserving)
   with a re-verify step; first-match-without-uniqueness on rungs 2–3 stated as accepted (Finding 5).
6. **Chunk convention fixed** — 0-based `chunk_index` everywhere; span validation against the article-global
   paragraph map, not the chunk's (Finding 6).
7. **Nits** — `insert_mention`/`insert_card` return `int | None`; `status` drops `exploration` (it's a trigger,
   not an outcome); the durable trigger test is a fixture pin (326 is a manual gate step); the model-pool test
   asserts `enable_thinking` is *absent* for `qwen3.8-max`.
