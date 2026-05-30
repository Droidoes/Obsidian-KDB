# Task #71 — Cold-Start Widening Rule for Graph Context Loader

**Status:** in-progress
**Parent:** Task #70 (GraphDB-backed context loader)
**Surfaced:** 2026-05-16 (gate testing on "My First Million Interview II")
**Decision:** D48

---

## Problem Statement

When a source has no `SUPPORTS` edges in the graph (first compile — no prior pages attributed to it), T1 is empty. T2 falls back to slug-in-text matching, but hyphenated slugs rarely appear verbatim in natural-language prose. Result: graph context is significantly sparser than manifest context for new sources (observed: 3 pages vs 6 on "My First Million Interview II").

The manifest context loader does not have this problem because its slug pool is larger at first-compile time (all manifest pages exist as indexable slugs). As the graph matures this gap narrows — but first-compile quality matters.

---

## Decision D48

**Graph context loader must be self-sufficient — no manifest fallback path.** Cold-start is resolved by widening graph-native matching (title phrase + extended hops), not by delegating to manifest. Manifest is being phased out of the context-generation pipeline; any fallback to it would be architectural regression.

Rejected alternatives:
- (b) Minimum-context fallback to manifest if graph returns < N pages — violates manifest phase-out direction.
- (c) Always use manifest for first-compile, graph for recompiles — same violation, plus creates a permanent second code path.

---

## Design

### Cold-start detection

```python
cold_start = len(t1_slugs) == 0
```

A source with zero `SUPPORTS` edges has never been compiled into the graph. This is the only trigger for widening.

### Primary fix: title-in-text matching

**When:** cold-start detected (T1 empty).
**What:** T2 matching expands from "slug appears in source_text" to "slug OR entity title appears as exact phrase in source_text."

Mechanics:
1. Build a `{normalized_title: slug}` reverse lookup from `active_entities`.
2. Normalize: lowercase the title. Keep it as-is otherwise (no stemming, no tokenization).
3. Build a second regex alternation from titles (same `(?<![\w-])..(?![\w-])` whole-word boundary pattern used for slugs).
4. Match titles against `source_text`. Each hit maps back to its slug via the reverse lookup.
5. Union title-match slugs with slug-match slugs → widened T2 set.

Guardrails:
- **Title eligibility rule:** a title is eligible for cold-start matching iff:
  - `len(normalized_title) > 3`, AND
  - either: title has **2+ alphanumeric tokens**, OR title is a **single token with length >= 6**
- Rationale: `len > 3` alone still allows single-word generics like "Risk", "Value", "Moat", "Oil" which exact-phrase-match too readily in long transcripts. The 2-token / 6-char rule keeps useful single-word concepts ("Legalism", "Confucianism", "Leverage") while filtering short generics.
- **Exact phrase only** — no fuzzy matching, no individual-word matching, no embedding similarity.
- Title normalization is minimal (lowercase only). Punctuation in titles is preserved for matching fidelity.

### Secondary amplifier: conditional 2-hop T3

**When:** cold-start AND `|widened_T2| < min_seed_threshold`.
**What:** T3 neighborhood expands from 1-hop to 2-hop.

Parameters:
- `min_seed_threshold = 5` — if widened T2 found >= 5 entities, 1-hop T3 is sufficient.
- 2-hop still filters against `candidate_slugs` (active entities not already in T1 or T2).
- `page_cap` still governs final output size — 2-hop widens the candidate pool, not the output.

Rationale: if title matching + slug matching together find < 5 seeds, the source's vocabulary overlap with the existing graph is genuinely thin. Extended neighborhood compensates by discovering more of the graph's structure through whatever seeds exist.

---

## What does NOT change

- Tier scoring: T1=3, T2=2, T3=1 — unchanged.
- PageRank tie-break within tier — unchanged.
- Non-cold-start path (T1 non-empty) — completely untouched.
- `page_cap` enforcement — unchanged.
- Return type / `ContextSnapshot` shape — unchanged.

---

## Implementation Plan

| # | Task | Test-first |
|---|------|-----------|
| 1 | Add `_t2_title_in_text()` helper — title phrase matching against source text | Yes: test with known titles, verify exact-phrase semantics, verify <= 3 char skip |
| 2 | Wire title matching into `build_context_snapshot` when `cold_start=True` | Yes: test cold-start path returns title-matched slugs; non-cold-start path unchanged |
| 3 | Add `max_hops` parameter to `_t3_neighbors()` with default=1 | Yes: test 2-hop discovers nodes not reachable at 1-hop |
| 4 | Wire conditional 2-hop when `cold_start=True AND len(t2_widened) < 5` | Yes: test triggers on sparse T2; does not trigger when T2 >= 5 |
| 5 | Live validation against "My First Million Interview II" source | Manual: compare graph context output before/after; target: parity with manifest (6 pages) |

---

## Acceptance Criteria

1. **Cold-start parity:** "My First Million Interview II" produces >= 5 context pages from graph (was 3, manifest gives 6).
2. **Non-regression:** All existing tests pass unchanged. Steady-state sources (Pabrai, Buffett, Howard-Marks, EP1) produce identical context with and without the change (they have SUPPORTS edges → T1 non-empty → widening never fires).
3. **Title guardrail verified:** Short titles (<= 3 chars) skipped; single-token titles < 6 chars skipped (e.g., "Risk", "Value"); multi-token titles and long single-token titles pass (e.g., "Margin of Safety", "Legalism").
4. **2-hop bounded:** When T2 >= 5, T3 stays 1-hop (verified in test).

---

## Post-implementation

After #71 lands and live validation passes:
- Update #70 to note cold-start gap closed.
- Evaluate whether to flip `KDB_CONTEXT_SOURCE` default from `manifest` → `graphdb` (separate decision, possibly D49).
