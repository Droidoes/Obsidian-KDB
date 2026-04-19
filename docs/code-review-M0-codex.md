# M0 Code Review: Obsidian-KDB

Scope reviewed:
- `docs/CODEBASE_OVERVIEW.md`
- `README.md`
- `kdb_compiler/*.py`
- `kdb_compiler/tests/README.md`
- `~/Obsidian/KDB/CLAUDE.md`

Skipped:
- `knowledge_graph/` as requested

## Findings

### 1. High: the LLM contract has drifted away from the architecture boundary

The overview says the LLM emits structured JSON patch-ops and Python owns deterministic state and file writes. The current `CLAUDE.md` contract is looser and more stateful than that:

- it asks the model to emit `content_patches[]` containing full markdown bodies
- it asks the model to choose `page_id` values that are filesystem paths under `KDB/wiki/`
- it asks the model to emit runtime frontmatter fields such as `compiled_at`, `compiler_version`, and `schema_version_used`

That is the wrong side of the boundary. If the model chooses file paths and runtime metadata, Python is no longer the sole authority over codegen/linking; it is just a file writer for LLM-authored documents.

Recommendation:
- choose one model and enforce it consistently:
  - either true patch-ops
  - or full-document replacement
- regardless of that choice, move these fields back to Python:
  - path resolution
  - timestamps
  - compiler version
  - schema version
- have the LLM emit logical identifiers such as `page_type`, `slug`, `title`, `body_sections`, `outgoing_links`, `supports_page_existence`

### 2. High: `CLAUDE.md` currently over-specifies cross-page edits and will cause unnecessary churn

The strongest example is the backlink rule:

> "you must also request updates to the linked page's `incoming_links_known` and (when sensible) add a prose mention in its 'See also' section"

This pushes one-source compiles toward broad graph rewrites. In practice that will:

- increase touched-file count per run
- create noisy diffs
- make compile results less stable
- raise the chance of the model editing pages with weak support from the current source

Recommendation:
- keep explicit link metadata if you want it in the manifest
- do not require prose edits to linked pages by default
- treat cross-page prose edits as rare, opt-in, and evidence-based

### 3. Medium: the top-level pipeline is correct, but M1/M2 are missing shared seam modules that should exist now

The current module boundary mostly matches the controller pipeline guidance:

`kdb_scan -> planner -> compiler -> validate -> patch_applier -> manifest_update`

That split is sound. What is missing are the shared seams that prevent M2 from turning into ad hoc glue code duplicated across modules.

Recommended stubs to add now:

- `kdb_compiler/paths.py`
  - owns vault-root discovery, repo/vault separation, and path normalization
- `kdb_compiler/atomic_io.py`
  - shared temp-write, fsync, replace, retry, lock helpers
- `kdb_compiler/contracts.py` or `kdb_compiler/types.py`
  - typed shapes for scan results, planner jobs, compile results, manifest payloads
- `kdb_compiler/run_context.py`
  - `run_id`, timestamps, compiler version, dry-run flag, schema version

These are not optional polish. `kdb_scan.py`, `patch_applier.py`, and `manifest_update.py` all claim the same atomic-write discipline; centralizing that now will prevent subtle divergence.

### 4. Medium: contract artifacts needed for review and testing are planned, but not stubbed

`CLAUDE.md` already references `compile_result.schema.json`, and the whole architecture depends on manifest shape, yet neither contract artifact is present in the repo in a reviewable form.

Recommendation:
- add these stubs now, before M1 implementation:
  - `kdb_compiler/compile_result.schema.json`
  - `kdb_compiler/manifest.schema.json` or `docs/manifest.schema.md`
  - `kdb_compiler/tests/fixtures/manifest.empty.json`
  - `kdb_compiler/tests/fixtures/compile_result.minimal.valid.json`
  - `kdb_compiler/tests/fixtures/compile_result.minimal.invalid.json`

Without those, the most important boundary in the system is still informal prose.

