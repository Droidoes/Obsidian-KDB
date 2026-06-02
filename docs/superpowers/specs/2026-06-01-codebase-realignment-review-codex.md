# Codebase Realignment — Codex Review

## Summary

The refactor is directionally right and worth doing before 0.6 feeders. The highest-value catch is that the proposal under-weights one remaining vocabulary mismatch: `source_state_update.py` has already become a source-state ledger writer, but the persistent file is still named `manifest.json` in `kdb_orchestrate.py` (`MANIFEST_NAME = "manifest.json"`) and in the implementation path. If the goal is architecture realignment, module/package names alone will leave a visible state-file noun lying to operators.

I agree with the A-then-B cut, but A must be treated as a real shippable release, not a cosmetic prelude. In particular, A.3 and A.4 belong in A because they remove the import/dependency facts that would make B a relocation of bad edges. I would also add an explicit A gate that the legacy driver is no longer a public CLI target and that any remaining `kdb_compile` coverage is either deleted or reclassified as regression coverage for relocated stage functions.

## 1. A/B cut

- Position: agree with fix-in-place then package split.
- Confidence: high.
- Reasoning: the current code has both naming drift and structural drift. Fixing names first lets import churn be mostly mechanical in B, and it gives test failures one dominant cause per phase. The brief's split is therefore the right seam.
- What we under-weight: A.3 is not a small dependency cleanup. `graph_context_loader.py` embeds raw Cypher across context-specific operations: active entity loading, domain pool selection, T1 source support, T3 neighbors, PageRank input edges, outgoing link batching, and alias-aware canonical resolution (`kdb_compiler/graph_context_loader.py:76`, `:87`, `:90`, `:108`, `:111`, `:126`, `:515`). `graphdb_kdb/queries.py` currently exposes generic graph reads, not the whole context-snapshot API. A.3 therefore needs an intentional graph API design, not just "replace imports."

A.4 also belongs in A. `source_io` imports upward into `ingestion.frontmatter_embedder` for `parse_existing_frontmatter` (`kdb_compiler/source_io.py:19`), and `types` references `SourceFrontmatter` under `TYPE_CHECKING` (`kdb_compiler/types.py:15`). If B happens before this inversion is fixed, the split will encode a bad dependency shape into the new packages.

A alone can be coherent only if it changes the public path. Today `kdb-compile` still points to `kdb_compiler.kdb_compile:main` (`pyproject.toml:34`), while `kdb-orchestrate` points to the real conductor (`pyproject.toml:38`). A is not honest if it leaves the user-facing command on the legacy driver.

One caution: "no behavior change" and "retire public CLI bindings" are in tension. Dropping or repointing `kdb-compile` is an intentional user-visible behavior change. That is fine, but call it out as the one allowed behavior change in A and verify it with CLI tests.

## 2. Rename adjudications

- `reconcile.py` / `reconcile()` -> `repair.py` / `repair()`: agree, with one refinement. The best module name may be `compile_result_repair` if you want maximum explicitness after the package split. Inside `compiler/`, plain `repair` is acceptable because the package supplies the scope. The docstring already says "post-validate repair" (`kdb_compiler/reconcile.py:1`), so this is a truthful rename.

- `patch_applier.py` -> `page_writer.py`: agree. The module writes rendered wiki pages and explicitly says it never mutates raw or state (`kdb_compiler/patch_applier.py:1`, `:17`). "Patch" is residual vocabulary.

- `kdb_compiler/ingestion/` -> `kdb_compiler/enrich/`: agree for Phase A. The existing subpackage is Pass-1 enrich, not the whole ingestion pipeline. Keeping the CLI as `kdb-enrich` is correct.

- `source_state_update.py` -> `source_state_writer.py`: agree, but incomplete if the file remains `manifest.json`. The module's docstring is already "source-meta-only manifest writer" (`kdb_compiler/source_state_update.py:1`), and `kdb_orchestrate.py` writes `MANIFEST_NAME = "manifest.json"` (`kdb_compiler/kdb_orchestrate.py:46`). Either rename the state artifact to `source_state.json` with a compatibility migration, or explicitly document that `manifest.json` is a legacy path retained for backward compatibility. Otherwise the rename only moves the lie from Python to disk.

- `validate_compiled_source_response.py` -> `validate_source_response.py`: acceptable. A more precise option is `validate_llm_source_response.py`, because this validates the per-source LLM payload before it becomes a compiled source. I would not over-optimize this name unless there is another "source response" object expected from feeders.

## 3. Relocation-map errors

