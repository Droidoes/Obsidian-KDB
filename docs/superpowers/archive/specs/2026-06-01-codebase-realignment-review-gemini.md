# Codebase Realignment — Gemini Review

## Summary
The proposed codebase realignment is an excellent and necessary step to resolve naming drift, pay down terminology debt, and enforce structural boundaries before starting the 0.6 feeder work. Dissolving [kdb_compiler/](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler) into peer packages (`common`, `ingestion`, `compiler`, `orchestrator`, and `tools`) cleanly aligns folder layout with the actual system architecture. 

The single highest-value catch is a critical bug in the live test [test_t2_structured_path_live](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/tests/test_t2_end_to_end_pass1_path.py#L43-L137): the test seeds concepts directly into the graph but fails to create the corresponding `Domain` nodes or `BELONGS_TO` edges. Consequently, when Pass-1 returns a domain in the frontmatter, the same-domain gate in [build_context_snapshot](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/graph_context_loader.py#L54-L140) filters out all seeded entities, resulting in an empty context snapshot and test failure. The test setup must be updated to seed these domain relationships.

---

## 1. A/B cut
- **Position**: Strong Agree / High Confidence.
- **Reasoning**: Performing renaming and interface corrections in-place (Phase A) before executing directory structural relocations (Phase B) is the correct engineering flow. Relocating modules that are currently suffering from layering inversions or circular imports would make Phase B messy and hard to debug. Keeping Phase B as a purely mechanical file relocation minimizes the footprint of potential issues and keeps git diff history clean.
- **What we under-weight**: The proposal under-weights the complexity of relocating tests in B.5. The tests in [kdb_compiler/tests/](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/tests) are highly centralized and rely on shared fixtures in [conftest.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/tests/conftest.py). Distributing tests to their respective package-level `tests/` directories will require either duplicating fixtures, copying `conftest.py` configurations, or creating a shared test-utility library within `common`. A structured plan for testing infrastructure separation should be added to Phase B.

---

## 2. Rename adjudications
- **`reconcile.py` / `reconcile()` → `repair.py` / `repair()`**:
  - *Adjudication*: Agree.
  - *Reasoning*: The current term is used for two conflicting tasks: repairing semantic invariants on a single compiler run output, and resolving out-of-sync states across independent datastores (graph vs. manifest vs. wiki). The latter is a true reconciliation. Renaming the compiler utility to [repair.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/reconcile.py) removes the naming collision and aligns with the docstring's own phrasing.
- **`patch_applier.py` → `page_writer.py`**:
  - *Adjudication*: Agree.
  - *Reasoning*: The term "patch" is residual. The module does not construct or apply delta diff patches; it renders complete wiki page files with markdown headers and bodies and writes them to disk. [page_writer.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/patch_applier.py) represents the actual file operations.
- **`kdb_compiler/ingestion/` → `kdb_compiler/enrich/`**:
  - *Adjudication*: Agree.
  - *Reasoning*: Today, the `ingestion` subdirectory only performs Pass-1 LLM-based source enrichment. Reclaiming the word "ingestion" is essential because the 0.6 feeder architecture will introduce a complete `feeder -> scan -> enrich` pipeline where "ingestion" serves as the root domain.
- **`source_state_update.py` → `source_state_writer.py`**:
  - *Adjudication*: Agree, but with a structural caveat.
  - *Reasoning*: [source_state_update.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/source_state_update.py) is a purely logic-based module that takes dictionary payloads and computes manifest changes. It does not perform actual disk write operations (which are owned by the orchestrator). Calling it a "writer" might lead readers to expect file I/O. However, since it is the sole logic generator for the source-state section of the manifest, the rename is acceptable, though `source_state_updater` or `manifest_updater` would be technically more precise.
- **`validate_compiled_source_response.py` → `validate_source_response.py`**:
  - *Adjudication*: Agree.
  - *Reasoning*: Eliminating the redundant word "compiled" is clean and matches the target vocabulary.

---

## 3. Relocation-map errors
- **`context_loader` (`graph_context_loader.py`)**:
  - *Target in Brief*: `compiler/context_loader`
  - *Critique*: This is a structural layering violation. [graph_context_loader.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/graph_context_loader.py) executes raw Cypher queries on `kuzu.Connection` and relies directly on the graph schema (node labels like `:Entity`, edge labels like `:ALIAS_OF` and `:BELONGS_TO`, and entity properties). Moving it to the `compiler` package forces the compiler stage to depend on database implementation details. To preserve database encapsulation, `context_loader` should live inside the `graph` package (e.g., `graph/context_loader.py` or as public read APIs in [queries.py](file:///home/ftu/Droidoes/Obsidian-KDB/graphdb_kdb/queries.py)). The `compiler` stage should simply request context snapshots through a clean graph API, keeping `compiler` entirely agnostic of Kuzu and Cypher.
- **`resp_stats_writer`**:
  - *Target in Brief*: `compiler/resp_stats_writer`
  - *Critique*: Since LLM call infrastructure is a shared leaf utility (`common/call_model`), and other pipelines (such as Pass-1 `enrich` or future feeders) make LLM calls, those stages will also need telemetry tracking. If `resp_stats_writer` is inside `compiler/`, `enrich` cannot import it due to the dependency contract (no cross-pipeline edges). Moving it to `common/telemetry` or keeping it under `common/` allows it to be shared across all LLM-calling stages in KDB, ensuring uniform telemetry formats.
- **`pipeline_registry`**:
  - *Target in Brief*: `orchestrator/pipeline_registry`
  - *Critique*: Placing it in `orchestrator/` is acceptable because the registry is primarily utilized by the orchestrator at startup to resolve execution scopes. However, if standalone diagnostics or out-of-band tools also need to read `pipelines.json` configuration, placing it in `common/config` would prevent coupling tools to the orchestrator package.

---

## 4. Retirement risk
- **Live Flows**: We verified that [kdb_compile.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/kdb_compile.py), [run_journal.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/run_journal.py) (the old batch journal), and [validate_last_scan.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/validate_last_scan.py) are not imported or called by the live per-source orchestrator [kdb_orchestrate.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/kdb_orchestrate.py). They are safe to retire.
- **`planner` in A**: [planner.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/planner.py) is only imported by `compiler.compile()` (the legacy batch compiler function) and is not called in the orchestrator flow. Since the batch driver is being retired, both `planner.py` and `compiler.compile()` are dead code. We recommend keeping `planner.py` in Phase A to avoid surgical changes to `compiler.py`, but it should be omitted from relocation in Phase B (letting it retire during the package split).
- **CLI Point**: Currently, the main user command `kdb-compile` in [pyproject.toml:L34](file:///home/ftu/Droidoes/Obsidian-KDB/pyproject.toml#L34) points to the legacy batch compiler. We should re-point `kdb-compile` to `kdb_orchestrate:main` rather than dropping it entirely. This preserves user muscle memory while routing execution through the correct orchestrator pipeline.

---

## 5. Layering-fix approach
To break the cycle `source_io → ingestion.frontmatter_embedder` and decouple `types` so `common` is a true leaf, we recommend:
1. Move the [SourceFrontmatter](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/source_io.py#L22-L33) dataclass definition from `source_io.py` to [types.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/types.py). This completely decouples `types.py` from `source_io.py` (resolving the `TYPE_CHECKING` import).
2. Move the YAML parsing function [parse_existing_frontmatter](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/ingestion/frontmatter_embedder.py#L34-L45) and its regex `_FRONTMATTER_RE` from `frontmatter_embedder.py` to `common/source_io.py`. Since this helper relies only on standard libraries and `yaml`, it is a clean common utility.
3. Have `frontmatter_embedder.py` (which will live in `ingestion/enrich`) import `parse_existing_frontmatter` from `common.source_io`.
This leaves `common` leaves (like `types` and `source_io`) depending on nothing above them, cleanly obeying the dependency contract.

---

## 6. CLI surface
- **Public Entry Points (earning bindings in [pyproject.toml](file:///home/ftu/Droidoes/Obsidian-KDB/pyproject.toml))**:
  - `kdb-compile`: Re-pointed to `orchestrator/orchestrate:main` (user facing).
  - `kdb-orchestrate`: Direct orchestrator binding.
  - `kdb-enrich`: For manual Pass-1 triggers.
  - `kdb-scan`: Developer tool to view vault modifications.
  - `kdb-clean`: Orphans and state pruning.
  - `kdb-replay`: For LLM response replay.
  - `kdb-benchmark`: Cross-model benchmarking.
  - `graphdb-kdb`: Graph management (rebuild/verify).
- **Internal / Retired (no public bindings)**:
  - `kdb-old-compile` (retired)
  - `kdb-compile-sources` (retired)
  - `kdb-plan` (retired; redundant without batch compilation)
  - `kdb-validate-scan` (internal)
  - `kdb-validate-response` (internal)
  - `kdb-validate` (internal schema validator)

---

## 7. Sequencing vs 0.6
The realignment refactor must precede the 0.6 feeder work. If we defer the refactor:
1. We would write feeders under the confusing `kdb_compiler/ingestion/` directory structure, exacerbating terminology drift.
2. The 0.6 feeder PR would be contaminated with large structural renames and relocations, violating code review hygiene.
Aligning the codebase first sets up a clean `ingestion/` structure with a placeholder slot (`ingestion/feeder/`) ready for 0.6, while ensuring that all shared logic is correctly isolated in `common/`.

---

## 8. What's missing
- **Test File Retirement**: We must explicitly list the retirement of test files for retired code. Specifically, [test_kdb_compile.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/tests/test_kdb_compile.py) and [test_validate_last_scan.py](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/tests/test_validate_last_scan.py) should be deleted in Phase A. Leaving them in the tests directory will break the test suite.
- **Unused schemas**: The schema file [last_scan.schema.json](file:///home/ftu/Droidoes/Obsidian-KDB/kdb_compiler/schemas/last_scan.schema.json) should either be retired alongside `validate_last_scan.py` or relocated to `ingestion/scan/schemas/`. Schema files should be loaded relative to their validator modules.

---

## Convergence note
- **`context_loader` Placement**: Other reviewers might instinctively place `context_loader` in `compiler/` because it is used for prompt construction. However, when presented with the dependency contract, they should converge on placing it in `graph/` to prevent Kuzu/Cypher leakage into the compiler.
- **`planner` Retirement**: Reviewers might argue for deleting `planner.py` in Phase A rather than Phase B. While deleting it in Phase A is cleaner, leaving it as dead code to be deleted during B is safer to avoid modifying `compiler.py` twice.
