# #123 v0.16 — implementation concurrence brief

Date: 2026-08-02 · Task **#123** · Reviewers: **codex**, **kimi** · Suite **3,059 passed, 34 skipped**

> **Output guardrail — read before starting.** Write your review to a **new file of your own**
> under `docs/superpowers/specs/`. Do **not** modify, reformat, stage, commit or delete any other
> file in this repository, and do not run the test suite in a way that writes fixtures or artifacts.
> Read freely; write only your own review file.

## 0. What this is, and what it is not

This is an **informational brief**, not a request for redesign. The v0.16 simplification amendment
(`2026-08-02-task123-simplification-amendment.md`, D-123-A…F) is **owner-ratified and binding**, and
so is the principle behind it — Joseph, 2026-08-02: *"the chief objective is to simplify, simplify
and simplify — by removing complexity, we are making our architecture/design/code stronger."*

The implementation is complete and green. **Nothing is committed.** What we want is concurrence that
the code matches the ratified decisions and that the consequences below are correctly handled.

If you find a genuine defect — a broken invariant, an unhandled path, a false claim — say so and we
will act on it. But arguments of the form *"this mechanism should be retained for safety"* about a
mechanism the amendment deleted on measured evidence are re-litigating a settled owner decision, and
will be recorded rather than actioned. The bar for reopening is new evidence, not restated caution.

## 1. The two consequences the amendment did not anticipate

**Read these first.** They are the parts where an outside check is worth most, because they were
discovered during implementation rather than reasoned about during ratification.

### 1.1 `M` = 150 forced thin's OUTPUT allowance up

D-123-A reasoned that `M` "is no longer an input to any guarantee." That is true of the **input**
budget and **false of the output wire.** Thin's response is a retained-slug list bounded by
`M × MAX_SLUG_LEN`, so:

| | was | now |
|---|---:|---:|
| thin exact max serialization | 12,314 B | **18,464 B** |
| `VISIBLE_OUTPUT_ALLOWANCE_THIN` | 13,000 | **20,000** |
| `PROVIDER_MAX_TOKENS_THIN` | 29,000 | **36,000** |

18,464 B went straight through the old 13,000 allowance. D8(iii)'s ratified rule is that the
allowance **derives** from the exact maximum, so it follows `M` rather than being re-decided; 20,000
keeps roughly the relative headroom 13,000 gave 12,314 (8.3% vs 5.6%). 36,000 is still far under the
pool's smallest `max_output_tokens` (gemini-3.6-flash, 65,536), asserted at route resolution.

**What we want checked:** that treating this as a derived consequence rather than a new decision is
right, and that 20,000 is the correct reading of the derivation rule.

### 1.2 `FAT_PREFLIGHT_BUDGET` changed shape, not merely meaning

The amendment (§7.1) said the terminal narrows to *"not even one entity fits."* In practice it is
stronger than that: **a small context window can no longer reach the terminal at all.** Thin now
reserves 36,000 output tokens, so any route that passes thin's pre-flight has ample room for a fat
entity. The only thing that still reaches it is a **single oversized body**.