The biggest potential misplacement is `pipeline_registry`. The current module is a per-vault ingestion-pipeline registry: it validates pipeline ids, roots, scopes, force-noise/signal lists, and feeder metadata (`kdb_compiler/pipeline_registry.py:1`, `:24`, `:33`, `:61`). Today the orchestrator is its only live production reader (`kdb_compiler/kdb_orchestrate.py:30`, `:496`, `:985`), so `orchestrator/pipeline_registry` is defensible as an intermediate home. But architecturally it describes ingestion configuration, not orchestration behavior. Before 0.6 feeders land, I would move it to `ingestion/pipeline_registry` or `ingestion/config/pipeline_registry`, with the orchestrator depending on it.

`context_loader` belongs in `compiler`, not `graph`, as long as it owns prompt-context semantics. It decides T1/T2/T3 ranking, same-domain gating, cold-start widening, and page-cap projection. Those are compiler-context choices over graph data, not graph substrate primitives. The raw graph reads inside it should move behind graph API functions in A.3, but the composition algorithm should stay compiler-side.

`resp_stats_writer` is partly misplaced in the proposal. It is not purely compiler behavior: benchmark imports `safe_source_id` from it (`kdb_benchmark/runner.py:38`), and it writes general LLM-call telemetry (`kdb_compiler/resp_stats_writer.py:1`). But it also builds a compiler-specific `ParsedSummary` over source-response JSON (`kdb_compiler/resp_stats_writer.py:76`). Recommendation: split it. Put hashing, capture policy, filename safety, and generic `RespStatsRecord` construction in `common/llm_telemetry`; keep compiler-specific parsed-response summarization in `compiler/resp_stats_writer`.

`call_model` and `config` should not become vague `common` catchalls without substructure. There is already a historical collision risk around `kdb_compiler/config/` versus settings imports, documented in the repo (`docs/superpowers/plans/2026-05-26-task89-pass1-ingestion-implementation.md:113`). In the split, distinguish `common/llm_config` or `common/settings` from controlled vocabularies such as domains and source types.

## 4. Retirement risk

`kdb_compile.py` is not the live operational path anymore, but it is still user-facing and heavily test-facing. Public bindings point to it (`pyproject.toml:33`, `:34`), and tests import or execute it directly (`kdb_compiler/tests/test_kdb_compile.py:12`, `:400`; `kdb_compiler/tests/test_canonicalize_stage_integration.py:20`; `kdb_compiler/tests/test_pass1_end_to_end.py:41`). This is not evidence that the driver is live architecture; it is evidence that A.2 needs a test migration plan.

`run_journal.py` appears driver-only outside tests. Its docstring says the journal is assembled by `kdb_compile.compile` (`kdb_compiler/run_journal.py:3`), and the only production import is `kdb_compile.py`. Retire it with the legacy driver unless some journal-reader contract still needs its constants. Do not move it into B as a zombie common module.

`validate_last_scan.py` has no live production importer except the legacy driver and CLI binding. It is still a useful diagnostic module: it has a clean public `validate(payload) -> list[str]` API and catches semantic scan invariants (`kdb_compiler/validate_last_scan.py:19`, `:49`). I would keep the module through A as an internal diagnostic/library, but drop the top-level `kdb-validate-scan` binding unless you intentionally want it in the public operator surface.

Do not bundle planner excision into A. `compiler.py` imports `planner` (`kdb_compiler/compiler.py:38-40`) and `run_compile` still uses the batch planning path. Retiring `planner` means also retiring or rewriting `compiler.run_compile` and likely `kdb-compile-sources`; that is more than legacy-driver deletion. Treat it as a follow-on cleanup once the public CLIs are rationalized.

## 5. Layering-fix approach

The cleanest inversion is:

- Move frontmatter parsing down to a common leaf, e.g. `common/frontmatter.py` with `parse_frontmatter(text) -> tuple[dict, str]`.
- Move `SourceFrontmatter` into `common/types.py` if it is part of cross-pipeline payload shape. Then `common/source_io.py` imports only `common.frontmatter` and `common.types`.
- Make `enrich/frontmatter_embedder.py` depend downward on `common.frontmatter` for parsing and `common.atomic_io` for writes.
- Remove the `types -> source_io` type-check import by either defining `SourceFrontmatter` in `types`, or using a local forward string without importing from another common module.

This keeps `types` as the true leaf. It also prevents the future feeder code from inheriting a dependency on Pass-1 embedding just to read source frontmatter.

## 6. CLI surface

Public commands that earn bindings:

