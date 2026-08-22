# Review — Task #145 Phase 2 Extraction Blueprint v0.1 (Kimi, 2026-08-21)

> **Subject**: [`2026-08-21-task145-phase2-extraction-blueprint.md`](2026-08-21-task145-phase2-extraction-blueprint.md)
> **Method**: every verifiable claim checked against the live ledger (`~/Obsidian/KDB/fts/ledger.sqlite`),
> `common/model_pool.py`, `common/model_route.py`, `kdb_fts/gate.py`, and the blueprint's own pseudo-code.
> Review aimed at the six load-bearing areas in the hand-off brief.

## Verdict

Blueprint is faithful to the ADR, the trigger-set fix (326 = 293 + 33) is now correct and **verified against the
live ledger**, and the model-registration semantics are right. I found **two material data-model/runner issues
the brief didn't list**, plus answers to all six briefed questions. Nothing requires a re-architecture — all
fixes are local to migration 3 + the runner contract.

---

## Verified correct (no action)

- **Triggered set = 326.** Live ledger: accept-rule 293, exploration 36, union **326** (3 exploration marks
  sit on accepted articles). The P2.0 gate number is right. (Caveat below about pinning it as a standing test.)
- **Model registration vs `model_pool.py` semantics — all three entries behave as designed:**
  - `resolve_models_json` (model_pool.py:144-152): `thinking: "enabled"` → the provider's disable param is
    **not sent**; explicit `extra_body` keys are merged over (and win conflicts). So `qwen3.8-max` will NOT
    receive alibaba-sgp's `enable_thinking: false`, and `glm-5.3` will NOT receive zai's
    `{"thinking": {"type": "disabled"}}` — the ADR's gotcha is correctly handled. ✓
  - `gpt-5.6-luna`: openai has no entry in `_THINKING_DISABLE_EXTRA_BODY`, so `thinking` (absent → default
    `"disabled"`) is a no-op there; `extra_body.reasoning_effort: "low"` is the only signal sent. ✓
  - `model_route.validate_provider_identity` has **no closed provider set** — `"zai"` passes as-is
    (canonical = non-empty, unpadded). Gate 1 requires the three route keys present; `endpoint: null` is legal
    for `openai_compat`. All three entries validate. ✓
- **`paragraphs` table supports the design**: PK `(article_id, paragraph_id)`, `body TEXT`, cascade on article
  delete — so `article_paragraphs` works and a ledger-level span re-check is cheap (see Finding 2).
- **Resume pattern matches `run_gate`'s precedent** (`ungated_articles` keyed on model + prompt_version) —
  consistent, with one chunk-granularity gap (Finding 3).

---

## Findings

### 1. `evidence_spans` leaks on article deletion — no cascade path exists (material)

`evidence_spans` declares **no `REFERENCES` clause at all** (the polymorphic `record_id` can't be a DDL FK —
correct). But the consequence is unhandled: on the next #151/#152-style cleanup, `articles` deletion cascades
to `idea_mentions`/`lesson_cards` while their `evidence_spans` rows **stay behind as orphans** — dangling
`record_id`s and quotes pointing at deleted paragraphs. The blueprint that made gate verdicts cascade-clean
(`ON DELETE CASCADE` on `gate_verdicts`) is exactly the discipline being dropped here.

**Fix (one column kills both Finding 1 and Finding 2):** add
`article_id TEXT NOT NULL REFERENCES articles(article_id) ON DELETE CASCADE` to `evidence_spans`. The DDL
cascade then works (spans die with their article regardless of record type), and the column enables the
insert-time re-check below.

### 2. D10 enforcement: comment-only at the ledger is not faithful enough to "insert is refused" (brief Q2)

`insert_span`'s contract is a *comment* ("ONLY ever called with an exact_quote returned by
spans.slice_span/locate_quote"). This is the same failure family as the ADR's D-P2-3/D-P2-5 collision and the
write-boundary guard's own rationale ("drifts silently if left to convention"). The runner is the *first*
enforcement point; the ledger is the *last* write boundary, and `ledger.py` is already defined as the only
sqlite writer — the trust boundary belongs there.

**Recommendation: re-verify in `insert_span`, fail-closed.** With `article_id` added (Finding 1), it's one
indexed PK lookup + a substring assert:

```python
body = conn.execute("SELECT body FROM paragraphs WHERE article_id=? AND paragraph_id=?",
                    (article_id, paragraph_id)).fetchone()
if body is None or exact_quote not in body[0]:
    raise SpanProofError(...)   # insert IS refused, structurally
```

Cost is trivial (indexed SELECT + substring per span). It covers every future caller — cluster.py repairs,
manual tooling, the Phase-4 app — not just today's runner. The runner-level check stays (it's where salvage
decisions are made); the ledger check is the invariant's structural home. Given D10 is *the* load-bearing
guarantee of the whole system ("zero unvalidated spans in the ledger"), comment-grade enforcement is the wrong
grade.

### 3. Resume granularity: a partially-chunked article freezes forever (material for the 22-article tail)

