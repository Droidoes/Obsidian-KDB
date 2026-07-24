# Task #120 Spec v1.2 Review — Codex R3

**Date:** 2026-07-24

**Reviewed:** `docs/superpowers/specs/2026-07-24-task120-pass2-wikilink-emission-restoration.md`

**Repository anchor:** `main` at `9a320fd`

**Verdict:** **REVISE**

Spec v1.2 correctly absorbs the substance of the previous review. The resolved-edge equations now reproduce the retained 3.0.0 graph exactly; the dangling denominator follows production extraction; D3 is honestly labeled as a mixed downstream realization signal; the schema canary pins the full directive; and D5 is a justified, narrow closure of the system-owned `summary-` namespace.

Two Important design details remain. The upper-density semantic audit mixes page and edge sampling, has no unambiguous source-evidence authority, and names no tracked destination for the supposedly committed result. D5 also changes the current bridge used by every 4.x replay, so its retrospective-versus-patch-specific semantics must be chosen and tested. One Minor North-Star tracking claim is not yet true in the worktree.

Kimi's prompt still names spec v1.1 and the already-used `…review-codex-v2.md` output. I preserved that prior review—which v1.2 cites as superseded—and wrote this v1.2 delta review as `…review-codex-v3.md`.

## Findings

### 1. Important — the upper audit is not executable or persistable as written

**Location:** spec `:31,37,59`; `.gitignore:40-43`; `kdb_graph/schema.py:126-143`; `kdb_graph/intake.py:338-375`

The exact `>= 1.78` trigger is now good, but the sampling contract changes units mid-sentence:

> the 20 highest-outdegree canonical concept pages ... each target is judged ... pass = >=18/20 supported

Twenty pages can have far more than twenty targets. Conversely, if the intended sample is twenty edges, “20 highest-outdegree pages” does not identify those edges. `target slug asc` also cannot break a tie between page candidates unless the unit is actually an edge.

“Source-supported” is also ambiguous for canonical pages. A canonical entity may have several `SUPPORTS` sources, while a stored `LINKS_TO` relation contains only `run_id` and `created_at`, not the raw `source_id`. Within one combined run, a repeated canonical page slug can be wired more than once and the final outgoing set is the last replacement. The audit must say which page occurrence/raw source supplies the semantic authority; “the run's raw sources” permits different reviewers to choose different evidence.

The persistence location is equally unresolved. The spec promises a **committed** artifact “beside the run evaluation,” but `benchmark/runs/`—where `report.md` and the run evidence live—is intentionally gitignored. The implementation sketch names no tracked alternative. Force-adding an ad hoc file inside an ignored runtime directory would work mechanically but would violate the documented storage convention and be easy to miss.

**Concrete fix:**

1. Make the sample unit a resolved edge: candidate `(source_page_slug, target_slug)` pairs whose source is a canonical concept; calculate source outdegree; sort by `outdegree DESC, source_page_slug ASC, target_slug ASC`; take the first 20 edges. If the team truly wants twenty pages, define how targets within those pages are sampled and change the pass denominator accordingly.
2. Define semantic support against the concrete final page occurrence that produced the stored outgoing set. Persist its `compiled_source.source_id`, the source and target slugs, the relevant raw-source excerpt, and the reviewer verdict. If “any source supporting the canonical page” is preferred instead, state that explicitly.
3. Define the small-sample rule as `supported_edges / audited_edges >= 0.90`, with `audited_edges = min(20, candidate_edges)`, so the denominator remains valid if fewer than twenty candidates exist.
4. Name a tracked destination outside `benchmark/runs/`, for example `docs/superpowers/evaluations/2026-07-24-task120-<model>-<run-id>.md` or an unignored `benchmark/evaluations/` directory. Record the ignored run-directory ID, release version, corpus fingerprint, prompt version/SHA, all calculations, excerpts, and verdicts there.

### 2. Important — D5 silently changes replay semantics for the entire 4.x era

**Location:** spec `:18,39,41-59`; `tools/replay.py:101-108,186-215`; `tools/tests/test_response_replay.py:239-250`

The earlier “no new replay era” conclusion was safe when Task #120 contained description-only prompt changes. D5 is different: it changes the normalization bridge's semantic verdict.

Replay dispatch sends every `4.*` fixture through the **current** `normalize_proposal()`. A synthetic `prompt_version="4.0.0"` response containing a concept slug `summary-callout` is currently schema- and semantic-valid. Once D5 lands, that same historical fixture will become semantic-invalid even though its prompt version is unchanged.

