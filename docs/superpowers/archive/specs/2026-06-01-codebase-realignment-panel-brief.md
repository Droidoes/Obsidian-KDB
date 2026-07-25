# Codebase Architecture Realignment — Ratified Blueprint (v2)

**Type:** Architecture-level refactor blueprint. **Date:** 2026-06-01. **Status:** **RATIFIED v2** — panel-reviewed
(5/5 GO), all forks adjudicated, scope locked. **Supersedes:** v1 (the panel-review draft; git history preserves it).
**Release context:** Authored at the `v0.5.0` boundary, before the `0.6 → 1.0` ingestion-pipelines arc.
**Provenance:** five panel reviews (`*-review-{codex,deepseek,qwen,gemini,grok}.md`) + synthesis
(`*-review-synthesis.md`). Decisions in Part 3.

**The job:** make the implementation reflect the (already-decided) architecture — **one refactor, two sequential,
both-mandatory phases: A (fix in place) then B (split into peer packages).** A ends on a clean **run-6** live gate.

---

# Part 1 — Problem Statement

## 1.1 The drift
The package structure and vocabulary still belong to the original monolithic `kdb_compile` — one batch driver,
no Pass-1/Pass-2 split, no orchestrator. The architecture has since become (through #89–#104, shipped in `v0.5.0`)
**two pipelines over a graph substrate, conducted by an orchestrator, with out-of-band tools.** The names never
caught up; the codebase's nouns describe a system that no longer exists.

## 1.2 Why this is load-bearing
- Names that lie compound — every reader inherits the wrong mental model.
- We are about to build the 0.6 feeder/ingestion subsystem **directly on top of this** — pouring new structure
  onto colliding vocabulary turns a naming problem into a costlier structural one.
- The timing is maximally cheap: `v0.5.0` shipped on a clean run-5 gate; the green suite is the safety net.

**Thesis (panel-affirmed 5/5):** the terminology debt **is** the architecture problem. Fix vocabulary and
structure together; explain nothing away.

## 1.3 The decided architecture (target mental model)
```
INGESTION PIPELINE              COMPILER PIPELINE          GRAPH (substrate)       ORCHESTRATOR
feeder → scan → enrich          compile (Pass-2) →         Kuzu store + the        the conductor; just
(Pass-1) → post-pass1           repair → canonicalize →    SINGLE owned door       strings stages together
processing                      page-write                 for all Kuzu I/O

COMMON  shared leaves, no stage: atomic_io · call_model · run_context · types · source_io · paths · config · llm_telemetry
TOOLS   out-of-band, run anytime: cleanup · viewer · replay · benchmark · diagnostics
```
- **graph** = the GraphDB substrate **and its access API** (today `graphdb_kdb/` → Python pkg `kdb_graph`; CLI stays `graphdb-kdb`).
- **common** = cross-cutting infrastructure belonging to no single stage (NOT the graph).
- **tools** operate *on* state but are decoupled from a run (the viewer is the archetype).

## 1.4 Structural exhibits (grounded; all panel-verified)
- **Two "orchestrators":** `kdb_compile.py` self-titles "End-to-end orchestrator" (M1.7); the real one is `kdb_orchestrate.py`.
- **`kdb_compiler/` is "everything-except-the-graph."** `graphdb_kdb/` is the lone clean stage-package — the model.
- **Two doors into Kuzu:** `graph_context_loader.py` opens its own `kuzu.Connection` (~7 raw-Cypher ops) instead of the graph API.
- **Cleanup is inline** in `orchestrate.finalize` but is conceptually an out-of-band tool.
- **Layering inversions:** `source_io` (shared leaf) imports `ingestion.frontmatter_embedder`; `types` imports `source_io`.
- **`manifest.json` doc/disk split:** the file on disk is `manifest.json`; the North Star/D51/JOURNEY call it `source_state.json`.

---

# Part 2 — The Refactor (LOCKED scope)

## Phase A — Honest baseline, in place (inside `kdb_compiler/` + `graphdb_kdb/`)

**A.1 — Renames** (symbol + module, same package; the file `manifest.json` is NOT renamed — see Part 3 §5):

| From | To |
|---|---|
| `reconcile.py` / `reconcile()` | `repair.py` / `repair()` |
| `patch_applier.py` | `page_writer.py` |
| `graph_context_loader.py` | `context_loader.py` *(graph "lie" gone once A.3 routes reads through the API)* |
| `source_state_update.py` | `manifest_writer.py` *(default; consistent with keeping `manifest.json` — flip to `source_state_writer` on review if preferred)* |
| `validate_compiled_source_response.py` | `validate_source_response.py` |
| `kdb_compiler/ingestion/` | `kdb_compiler/enrich/` |
| `kdb_compiler/ingestion/run_journal.py` | `enrich_journal.py` *(prevents future collision with the retired root-level journal)* |

**A.2 — Retire the dead batch path** (gated: nothing on a live root imports/executes it + green tests):
- `kdb_compile.py` (legacy driver) and `run_journal.py` (427 ln, driver-only).
- **`planner.py` + `compiler.run_compile()`** — confirmed dead by execution analysis: `run_compile` (sole caller
  of `planner.plan`) is reached only by `kdb_compile.py` + the `kdb-compile-sources` entry; live paths use
  `compile_source` (orchestrate) and `compile_one` (benchmark), which never touch it. Excising `run_compile`
  edits the live `compiler.py` to remove dead code — gate with tests.
- **CLI bindings dropped:** `kdb-compile`, `kdb-old-compile`, `kdb-compile-sources`, `kdb-plan`.
- **`validate_last_scan.py`: keep as a diagnostic** (relocate to `tools/diagnostics` in B); drop its top-level binding.
- **Delete dead tests:** `test_kdb_compile.py`, `test_validate_last_scan.py`.

**A.3 — Single owned door to Kuzu.** Route `context_loader`'s graph reads through a **real graph context-snapshot
API** added to `kdb_graph` (`queries.py`) — not a mechanical import-swap; the loader runs ~7 distinct Cypher ops
the graph package doesn't yet expose. After this, **all** Kuzu I/O passes through the graph package. *(Classify
`kdb_clean`'s direct graph access too — acceptable once it's a tool, but make it explicit.)*