`extraction_runs` is chunk-keyed `(article_id, run_id, chunk_index)`, but §5.4's resume rule is
article-level: "an article already having an `extraction_runs` row at the same (schema_version, model,
prompt_version) is skipped." Sequence: 3-chunk article, chunk 0 commits, call dies on chunk 1 → re-run sees
the chunk-0 row, **skips the article, chunks 1–2 never extracted, silently.** This hits precisely the
highest-value long-tail the chunking exists for.

**Fix options (pick one, state it in the blueprint):**
- *(a) resume at chunk granularity* — skip only `(article_id, chunk_index)` pairs already present;
- *(b) article-complete predicate* — skip only when `COUNT(rows) == n_chunks` for the article;
- *(c) per-article transaction* — all chunks of one article commit atomically or not at all (simplest; the
  tail is 22 articles, so retry cost is bounded).

I lean (c) for simplicity, (a) if you want crash-resilient progress on the 45k-word outliers.

### 4. Cross-chunk dedupe: correct for dupes, but state the two collapse consequences (brief Q4)

`dedupe_key = sha256(company\0stance\0thesis)` + `UNIQUE(article_id, run_id, dedupe_key)` + `INSERT OR IGNORE`
is the right mechanism, and D12 is safe (stance is *in* the key, so opposite stances never collide). Two
consequences worth one sentence each:

- **Lost corroborating spans:** a byte-identical mention re-emitted in a later chunk is ignored — including
  its *spans*, so the surviving record keeps only its first chunk's evidence. Acceptable (corroboration within
  one article is low-value), but it should be a stated tradeoff, not a surprise.
- **`lesson_cards` key is thinner:** `sha256(principle)` alone collapses two genuinely distinct cards that
  share principle text but differ in `context`/`reusable_application`. Consider `sha256(principle\0context)`
  or accept-and-document; either way, decide deliberately.

### 5. `spans.py` ladder: the invariant holds, but `_unmap` needs an offset map, not reconstruction (brief Q3)

- `slice_span` pseudo-code is correct (uniqueness + ordering + anchor-inclusive slice; `ti < hi + len(head)`
  rejects overlap). ✓
- `locate_quote` rung 1 requires `count == 1`; rungs 2–3 take the *first* folded/fuzzy match with no
  uniqueness check. The verbatim invariant survives (the returned text is always a source slice), but the
  span's **location** can silently bind to the wrong occurrence. State that as accepted behavior.
- **`_unmap` is the real hazard:** NFKC folding is *not* length-preserving (ligatures, full-width forms,
  compatibility expansions), so mapping a folded index back to original offsets by arithmetic is ill-defined.
  The fold must be built **with a source-offset map** (fold char-by-char, record offsets), making `_unmap` a
  lookup. And after unmapping, **re-verify**: `fold(candidate) == folded_q` before returning; else `None`.
- The test-plan row "each rung returns a verbatim substring or `None`" is the right pin — strengthen it to a
  property test: `result is None or result in paragraph`, over randomized paragraph/quote pairs, applied to
  both `_unmap` and `_fuzzy_snap` outputs.

### 6. Chunking edge cases (brief Q4) — mostly clean, two nits

- Paragraph-atomic ≤6,000 with the >target paragraph as its own chunk: correct, and since `paragraph_id`s are
  article-global, spans validate identically. One clarification: state that span validation runs against the
  **article-global paragraph map** (not the chunk's), so a model citing a paragraph outside its chunk still
  resolves — or fails the lookup and drops — deterministically.
- **Convention clash:** the schema comment says `chunk_index`: "0 = whole body; 1..n = chunked tail," but the
  §5.4 pseudo-code uses `enumerate(chunks)` (0-based for chunked articles too). Pick one — 0-based everywhere
  is the least surprising — before P2.0 pins it in a test.

---

## Nits

- `insert_mention` is annotated `-> int` but returns `None` on dedupe-ignore — contract should be
  `-> int | None`.
- `extraction_runs.status` includes `exploration` in its vocabulary, but exploration is a *trigger* attribute
  (known from the verdict before any call), not a call outcome. An exploration article that lands records is
  `ok` or `exploration`? Either move exploration to its own column or drop it from the status enum.
- **P2.0 gate** pins "exactly 326 on the real ledger" — right as a one-time gate check, wrong as a standing
  test (the corpus grows with every feeder run; the number will rot). The §9 fixture pin (293/33 split on a
  fixture) is the durable one — make sure the committed test is the fixture, and the 326 check is a manual
  gate step.
- §9 test-plan row says "(gpt effort, **qwen disable**, glm effort)" — for `qwen3.8-max` the assertion is that
  the alibaba-sgp `enable_thinking: false` is **absent** (thinking stays *enabled*). As written, the
  parenthetical describes the opposite of §6's design.
- §10 cost: ~$1.1 for 326 articles is consistent with the ADR's ~$1 × 326/293. ✓

## Bottom line

Ship-shape after four local fixes: (1) add `article_id` + cascade to `evidence_spans`; (2) move the D10
re-check into `insert_span` (fail-closed); (3) pick a chunk-granular or per-article-transaction resume rule;
(4) the `_unmap` offset-map + re-verify requirement. Findings 1–3 are the ones I'd want folded into v0.2
before the TDD plan.
