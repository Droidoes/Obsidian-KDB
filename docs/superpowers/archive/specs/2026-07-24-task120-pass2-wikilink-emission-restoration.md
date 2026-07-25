# Task #120 — Pass-2 Wikilink-Emission Restoration (spec v1.4)

**Date:** 2026-07-24 · **Status:** v1.4 — Codex R1–R4 absorbed (all controller-verified); awaiting Joseph's ratification
**Supersedes:** v1.3 (`…-review-codex.md` … `…-review-codex-v4.md`). v1.4 changes: the upper audit now samples the **same all-edge population the trigger measures** (Codex R4 F1 — concept-only sampling could miss the summary/article edges causing the trigger); TASKS.md label corrected to "Candidate design v1.4 (awaiting ratification)" (Codex R4 F2).

**Seed:** #119 Phase-5 closure — deepseek concept-page wikilink emission collapsed **0.45 → 0.08 links/page** (overall 1.30 → 0.68) between prompt 3.0.0 and 4.0.1; gpt-5.4-mini stable on the identical contract. Mechanism (code-verified): the 4.0.1 proposal schema dropped both schema-level link mentions the 3.0.0 schema carried. `link_density` is a scored axis (0.30 of the graph block). Calibration (Codex, from retained 3.0.0 artifacts + graph): overall resolved `272/222 = 1.225225`; concept resolved `76/183 = 0.415301`; target pairs 285; dangling `13/285 = 4.561%`; self-links 0; current-summary links 0. (Codex self-correction: R1's "2 guessed summary targets" resolve to an emitted `summary-callout` concept — the namespace violation D5 closes, not current-summary links.)

## Ratified decisions

**D1 = B+ (constrained) — restore the full 3.0.0 schema link surface + an explicit linking expectation limited to authoritative targets** (Codex-accepted):

1. `body` field description (new):
   > "Full markdown body, no frontmatter (Python prepends frontmatter during apply). Use Obsidian wikilink syntax `[[slug]]` inline whenever you reference another page in this response or in EXISTING CONTEXT. Whenever you mention a concept, technology, person, organization, or work that **already has a page in this response or EXISTING CONTEXT**, make that mention a wikilink to that page. Do not invent a target, self-link, or link to the current source's summary merely to satisfy this instruction."
2. Top-level `description` gains: "The contract is wiki-native: pages carry prose bodies with `[[wikilinks]]` to other pages."

No system-prompt changes. No mirror fields.

**D2 — version 4.0.2** (Codex-accepted; golden system-prompt SHA unaffected).

**D3 = Path 1 (Joseph) — keep `entity_search_key_resolution`; document honestly.** The metric is the **mixed downstream final-graph realization rate of Pass-1 search keys** — influenced by Pass-1 key selection, Pass-2 materialization, and canonicalization; watched-not-scored; **not** a reuse/maturity measure, **not** an extraction-quality measure; cross-model comparison valid only for controlled runs (same corpus fingerprint + equivalent initial graph state). No novelty complement (information-free, semantically backwards on cold graphs). The three-way decomposition (pre-existing / materialized / unresolved via canonical `first_run_id`, watched-not-scored) is deferred to **#118** and recorded in #118's ledger row (applied).

**D4 — two-run 4.0.2 cohort: deepseek = restoration canary; gpt = non-regression guard.**

Predeclared acceptance equations:

1. `overall_resolved_density` = the persisted `graph.scored.link_density`: all stored `LINKS_TO` edges ÷ all entities with `canonical_id IS NULL` (exactly `compiler/kpi/graph.py:129-132`).
2. `concept_resolved_density` = stored `LINKS_TO` edges whose source entity has `canonical_id IS NULL AND page_type = 'concept'` ÷ entities with that same predicate; entity `status` intentionally unfiltered (reproduces 3.0.0's `76/183 = 0.4153`).
3. `raw_target_pairs` = Σ over emitted pages of `|body_wikilink_slugs(body)|` (production extractor: code spans ignored, non-kebab targets ignored, per-page dedupe). `dangling_pairs` = the subset with **no exact `Entity` match** in the final graph (intake's exact-slug semantics; link wiring never aliases).
4. Self-link: target equals its own page's **post-normalization** slug — zero required. Current-summary link: target equals its own compiled source's Python-derived summary slug — zero required.
5. Reserved-namespace: **zero concept/article slugs beginning with `summary-`** (the D5 canary).

Gates:

- **deepseek (canary):** `overall_resolved_density ≥ 1.2` AND `concept_resolved_density ≥ 0.4`; safety conditions 3–5 pass (`dangling/raw ≤ 13/285 ≈ 4.6%`; zero self-links; zero current-summary links; zero `summary-` violations); quarantine/recovery/retry_load pass-2 = 0.0; stamps 4.0.2 + prompt SHA. A miss routes to investigation (canary ≠ causal proof).
- **gpt (non-regression):** `overall_resolved_density ≥ 1.5` (historical band: 1.709 / 1.538); safety conditions 3–5 pass; the upper audit trigger applies equally.
- **Upper audit trigger (exact):** `overall_resolved_density ≥ 1.78`. Sample population = **all resolved edges counted by the trigger metric** (Codex R4 F1 — a concept-only sample can miss the summary/article edges that caused the trigger; retained cohorts show 196/272 and 263/400 of resolved edges originate from summaries/articles), limited to the current cohort's final compiled-page occurrences: candidate `(source_page_slug, target_slug)` pairs from the stored `LINKS_TO` set; sort by `source_outdegree DESC, source_page_slug ASC, target_slug ASC`; take `audited_edges = min(20, candidate_edges)`; persist `source_page_type` alongside the other evidence fields; judge each target against the **concrete final page occurrence that produced the stored outgoing set** — persist that occurrence's `compiled_source.source_id`, source/target slugs, the raw-source excerpt, and the verdict (LINKS_TO stores only `run_id`/`created_at`, so the edge alone cannot identify the evidence source — the analysis names it); pass = `supported_edges / audited_edges ≥ 0.90`.
- **Evidence persistence (tracked, not gitignored):** per run, an evaluation file at `docs/superpowers/evaluations/2026-07-24-task120-<model>-<run-id>.md` (benchmark/runs/ is gitignored by design — nothing may be force-added there) recording: run-dir ID, release version, corpus fingerprint, prompt version/SHA, all equations' numerators/denominators, dangling list, safety-check results, audit excerpts + verdicts. Raw body emission reported as a diagnostic only.

**D5 — reserved-prefix guard at the normalization boundary, retrospective across the whole 4.x era (Codex R3 F2 policy call).** The system prompt has always declared `summary-<stem>` Python-owned; today the bridge accepts any non-summary slug starting with `summary-` unless it exactly equals the current derived summary slug (controller-reproduced: `summary-callout` → `BridgeSuccess`; `collapse_slug` reserves only `index`/`log`-class slugs). A model-owned `summary-*` slug can collide with a FUTURE source's Python-derived summary identity at graph level. **Fix:** the bridge's collision stage rejects any non-summary page whose **planned (post-coercion)** slug starts with `summary-` as `slug_collision` (model-correctable, retriable like all bridge rejects) — the post-coercion pin matters: `SUMMARY--Foo` coerces to `summary-foo` and must reject, not slip through on the raw form.

**Replay policy (declared):** D5 is a **corrected invariant for the entire 4.x era**, not a new contract era — the namespace was always system-owned, so this is a validator bugfix. `tools/replay.py`'s `startswith("4.")` dispatch stays as-is; a historical 4.0.0/4.0.1 response carrying a `summary-*` concept slug now fails semantic normalization (was: passes). Tests: (a) replay fixture `prompt_version="4.0.0"` with a `summary-foo` concept → proposal-schema OK, `semantic_ok=False` with `slug_collision`; (b) all existing valid 4.x fixtures stay green; (c) bridge tests: `summary-foo` concept/article rejects post-coercion (`SUMMARY--Foo` included), `summary-foo` summary stray still tolerated (D-119 unaffected), exact derived-slug collision still rejects, plain concept still succeeds. Historical graph cleanup of pre-existing violations stays out of #120 (tracked in #116/WS3's lifecycle/occupancy context).

## Regression canary (Codex R1 F4 + R2 note)

One provenance suite via `prompt_builder.load_response_schema_text()`:

1. top-level description contains the wiki-native `[[wikilinks]]` clause;
2. `body` description contains the **complete** authoritative-target sentence and all three prohibitions (not merely the `[[slug]]` token);
3. `PASS2_PROMPT_VERSION == "4.0.2"`.

## Implementation sketch

- `compiler/schemas/proposal_response.schema.json` — the two description edits (D1)
- `compiler/prompt_builder.py` — `PASS2_PROMPT_VERSION = "4.0.2"` + history comment (D2)
- `compiler/proposal_bridge.py` — D5 guard on planned slugs (post-coercion) in the collision stage
- `compiler/kpi/graph.py` — docstring: honest "mixed downstream final-graph realization" wording (D3; no computation change)
- Tests: canary suite; version pins → "4.0.2"; D5 bridge tests; D5 replay tests (4.0.0 retrospective + existing fixtures green)
- `docs/TASKS.md` — ledger correction (applied in worktree; rides the first commit)
- Commits (each Joseph-gated): (0) design docs (spec v1.4 + review files + TASKS.md); (1) schema + 4.0.2 + canary; (2) D5 guard + tests (+ replay tests); (3) D3 docstring; then the D4 cohort (Joseph-gated: Drive-sync pause) + tracked evaluation artifacts + results commit
- Branch: `feat/120-wikilink-emission` from `main` (`9a320fd`)

## Out of scope

- Restoring `outgoing_links` or any mirror field
- `entity_search_key_novelty`; the three-way decomposition (→ #118)
- Historical `summary-` namespace cleanup in production graphs (→ #116/WS3)
- Promoting any Pass-1 diagnostic to scored; Pass-1 metadata diagnostics beyond D3 (→ #118)