**A.4 — Fix the layering inversions.** Move the pure parser `parse_existing_frontmatter` **down** into `common`
(in `source_io`, or a tiny `common/frontmatter`); move `SourceFrontmatter` into `common/types` (kills the
`types → source_io` `TYPE_CHECKING` edge). `enrich/frontmatter_embedder` then imports downward from `common`. Result:
`common` is a true leaf.

**A.5 — Rewrite the North Star + stale-reference sweep:**
- Rewrite `CODEBASE_OVERVIEW.md` §5 (still describes `kdb_compile.py` as the 10-stage orchestrator) to §1.3.
- Fix every `source_state.json` doc reference → `manifest.json` (North Star §6, D51, JOURNEY).
- Sweep stale refs: deleted `manifest_update.py` cited in `CODEBASE_OVERVIEW.md` + two `scripts/`; the stale
  linear-pipeline comment in `kdb_compiler/__init__.py`; `kdb_compile.py` mentions in `adapters/` + `canonicalize.py`.

**A.6 — Gate:** full `pytest -m "not live"` green; **no live-path behavior change**; then a **live run-6 E2E** on the
sandbox vault reproducing a clean result (the run-5/v0.5.0 standard). **Phase A ships only when run-6 is clean.**

## Phase B — Structural split into peer packages

**B.1 — Target tree:**
```
common/         atomic_io · call_model(+_retry) · run_context · types · source_io · paths · config · llm_telemetry
ingestion/      feeder/ (0.6) · scan/ · enrich/ (was ingestion) · config/ (pipeline_registry) · post-pass1 in enrich
compiler/       compile · prompt_builder · response_normalizer · repair · canonicalize · page_writer ·
                validate_compile_result · validate_source_response · context_loader · resp_summary
kdb_graph/      (was graphdb_kdb) graphdb · ingestor · queries(+context API) · rebuilder · schema · snapshot ·
                verifier · analytics · adapters/ · ops/ + core/ (dormant 2.0)
orchestrator/   orchestrate · events · manifest_writer
tools/          cleanup · viewer · replay · benchmark · diagnostics (incl. validate_last_scan)
```

**B.2 — Relocation map deltas from the architecture (locked decisions applied):**
- `resp_stats_writer` → **split**: generic record/write/hash/capture/`safe_source_id` → `common/llm_telemetry`;
  compiler-specific `build_parsed_summary`/`ParsedSummary` → `compiler/resp_summary`.
