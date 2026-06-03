# KDB Release Notes

Backward-looking, **version-keyed** release log. Major releases (`X.0.0`) carry a
running narrative; every point release gets at least one documented entry. Forward
plan: `docs/ROADMAP.md`. Fine-grained date-keyed dev log: `docs/CODEBASE_OVERVIEW.md`
Milestone Changelog.

Versioning + tag policy: see `docs/ROADMAP.md` § Versioning policy. Tags are cut
(and point-release wrapping is evaluated) at each session handoff.

---

## 0.5.3 — Pass-2 robustness ladder (tagged `v0.5.3`, 2026-06-02)

**Theme:** make Pass-2 deterministically recover from the two confirmed recoverable
LLM-emission malformations instead of relying on a lucky retry — a re-validation-gated
repair ladder (Task #106). 0.6-robustness precursor, on the 0.5.x line.

**Gate — run-8 clean E2E:** `exit_reason=ok`; graph **172 Entity · 29 Source · 12 Domain ·
173 `BELONGS_TO` · 177 `SUPPORTS` · 409 `LINKS_TO`** (≡ run-6/7 standard; 0 quarantined).
**1213 non-live tests green.** The new compositional repair telemetry plumbed through end-to-end
(all 29 Pass-2 compiles recorded `final_status='clean'` — the malformations didn't recur this run,
so the rungs correctly stayed dormant; the repair paths are covered by 15+ unit/integration tests).

**What landed (Task #106 — deterministic ladder: `emit → repair → retry → repair → quarantine`,
every repair re-validation-gated):**
- **Rung 1 — targeted JSON backslash-escaping** (`common/util/json_escape_fix`): doubles only the
  stray `\` that JSON rejects (e.g. unescaped LaTeX `\(n-1\)`) so the bytes parse **and the backslash
  survives** — content-preserving by construction. The 5-model design panel chose this over the
  `json-repair` package (which can silently strip content); **no new pip dependency**.
- **Rung 2 — slug coercion** (`common/paths.collapse_slug`): lowercase + collapse `-{2,}`→`-` +
  edge-strip (the deterministic non-semantic subset of `slugify`), with full reference-propagation
  across all 7 slug-bearing fields (regex wikilink rewrite preserving `|display`/`#anchor`) + an
  all-values collision guard, in `compiler/repair.coerce_slugs_and_propagate`.
- **LB2 — `semantic_check` moved inside the attempt loop** so a post-repair semantic failure retries
  rather than quarantining with no budget left; per-attempt state reset fixes a latent stale-state class.
- **Compositional telemetry** on `RespStatsRecord` (`compile_attempts`/`syntax_repaired`/`slug_coerced`/
  `final_status`) — observable deterministic-recovery rate, so over-reach is detectable.

**Also:** **viewer** — node captions now appear only past a zoom threshold (`LABEL_ZOOM_THRESHOLD`)
with a live zoom readout in the header.

**Process:** spec **5-panel design review** (Codex/Deepseek/Qwen/Gemini/Grok → unanimous
GO-WITH-CHANGES; all folded, incl. the rung-1 escaping decision and Joseph's decision-B lowercase).
Implemented **subagent-driven** (8-task TDD plan); per-task two-stage review caught two real bugs
(a telemetry sticky-flag mis-report; the original semantic-gate gap). Merged `2fb5d0e`. Plan:
`docs/superpowers/plans/2026-06-02-task106-json-escape-slug-coercion.md`; synthesis:
`docs/superpowers/specs/2026-06-02-task106-review-synthesis.md`.

**Next:** run-8 surfaced recoverable failures clustering in **Pass-1** (empty-response, null-summary;
all retry-rescued) → **Task #108** (extend the ladder into Pass-1; rung-1 already reusable in
`common/util`). Then the **0.6→1.0 ingestion-pipelines** arc.

---

## 0.5.2 — Codebase realignment, Phase B (tagged `v0.5.2`, 2026-06-02)

**Theme:** finish the realignment — split the monolithic `kdb_compiler` package into the
peer-package structure the architecture has described since `v0.5.0`, **before** the 0.6
ingestion arc builds on top of it. Internal refactor, **zero behavior change**. (Task #105, Phase B.)

**Gate — run-7 clean E2E** (post-split): `exit_reason=ok`; finalize wired **468 links, 0 orphans**;
graph **193 Entity · 29 Source · 10 Domain · 195 `BELONGS_TO` · 202 `SUPPORTS`** — structurally ≡
run-6 (the delta is normal LLM run-to-run variance) → behavior preserved end-to-end. **1191 non-live
tests green** (1175 → 1191: +16 guard/split/render/gate tests, none lost).

**What landed (Phase B — package split; leaf-first, move-don't-rewrite):**
- **Six peer packages** replace the flat `kdb_compiler/` (+ `graphdb_kdb`, `kdb_benchmark`):
  `common` (leaf) · `ingestion` · `compiler` · `kdb_graph` (was `graphdb_kdb`; `graphdb-kdb` CLI name kept) ·
  `orchestrator` · `tools`. Extracted in dependency order so every step stayed green.
- **B.3 dependency contract is guard-tested** — `tools/tests/test_package_boundaries.py` AST-asserts the
  actual import graph equals the contract (`common`→∅ · `kdb_graph`→`common` · `ingestion`→`common` ·
  `compiler`→`common`+`kdb_graph` · `orchestrator`→all · `tools`→{`common`,`kdb_graph`,`ingestion`,`compiler`}),
  with one documented `orchestrator→tools.cleanup` inline-cleanup exception.
- **One real restructure** — `resp_stats_writer` split into `common/llm_telemetry` (generic call telemetry)
  + `compiler/resp_summary` (`build_parsed_summary`); the internal `parsed_summary` gate was **lifted** to the
  compiler call site (byte-identical condition) to keep `common` a true leaf.
- **Deferred Phase-A cleanups landed**: `failure_stage="reconcile"→"repair"`, `JOURNEY` `source_state.json→manifest.json`.
- Tests redistributed into per-package `tests/` dirs behind a shared root `conftest.py`; `pyproject` discovery,
  package-data, and `testpaths` updated; all 9 CLI entry points resolve.

**Execution + review:** implemented **subagent-driven** (13-task plan, fresh agent per task, two-stage review on
the logic-bearing ones). **5-panel code review** (Codex · Deepseek · Qwen · Gemini · Grok) → **GO-WITH-FIXES**, all
must-fixes folded (F1–F6: guard retired migration scripts, `__version__`→`0.5.2`, `setup.sh`/boundary-set/wheel-exclude/
stale-text). 3 non-blocking follow-ups (viewer packaging · `compiler.compiler` rename · cleanup decoupling) → **Task #107**.
Synthesis: `docs/superpowers/specs/2026-06-02-phase-b-review-synthesis.md`. Merged `f28220e`.

**Next:** the **0.6 robustness ladder** — **Task #106** (JSON-repair + slug-coercion), now landing in the real
`common/util` + `compiler/repair` homes; panel-review its spec → writing-plans → run-8.

---

## 0.5.1 — Codebase realignment, Phase A (tagged `v0.5.1`, 2026-06-02)

**Theme:** make the implementation reflect the decided architecture — pay down the
monolithic-`kdb_compile`-era terminology + structure debt **before** the 0.6 ingestion
arc. Internal refactor, **zero behavior change**. (Task #105.)

**Gate — run-6 clean E2E** (post-refactor): `exit_reason=ok` — 36 scanned / 36 enriched /
**29 compiled / 7 noise / 0 quarantined / 0 invariant**; finalize wired 478 links, 0 orphans.
Graph: 180 Entity · 29 Source · **10 Domain** · 100% `BELONGS_TO`. Structurally ≡ run-5 (the
delta is normal LLM run-to-run variance) → behavior preserved end-to-end. 1175 non-live tests green.

**What landed (Phase A — fix-in-place; one refactor, two sequential phases, A then B):**
- **Retired the legacy batch path**: `kdb_compile.py` (the superseded "second orchestrator"),
  its 427-ln `run_journal.py`, dead `planner.py`/`compiler.run_compile`, and 5 dead CLI bindings.
- **Fixed two layering inversions** so `common`-level leaves (`types`, `source_io`) depend on
  nothing above them (`SourceFrontmatter`→`types`, frontmatter parser→`source_io`); guard-tested.
- **Honest renames**: `reconcile→repair` · `patch_applier→page_writer` ·
  `source_state_update→manifest_writer` · `validate_compiled_source_response→validate_source_response` ·
  `ingestion/→enrich/` (+`run_journal→enrich_journal`). (`manifest.json` file kept — its name is honest.)
- **Single Kuzu door**: a 10-function context read-API in `graphdb_kdb/queries.py`;
  `graph_context_loader→context_loader` now authors **zero Cypher** (byte-identical query port).
- **North Star §5 rewritten** to the orchestrator architecture + stale-reference sweep.

**Ratification:** 5-model panel (Codex · Deepseek · Qwen · Gemini · Grok-build), unanimous GO;
blueprint v2 + reviews + synthesis under `docs/superpowers/specs/2026-06-01-codebase-realignment-*`.

**Next:** **Phase B** — split the `kdb_compiler` monolith into peer packages
(`common`/`ingestion`/`compiler`/`graph`=`kdb_graph`/`orchestrator`/`tools`), still before 0.6.

---

## 0.5.0 — Reliable orchestration (tagged `v0.5.0`, 2026-05-31)

**Theme:** the end-to-end `kdb-orchestrate` pipeline runs reliably, observably, and
gracefully — the 0.5.0 gate.

**Gate — run-5 clean E2E** (`2026-05-31T21-05-23`): `exit_code=0`, `exit_reason="ok"` —
36 scanned / 36 enriched / **29 compiled / 7 noise / 0 failed / 0 quarantined / 0
invariant / 0 warnings**; finalize wired 449 links, 0 orphans. Graph (schema **v2.4**):
181 Entity · 29 Source · **10 Domain** · 444 LINKS_TO · 183 SUPPORTS · 181 BELONGS_TO.

**What landed since 0.4.1:**
- **#96 — quarantine-and-continue** error-handling: severity taxonomy + structured
  `orchestrator_events.jsonl`, production invariant checks, source-local quarantine
  (run continues; `run_fatal`/`invariant` still abort), finalize-always-over-committed-set.
- **#102 — live stdout progress**: default-on, blow-by-blow per-stage narrative
  (`[n/total] ▸ source`, `pass-1`/`pass-2` with elapsed, running counts, inline `⚠`),
  `--quiet` opt-out, console decoupled from JSONL verbosity (supersedes #101's stderr tee).
- **#103 — domain-scoped Pass-2 context** (D3 → hard same-domain gate): the context
  snapshot is pulled only from the source's Pass-1 domain (anti-entropy).
- **D1-A derived domains** (from 0.4.1): `BELONGS_TO` derived from `Source.domain`+`SUPPORTS`;
  10 domains live in run-5 (vs 4 pre-backfill).
- **Pass-1 coercion + Pass-2 retry** (run-4 findings, `docs/run-4-findings.md`): Pass-1
  coerces >10 `entity_search_keys` to 10 and lets `source_type='other'` pass without
  `other_reason` (don't reject benign deviations); Pass-2 retries on a recoverable bad-JSON
  emission (parse/schema), mirroring Pass-1 — which recovered run-4's lone quarantine
  (a LaTeX `\(…\)` JSON-escape slip) in run-5.
- **#97 — GraphDB viewer**: multi-model bake-off → official single-command D3 viewer
  (`tools/viewer/kdb_graph_viewer.py`).

**Run history:** run-4 surfaced the findings (1 quarantine from a stochastic LLM
JSON-escape defect, handled gracefully); the fixes landed; **run-5 came back clean** → gate
met. 1219 non-live tests green. Next: **0.6 → 1.0** (ingestion pipelines). See `docs/ROADMAP.md`.

---

## 0.4.1 — Domain derivation, D1-A producer slice (tagged `v0.4.1`, 2026-05-31)

**Theme:** first slice toward 0.5.0 — fixes the domain meaning layer.

`Entity BELONGS_TO Domain` is now a **derived projection** from `Source.domain` +
`SUPPORTS` (an entity belongs to the domains of the sources that support it),
replacing the broken per-page LLM `domain`. Edges carry `support_count` (distinct
supporting sources); `sub_domain` retired. Pass-2 no longer emits page
`domain`/`sub_domain`. Schema → **v2.4** (destructive REL change; rebuild-only).
Snapshot → **v6**.

**Validated on run-3 data (zero LLM cost):** domains 4 → **11**; `value-investing`
0 → **66 entities** (now the top domain); canonical-entity domain coverage
16% → **100%**.

Implements ratified decision **D1-A** (`docs/ontology-blueprint-V1.md` v0.2). Plan:
`docs/superpowers/plans/2026-05-31-task-0.5.0-producer-domain-rebuild.md`. 1010
non-live tests green; final code review (opus) cleared it to ship.

**Still pending for 0.5.0:** D3 domain-scoped T2/T3 retrieval · stdout/progress
messaging · **run-4** (the orchestration-reliability gate).

---

## 0.4.0 — baseline (tagged `v0.4.0`, 2026-05-31)

**State:** the end-to-end pipeline runs (`feeder → ingestion/Pass-1 → compiler/Pass-2
→ GraphDB`). Run-3 (2026-05-30) was the first clean E2E run — 36 scanned / 29 compiled
/ 7 noise / 0 quarantined; graph: 178 Entity · 29 Source · 4 Domain · 0 Claim.

**Known limitation (the 0.5 target):** the domain meaning layer is broken —
`BELONGS_TO` is built from a leftover Pass-2 per-page LLM `domain` that under-emits
(24/147 concept pages, 4 values; `value-investing` never emitted). Orchestration is
not yet reliable.

**Planning landed this line:** Ontology Blueprint V1 ratified after a 5-model panel
review — D1→A (derive domain), D2→deferred to 2.0 (Claim/Learn layer), D3→C
(domain as retrieval coordinate). Release versioning + roadmap adopted.

→ Next: **0.5.0** (reliable orchestration). See `docs/ROADMAP.md`.