That retrospective correction may be exactly right: the system prompt has always declared `summary-` Python-owned, so D5 can reasonably be treated as a validator bugfix for every 4.x response rather than a new contract era. But the spec must choose that policy explicitly. Otherwise an implementation can either break historical expected flags or add unnecessary patch-level replay dispatch, and both would appear consistent with the current document.

**Concrete fix:**

1. State whether D5 applies retrospectively to all 4.x replay or only to 4.0.2+.
2. Recommended: declare it a corrected invariant for the whole 4.x era, keep the existing major-version dispatch, and add a `prompt_version="4.0.0"` replay test whose `summary-*` concept passes proposal schema but fails semantic normalization as `slug_collision`. Keep the existing valid 4.0.0 fixture green.
3. Add the corresponding 4.0.2 case or direct bridge case, and pin that the guard evaluates the **post-coercion planned slug** (`SUMMARY--Foo` -> `summary-foo` must reject), not merely an already-normalized raw slug.
4. If historical observed behavior must instead remain patch-exact, introduce an explicit replay policy seam for `<4.0.2` versus `>=4.0.2`; do not let the current broad `startswith("4.")` dispatch decide accidentally.

### 3. Minor — the claimed task-ledger absorption has not occurred

**Location:** spec `:3-4,20,58`; `docs/TASKS.md:46-47`

The spec says the three-way search-key decomposition “is now recorded in #118's ledger row” and that #120 is linked to this spec. Neither change exists in the current task ledger:

- #118 still lists only split-model orchestration, provenance, and leaderboard-key work.
- #120 still carries its original scope, including the now-rejected “consider promoting `entity_search_key_resolution`” wording, and does not link spec v1.2.

The implementation sketch correctly schedules these edits, but that contradicts the status text's claim that they are already present. Under the project's North-Star gate, the ledger should be accurate before implementation begins.

**Concrete fix:** update `docs/TASKS.md` before ratification: add #118's pre-existing/materialized/unresolved watched decomposition, and revise #120 to link spec v1.2, record D1-D5's chosen scope, and remove the obsolete promotion decision.

## R2 absorption status

| R2 finding | v1.2 status |
|---|---|
| F1 — predeclare exact D4 equations, correct the historical baseline, and protect the reserved namespace | **Mostly absorbed.** Equations 1-5, `13/285`, D5, and lower gates are correct. The upper audit's sample/evidence/persistence contract remains open in Finding 1 above. |
| F2 — remove the inaccurate reuse/maturity interpretation | **Fully absorbed.** D3 now states the mixed causes and the controlled-comparison boundary accurately. |
| F3 — record the deferred decomposition in #118 | **Specified but not applied.** The planned wording is correct; the actual ledger remains unchanged. |
| R2 canary note — pin the complete body directive | **Fully absorbed.** The suite now requires the authoritative-target sentence and all three prohibitions. |

## Items accepted as designed

- D1's complete constrained schema text and restoration of both 3.0.0 link surfaces.
- `PASS2_PROMPT_VERSION = "4.0.2"` and the unchanged system-prompt SHA model.
- D3's mixed downstream realization wording and watched-not-scored disposition.
- D4 equations 1-5, including exact-slug dangling semantics, unfiltered canonical denominators, and post-normalization self/current-summary checks.
- The corrected 3.0.0 calibration values: overall `272/222`, concepts `76/183`, dangling `13/285`, self `0`, current-summary `0`.
- DeepSeek `>=1.2` overall / `>=0.4` concept and GPT `>=1.5` lower gates.
- D5's normalization-boundary placement and `slug_collision` classification. Namespace reservation is model-correctable, and all bridge reject classes already route through the retry seam.
- Keeping historical graph cleanup out of #120; #116/WS3 is the appropriate lifecycle/occupancy context, provided the follow-up is explicitly tracked there.

## Verification performed

- Rechecked production link extraction, exact-slug intake, graph denominator queries, and the retained 3.0.0 evidence.
- Verified `LINKS_TO` stores no raw `source_id`, so semantic source authority cannot be inferred from the edge alone.
- Verified `benchmark/runs/` is gitignored and current per-run `report.md` files are not tracked.
- Ran a read-only replay probe: a 4.0.0 proposal containing concept `summary-callout` currently returns `semantic_ok=True`; D5 will reverse that verdict through the broad 4.x dispatch.
- Rechecked the bridge's post-coercion planning order and generic `slug_collision` retry route.
- Compared spec claims with the current #118/#120 rows in `docs/TASKS.md`.
- No production code changed; this was a design review, so no test suite was rerun.

## Recommendation

Issue spec v1.3 with Findings 1 and 2 resolved before ratification, then apply the small ledger correction in Finding 3 as part of the North-Star gate. The underlying implementation remains narrow; these changes make its acceptance and compatibility behavior deterministic.