- `kdb-orchestrate`: primary production command.
- `kdb-enrich`: useful standalone Pass-1 operation.
- `kdb-scan`: useful deterministic diagnostic and feeder boundary check.
- `graphdb-kdb`: graph administration/query/verify/rebuild.
- `kdb-clean`: destructive maintenance with dry-run/apply semantics.
- `kdb-replay`: explicit diagnostic tool.
- `kdb-benchmark`: explicit benchmark tool.

Drop or hide:

- `kdb-old-compile`: drop.
- `kdb-compile`: either drop or repoint to `kdb-orchestrate` with a deprecation warning. Do not leave it on `kdb_compile.py`.
- `kdb-compile-sources`: internal-only unless you still want a benchmark/debug entry point. Prefer `python -m compiler.compile` style invocation if needed.
- `kdb-plan`: internal diagnostic only. Its own docstring says it is not part of the normal run path (`kdb_compiler/planner.py:28`).
- `kdb-validate-scan`, `kdb-validate`, `kdb-validate-response`: I would remove top-level bindings unless there is active operator usage. If kept, group them under a future `kdb-diagnose` or document them as diagnostics, not pipeline commands.

## 7. Sequencing vs 0.6

Do not start feeder implementation before A is complete. The feeder work is exactly where today's vocabulary collision will compound: `ingestion` currently means Pass-1 enrich, while future ingestion will mean feeder plus scan plus enrich plus post-Pass-1 handling.

B can be staged, but not skipped. The minimum pre-feeder B slice should split `common`, `ingestion/enrich`, `orchestrator`, and `compiler` enough that feeder modules have a real home and do not land under `kdb_compiler/ingestion` by inertia. Moving benchmark/tools can trail if needed, but the ingestion/compiler/orchestrator/common boundary should precede 0.6.

## 8. What's missing

The persistent state noun is missing from the inventory. If `manifest.json` is source lifecycle only, call it `source_state.json` or document it as a compatibility filename. The North Star already speaks in source-state terms, while the implementation still writes `manifest.json`. This is the same class of terminology debt as `patch_applier`.

There are stale `manifest_update` references. The file no longer exists (`kdb_compiler/manifest_update.py` is absent), but docs and scripts still reference it: `docs/CODEBASE_OVERVIEW.md:139`, `docs/CODEBASE_OVERVIEW.md:141`, `scripts/migrate_task64_supersession.py:26`, and `scripts/migrate_task66_compiled_hash.py:36`. If those scripts are historical one-shots, move them under archived migrations or mark them non-runnable. If they are meant to remain usable, they are currently broken.

Graph access inventory should include `kdb_clean`, not just `planner` and `graph_context_loader`. `kdb_clean.py` imports `kuzu`, `default_graph_path`, and graph queries directly (`kdb_compiler/kdb_clean.py:53`, `:57`, `:58`, `:215`). That may be acceptable once cleanup moves to `tools`, because tools may depend on graph. But it should be explicitly classified so A.3's "single owned door" does not accidentally apply only to compiler pipeline modules.

The package-data and testpath migration are under-specified. `pyproject.toml` currently packages only `kdb_compiler` schema data and discovers only `kdb_compiler*`, `kdb_benchmark*`, and `graphdb_kdb*` (`pyproject.toml:46`, `:50`, `:54`). Phase B must update package discovery, package data for schemas/config/Jinja templates, and pytest testpaths. Otherwise the import split can pass locally while installed entry points miss data files.

The GraphDB package rename should be treated carefully. The command `graphdb-kdb` is a good public name and should probably remain even if the Python package becomes `graph`. A package named plain `graph` is also generic enough to collide mentally with third-party graph libraries. Consider `kdb_graph` as the Python package while keeping `graphdb-kdb` as the CLI.

Finally, `kdb_compiler/__init__.py` is stale and should be part of A. It still advertises the old linear pipeline ending in `patch_applier -> source_state_update` (`kdb_compiler/__init__.py:3-4`). That is small, but it is exactly the kind of entry-point-level lie this refactor is meant to eliminate.

## Convergence note

I expect other reviewers to converge on: A before feeders, `kdb-compile` cannot stay bound to the legacy driver, `source_io -> ingestion.frontmatter_embedder` must be inverted before package splitting, and `context_loader` should keep compiler semantics while graph reads move behind graph APIs.

Likely contested points: whether `resp_stats_writer` is common or compiler, whether `pipeline_registry` belongs in orchestrator or ingestion, and whether `manifest.json` should be renamed on disk now or documented as a compatibility artifact. My view is that `manifest.json` is the highest-leverage naming question not explicitly framed in the brief.