- `pipeline_registry` → **`ingestion/config`** (it describes ingestion; the orchestrator only reads it).
- `graphdb_kdb/*` → **`kdb_graph/*`** (Python pkg rename; `graphdb-kdb` CLI name unchanged).
- `planner` → **retired** (A.2), not relocated.
- `validate_last_scan` → **`tools/diagnostics`**.
- everything else per §1.3 (scan → `ingestion/scan`, enrich subpkg → `ingestion/enrich`, the conductor →
  `orchestrator`, `kdb_clean` → `tools/cleanup`, `response_replay` → `tools/replay`, `kdb_benchmark` → `tools/benchmark`).

**B.3 — Dependency contract:** `common` depends on nothing internal (true leaf after A.4). `ingestion`/`compiler`
depend on `common` (+ `compiler` → `kdb_graph` for context reads via the API). `kdb_graph` depends on `common` only.
`orchestrator` depends on all (the conductor). `tools` may depend on any package + `common`; nothing depends on `tools`.

**B.4 — CLI surface** (`pyproject [project.scripts]`): keep `kdb-orchestrate` (primary) · `kdb-enrich` · `kdb-scan` ·
`graphdb-kdb` · `kdb-clean` · `kdb-replay` · `kdb-benchmark`. Dropped in A.2. The `kdb-validate-*` stay importable, no
top-level bindings.

**B.5 — Tests + packaging:** centralized `kdb_compiler/tests/conftest.py` + fixtures do **not** split for free —
design a shared test-fixture strategy (e.g. `common/tests` or a root `conftest`) before distributing tests. Update
`pyproject` **package discovery, package-data** (schemas/Jinja templates), and **pytest testpaths**, else installed
entry points miss data files. Retire/relocate `last_scan.schema.json` with its validator.

**B.6 — Gate:** full non-live suite green at new paths; `pip install -e .` resolves entry points + data files; a live
`kdb-orchestrate` smoke run reproduces a clean E2E.

## Constraints (binding)
Move-don't-duplicate · reversibility (renames/moves over rewrites) · single-user (no locking/retry ceremony) ·
leave a clean `ingestion/feeder/` seam for 0.6 · surface-don't-delete anything on a live path.

---

# Part 3 — Decisions & Panel Outcome

**Verdict:** unanimous GO (5/5), all reviewers repo-verified. Convergence detail in `*-review-synthesis.md`.

**Load-bearing (5/5):** the refactor + its timing (before 0.6); the A-then-B seam; all renames; safe retirement of
the legacy driver + 427-ln journal; `kdb-compile` must not stay on the legacy driver; `validate_last_scan` kept as a
diagnostic; `common` must be a true leaf (layering fix).

**Settled by fact:** `planner` + `run_compile` are dead (Gemini correct; the "planner is live" reads were
import-reachability, not execution) → retired in A.2.

**Adjudicated forks (Joseph, 2026-06-01):**
1. `resp_stats_writer` → **split** (general → `common/llm_telemetry`; each stage keeps its own output summary).
   *Rationale:* every stage's LLM call produces identical call-stats (common); only "summarize my output" is
   stage-specific (different shapes) and cannot live in `common` without re-introducing an upward dependency.
2. `pipeline_registry` → **`ingestion/config`** (orchestrator only strings stages together).
3. A.3 + A.4 stay **in Phase A**; Phase A ends on a clean **run-6**; then Phase B.
4. `kdb-compile` → **dropped** (no re-point; no muscle-memory to preserve).
5. `manifest.json` → **kept as-is** (legitimate name for a source-file ledger; zero persisted-state migration
   risk). Residual confusion was doc/disk name split → fixed in A.5 (docs say `manifest.json`). Module → `manifest_writer`.
6. Python package → **`kdb_graph`**; CLI stays `graphdb-kdb`.

**Folded panel catches:** `graph_context_loader → context_loader` (A.1); `ingestion/run_journal → enrich_journal`;
A.3 needs a real graph context-snapshot API (not a swap); stale-ref sweep + doc naming consistency (A.5); delete dead
tests (A.2); test-fixture split + `pyproject` package-data/discovery/testpaths (B.5); a pre-existing live-test bug in
`test_t2_*` (seeds concepts without `Domain`/`BELONGS_TO` → empty context) is logged **separately** as a bug, not part of this refactor.

**Next:** this blueprint → `writing-plans` for the **Phase A** implementation plan.