Concretely, the old branch-table rows drove it with 90 moderate bodies against a 45,000-token
window. That window no longer fits *thin* (0.8 × 45,000 = 36,000 = thin's whole reserve), and the
fill would in any case simply seat fewer bodies and succeed — correctly. The rows are rebuilt on a
60,000 window (88,000 B fat allowance) and one ~120 kB body.

**What we want checked:** whether the terminal remaining reachable *only* by an oversized body is
acceptable, or whether its narrowing should be recorded as a contract change beyond §7.1's wording.

## 2. What was deleted

| | |
|---|---|
| `_excerpt_policy_v1`, `_truncate_to_block_ceiling` | the 250-word cap + 2,500 B ceiling with its binary search |
| `ProjectedEntity.truncated` | computed on every projection, read nowhere |
| `EXCERPT_WORD_CAP`, `EXCERPT_SENTENCE_EXTENSION_WORDS`, `EXCERPT_BLOCK_CEILING_BYTES` | |
| `EXCERPT_POLICY_VERSION` | **see §3.1 — larger than the amendment recorded** |
| `fat_worst_case_request_bytes`, `fat_static_guarantee_tokens` | the `M × ceiling` static guarantee |
| `ValidatedResponse.advisory_unresolved`, `ExpressionAccounting.selector_accounting_delta` | D-123-F |

Added: `budget.fat_input_byte_allowance`, the fill loop in `search.py`, telemetry
`stage2_pool_size` / `stage2_budget_bound`. `M` = 150. `excerpt` → `body`. Fat prompt `_v3`
(owner-reviewed and approved 2026-08-02).

## 3. Judgment calls we are flagging ourselves

### 3.1 `EXCERPT_POLICY_VERSION` was live, not a fixture-only field

The amendment treated it as a manifest field. It was in fact stamped on **every fat artifact**
(`artifact.py`, `stage.py`) and was a **hashed term in `compute_search_snapshot_hash`**. Retired
with the policy: with no transformation it describes nothing, and the evidence digest already
carries the exact bytes it used to characterise. Snapshot hashes move across this change regardless,
because the evidence bytes themselves changed. The frozen v1 manifest keeps its `"1"` as a
historical record that nothing reads.

### 3.2 `worst_case_input_tokens` kept, against the test that removed two other things

Its only remaining callers are its own unit tests. We deleted `ProjectedEntity.truncated` and
`selector_accounting_delta` on exactly the "computed, read nowhere" argument, so the asymmetry is
stated rather than left to be found: it survives because it is the executable form of the
`tokens_lte_bytes` premise that still proves the **output** allowances — a live ratified invariant,
not dead data. If that reads as special pleading, it is a one-line deletion.

### 3.3 The frozen fixture keeps a 2/163 divergence

The two entities the retired word cap truncated keep their capped tail text. Both are **absent from
the current wiki**, so their full bodies are unrecoverable and re-freezing is impossible without
reproducing that compile. Checksums untouched; the 39 adjudicated D7 probes not re-opened.

### 3.4 One pre-existing orphan, deliberately not touched

`types.py:99` — `evidence_excerpt: bool = True  # v1 always true; reserved`. Referenced nowhere and
predates this work, so it falls under flag-don't-delete rather than clean-up-your-own-orphans.

## 4. What was verified, and how

- **The fill's cost model is conservative in the safe direction.** The fill accepts on an
  accumulator (`overhead + Σ stream_contribution_bytes`); the pre-flight then re-measures the true
  rendering. Two different computations — if the accumulator ever under-counted, the fill would seat
  a pool its own pre-flight refuses. Measured at pool sizes 1/2/5/17: it overstates by **exactly +1
  byte** every time (`"\n".join` over n blocks costs n−1 separators; the accumulator charges n).
- **The boundary is tested, not just the slack region.** Every other fill test runs with kilobytes
  of headroom, where a sign error would hide.
  `test_a_pool_filled_to_the_LAST_BYTE_still_passes_its_own_pre_flight` binary-searches the body
  size until the fill is one byte from refusing, then asserts the real rendered request fits with
  ≤ 2 B to spare — and that one byte more is refused.
- **`fat_input_byte_allowance` is derived from `preflight`'s own inequality**, not restated beside
  it: `ceil(b/K) + reserved ≤ budget ⟺ b ≤ (budget − reserved) × K`, exact for integer `b`.
  Asserted in both directions at five window sizes.
- **Membership and presentation are asserted separately.** Thin ranks the manifest's *tail* first,
  so the two orders disagree completely; one test asserts the seated set is thin's top-K, another
  that the rendered order is the manifest's. A fill that returned everything would pass an
  order-only test; one that returned a single entity would pass a never-over-budget test.
- **"Above M" is now derived (`M + 20`), not the literal 120** it had been. That literal silently
  became *below* M when D-123-A raised M, and every above-M branch test began exercising the
  small-space path instead.

## 5. Explicitly settled — not open

- The three deleted mechanisms, on measured evidence: the byte ceiling had fired **0/163** fixture
  and **0/83** live; the word cap 2/163 and 0/83; `truncated` was read nowhere. The cause is
  structural — pass-2 writes these pages, so their length is governed by the compiler's own prompt
  contract (live max 129 w / 976 B).
- **D-123-F** dropping the advisory `unresolved` list. codex F2 (HIGH) closes as a side effect: the
  prompt-vs-controller divergence has no prompt side left. kimi F5's remaining half was considered
  and **withdrawn** — with the advisory gone, `unresolved_expressions` means one thing and says so,
  and no consumer decides differently with a third annotation than without it.
- The **query-block ceiling** stays, and is filed as a separate candidate to be decided the same way
  — by measuring how often it binds on real pass-1 output first. Pass-1 metadata is model-authored
  and genuinely unbounded, unlike a compiled body; that is a real difference, not an inconsistency.
- Output truncation (`stop_reason`, D9.3/D9.4), `delimiter_collision_guard`, `_single_line` P10
  containment, and the thin estimate guard are all **untouched**. "Truncation" names three unrelated
  things in this codebase and only the body one was removed.

## 6. Landing plan

Three commits, owner-confirmed:

| | contents |
|---|---|
| **1** | `_v2` prompts · blueprint v0.15 · `SYSTEM_TEMPLATE_BUDGET_BYTES` · D5 calibration · panel absorption |
| **2** | v0.16 docs (D-123-A…F) + the Fork A code |
| **3** | `_v3` — rename + D-123-E prose + D-123-F's prompt cut — + the Fork B code |

Commit 3 stands alone by **D-115-13**: template bytes move, so the filename bump, the golden re-pins
and the prose travel together.

*Staging note, recorded because it nearly cost the split:* `selector_fat_v2.txt` was overwritten in
the working tree by `_v3` before anything was staged, and git had collapsed the rename to
`v1 → v3`. It was reconstructed by reversing the four v3 edits and **verified byte-exact against the
digest pinned before the overwrite** (`sha256:3083b474…58a7d9`), so commit 1 carries the real v2
rather than prose rebuilt from memory.

## 7. Where to look

- Amendment + rationale: `docs/superpowers/archive/specs/2026-08-02-task123-simplification-amendment.md`
- Spec D-123-A…F: `docs/superpowers/specs/2026-07-25-task123-semantic-graph-search-spec.md` §0
- Byte tables: blueprint §7.0 / §7.0a
- The fill: `kdb_search/search.py` step 7; the allowance: `kdb_search/budget.py`
- Fill tests: `kdb_search/tests/test_two_stage.py`, the D-123-B section
- Prompt: `kdb_search/prompts/selector_fat_v3.txt`