### 5. Medium: `compiler.py` is at risk of becoming a god-module

The current responsibilities listed for `compiler.py` include:

- loading source content
- loading `KDB/CLAUDE.md`
- loading related context from the manifest
- building prompts
- calling the model
- parsing the response
- accumulating global compile output

That is workable for a stub, but it is too much for one implementation module if kept as-is.

Recommendation:
- keep `compiler.py` as orchestration
- factor these helpers when implementation starts:
  - `prompt_builder.py`
  - `context_loader.py`
  - `response_normalizer.py`

If you do not want extra files yet, at least reserve those names in the design notes so M2 does not accrete everything into one script.

## Answers

### (a) Does the module boundary match earlier pipeline guidance?

Mostly yes.

What is right:
- `kdb_scan`, `planner`, `compiler`, `validate`, `patch_applier`, `manifest_update` is the correct controller pipeline
- `call_model` and `call_model_retry` being separate is also correct
- keeping reconciliation in `manifest_update` rather than `patch_applier` is the right split

What needs tightening:
- `planner` should stay limited to batch formation and context selection, not prompt authorship
- `compiler` should not become the owner of path policy or runtime metadata
- `patch_applier` should derive file paths and deterministic frontmatter fields, not trust the LLM for them

### (b) Are responsibilities correctly split between modules?

Mostly yes at the coarse level, but the fine-grained ownership needs correction.

Recommended ownership model:
- `kdb_scan.py`
  - discover sources, compute hashes, classify changes, write `last_scan.json`
- `planner.py`
  - turn scan deltas into compile jobs and context references
- `compiler.py`
  - turn one job into one compile payload via the LLM
- `validate_compile_result.py`
  - schema gate only
- `patch_applier.py`
  - resolve logical page descriptors into actual markdown writes
- `manifest_update.py`
  - update ledger, provenance mappings, run journals, tombstones, orphans

The main correction is that filesystem path choice and runtime frontmatter generation belong with `patch_applier.py` and `manifest_update.py`, not the LLM contract.

### (c) Is anything missing from the M1/M2 plan that should be a stub now?

Yes.

Highest-value additions now:
- `paths.py`
- `atomic_io.py`
- `contracts.py` or `types.py`
- `run_context.py`
- `compile_result.schema.json`
- manifest empty-shape fixture
- minimal valid/invalid compile-result fixtures

Optional but likely worth stubbing:
- `prompt_builder.py`
- `context_loader.py`

I would not stub more than that in M0. The goal is to lock interfaces, not pre-implement M2.

### (d) The LLM contract in `~/Obsidian/KDB/CLAUDE.md` — enough discipline, or too much?

Both.

It has the right discipline in these areas:
- grounding in source text
- no direct file writes
- no Human Side edits
- explicit schema compliance
- explicit contradiction handling

It is too strict or misplaced in these areas:
- requiring filesystem-path-shaped `page_id`
- requiring runtime frontmatter fields from the model
- requiring broad backlink and prose updates to linked pages
- conflating "patch ops" with full-document replacement

My recommendation is to simplify the contract so the model is responsible for semantic intent, not repository mechanics.

Better contract shape:
- input
  - one source
  - relevant manifest snapshot
  - compiler invariants
- output
  - summary intent
  - concept/article intents
  - logical ids or slugs
  - supported claims
  - link targets
  - optional warnings/log entries
  - structured body sections or full body text without runtime metadata

Python should then:
- assign final paths
- inject deterministic frontmatter
- stamp timestamps and versions
- merge index/log updates

## Bottom Line

The M0 scaffold is directionally strong. The top-level pipeline and the safety philosophy are both correct.

The main issue is not module count. It is boundary purity. Right now the prose architecture says "LLM as planner/parser, Python as codegen/linker," but `CLAUDE.md` still gives the LLM too much responsibility for file identity and deterministic metadata.

If you fix that contract now and add the missing shared seam stubs, the M1/M2 implementation path will be much cleaner.
