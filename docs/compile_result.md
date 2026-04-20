# `compile_result.json` — Role, Schema, and Semantics

**Companion to**: `kdb_compiler/schemas/compile_result.schema.json` · `manifest.schema.md` · `CODEBASE_OVERVIEW.md` §5

Consolidates the Q&A walkthrough from 2026-04-20: (1) what the `pages` array and its key fields mean, and (2) what role `compile_result.json` actually plays in the pipeline.

---

## Mental Models at a Glance

Two framings carry most of the intuition in this doc. Read these first, then the sections below fill in the mechanics.

**🏃 The baton (what `compile_result.json` *is*):**

> `compile_result.json` is **the baton** passed from the compile stage to the apply stage. The baton is valuable mid-race; afterward it's just the last one that got passed. The real race history lives in `runs/` and `llm_resp/`.

**🔗 The page intent (what each entry in `pages[]` *says*):**

> *"Here's a slug-keyed node for the wiki graph. It's of this type (`page_type`). Here's its content (`body`). Here's what it points at (`outgoing_links`). Here's how sure I am (`confidence`). Python — you handle the graph bookkeeping, frontmatter, paths, timestamps, and filesystem."*

That second one is the **D8 boundary** in one sentence: LLM emits semantic intent; Python owns everything else.

---

## 1. What `compile_result.json` Does

### The one-sentence mental model

> `compile_result.json` is **the baton** passed from the compile stage to the apply stage. The baton is valuable mid-race; afterward it's just the last one that got passed. The real race history lives in `runs/` and `llm_resp/`.

It is not purely a log. It is a **pipeline handoff artifact** with three roles, in order of importance.

### Role 1 — Contract between compile and apply (primary)

In `kdb_compiler/kdb_compile.py`, everything downstream of the compile step is a pure function of `compile_result.json` + prior manifest:

```
validate_compile_result.validate(cr)                                  # schema + semantic gate (D8)
manifest_update.build_manifest_update(prior, scan_dict, cr, ctx)      # compile_result drives the diff
patch_applier.apply(…, next_manifest, …)                              # writes pages derived from compile_result
manifest_update.write_outputs(…)                                      # persists manifest + journal
```

Every page written to `KDB/wiki/` and every row in `manifest.json` is derived from `compile_result.json`. A malformed compile_result aborts the run with **zero** vault writes.

### Role 2 — Replay / staging seam (dual-mode)

`kdb_compile.py:82–96` branches on the file's presence:

| Branch | Condition | Behavior |
|---|---|---|
| **1 — fixture-backed** | `state/compile_result.json` exists **and** its `run_id` matches the fresh scan's `run_id` | Use file directly — no LLM call |
| **2 — live compile** | File missing, or `run_id` mismatch (stale) | Invoke `compiler.run_compile`; overwrite the file on disk |

The `run_id` match requirement prevents stale leftover files from being accidentally replayed. Branch 1 only activates with operator intent (you staged a file whose run_id matches *this* scan). This is what lets M1.7 test the orchestrator end-to-end with hand-crafted JSON and zero API cost.

### Role 3 — Last-run record (narrow)

After a live compile, the file sits on disk reflecting that run's LLM output. But:

- **Overwritten every live run.** Only the latest lives at `state/compile_result.json`. No history.
- **NOT the audit trail.** History lives elsewhere.

| Artifact | Role | Retention |
|---|---|---|
| `state/compile_result.json` | Last LLM output — input to apply stage | **Overwritten each run** |
| `state/runs/<run_id>.json` | Journal — what *changed* this run (deltas, tombstones, log_entries) | Kept per run |
| `state/llm_resp/<run_id>/*.json` | Per-call telemetry (tokens, latency, validation flags) | Kept per run |

If someone asks "what happened on run X three weeks ago" — read `runs/<run_id>.json`, not `compile_result.json`.

### Why this design (D7 / D15)

The split between volatile handoff and durable journal is intentional:

- Keeps the apply stage **purely a function of compile_result + prior manifest** — no hidden history coupling.
- Journal-then-pointer writes (D15) make `runs/<run_id>.json` the crash-safe per-run record.
- `compile_result.json` stays small and single-purpose.

---

## 2. Schema Walkthrough — the `pages` Array

Each `compiledSource` entry contains `pages[]` — the LLM's set of page intents for one source. Minimum 1 page (the summary); usually 1 summary + N concepts + M articles.

Running example: **case01** (`kdb_compiler/tests/fixtures/eval/case01_minimal_summary/stored_response.txt`) — the transformer source:

```json
{
  "source_id": "KDB/raw/transformer.md",
  "summary_slug": "transformer-architecture",
  "pages": [
    {
      "slug": "transformer-architecture",
      "page_type": "summary",
      "title": "Transformer Architecture",
      "body": "… replaces recurrence with [[self-attention]] …",
      "outgoing_links": ["self-attention"],
      "confidence": "high"
    },
    {
      "slug": "self-attention",
      "page_type": "concept",
      "title": "Self-Attention",
      "body": "… replacing [[transformer-architecture]] …",
      "outgoing_links": ["transformer-architecture"],
      "confidence": "high"
    }
  ]
}
```

Each page intent is a **full-body replacement** (D18) — no diffs, no patches. The LLM says "this is what this page should be, in full." Python prepends frontmatter and writes the file.

Required keys per page: `slug`, `page_type`, `title`, `body`. Optional: `status`, `supports_page_existence`, `outgoing_links`, `confidence`.

### `page_type` — the *kind* of page

Enum, exactly **three** LLM-authorable values:

| Value | Purpose |
|---|---|
| `summary` | One per source — the "what is this source about" page. Pointed to by the compiledSource's `summary_slug`. |
| `concept` | A reusable idea extracted from the source (e.g. `self-attention`). Linked to by multiple summaries. |
| `article` | Longer-form, synthesized writeup. Rarer. |

**What's NOT in the enum** (and why it matters): `index` and `log`. Those are Python-authored from manifest data (D19). The LLM is forbidden from emitting them — the schema enforces it. So `page_type` is really "LLM-authorable page types" only.

In case01: `transformer-architecture` is `summary`, `self-attention` is `concept`. Clean split.

### `outgoing_links` — the wiki graph, LLM side

An array of **slugs** (not paths, not URLs, not `[[wikilink]]` syntax) that this page's body links to.

Two hard contracts encoded in the schema description:

1. **Must appear in `body` as `[[slug]]`.** If `outgoing_links: ["self-attention"]` is declared, the body must contain `[[self-attention]]`. The validator cross-checks this.
2. **Python reconciles `incoming_links_known` from these.** The LLM only declares what goes *out*. It never sees or edits who links *in*. Python walks all pages' `outgoing_links` and mechanically builds each page's `incoming_links_known` field in the manifest. This is the D8 boundary — LLM owns semantic intent (what to link), Python owns bookkeeping (who linked me).

In case01 you see a bidirectional link declared naturally on both sides:

- `transformer-architecture` → `outgoing_links: ["self-attention"]` + body contains `[[self-attention]]`
- `self-attention` → `outgoing_links: ["transformer-architecture"]` + body contains `[[transformer-architecture]]`

The LLM never needs to think "am I linked from X" — it just emits its own outgoing edges.

### `confidence` — self-assessment enum

Three-level enum: `low` · `medium` · `high`. Deliberately coarse. Rationale: LLMs are bad at fine-grained probability; honest buckets beat false precision.

**What it is used for today**: signal captured in the run journal (`state/runs/<run_id>.json`) as log entries. Low-confidence decisions are recorded for human review. Also input for future quality/prioritization logic (e.g., "show me all low-confidence pages in this run").

**What it is not used for today**: gating writes. A `confidence: "low"` page still gets written. The design choice: let the LLM be honest and route uncertainty into observability (log entries, filter queries) rather than blocking the pipeline.

In case01 both pages are `"high"` — trivial, well-grounded summaries of a well-known paper.

---

## 3. How It All Composes

One mental model for a page intent:

> *"Here's a slug-keyed node for the wiki graph. It's of this type (`page_type`). Here's its content (`body`). Here's what it points at (`outgoing_links`). Here's how sure I am (`confidence`). Python — you handle the graph bookkeeping, frontmatter, paths, timestamps, and filesystem."*

That is the **D8 boundary** in one sentence: LLM emits semantic intent; Python owns paths, timestamps, versions, incoming-link reconciliation, and all persistence.

---

## 4. Quick-Reference — Where Things Live

| Question | File to read |
|---|---|
| "What did the LLM want written this run?" | `state/compile_result.json` |
| "What did the pipeline actually change this run?" | `state/runs/<run_id>.json` |
| "Was the LLM call healthy (tokens, latency, parse_ok)?" | `state/llm_resp/<run_id>/*.json` |
| "What's in the wiki right now?" | `state/manifest.json` + `wiki/**/*.md` |
| "Run history (what happened on run X)?" | `state/runs/<run_id>.json` |
