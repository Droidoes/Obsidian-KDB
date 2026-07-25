# KDB E2E Orchestrator — Design Spec (WORK IN PROGRESS)

> **Status:** Living design doc, assembled collaboratively (brainstorming phase, 2026-05-28). NOT yet ratified. Sections are added as each component is settled. Supersedes the compile-driving assumptions in `docs/task91-kdb-orchestrate-blueprint.md` §4 where they conflict (the blueprint modeled a per-source world against the pre-split monolithic `kdb-compile`; this doc reflects the real, decomposed `feeder → ingestion → compiler → GraphDB` architecture).

## Strategic frame

`kdb-orchestrate` is the **end-to-end conductor** for the pipeline:

```
feeder → ingestion pipeline (Pass-1 enrich) → compiler pipeline (Pass-2) → GraphDB
```

Historical note: `kdb-compile` was the *original* whole-pipeline orchestrator, from before ingestion and compilation were separated into distinct pipelines. Post-split, much of `kdb-compile`'s outer shell (it owns its own scan, persists, graph-syncs) is redundant with what the new orchestrator must own; its reusable core is the Pass-2 artifact production (compile → validate → reconcile → canonicalize → manifest-delta → apply-pages). The keep/cut/move assessment of `kdb-compile`'s 10 stages is a later section of this doc.

## Settled commonality principles

The orchestrator is **multi-pipeline**. The vault-in-place (Obsidian) case is implemented *first*, but the implementation is kept **as common as possible** — the vault is the first *instantiation* of a general mechanism, never a bespoke path.

- **P1 — Ingestion pipeline is the unit of selection.** When `kdb-orchestrate` starts, it presents the registered ingestion pipelines and one is selected. Each pipeline carries its own **scan-scope config** (roots / excludes / file-types).
- **P2 — One common scanner.** A single scanner component, parameterized by the selected pipeline's scope, identifies NEW / MODIFIED / DELETED sources by diffing the filesystem against the manifest, and leaves UNCHANGED sources behind. It is a dumb filesystem diff — no pipeline-specific or feed-aware logic.
- **P3 — One unified manifest.** A single `KDB/state/manifest.json` (path-keyed, v3.0 source-state ledger) is the single change-tracker across *all* pipelines. (= blueprint D-91-1.)
- **P4 — Vault-in-place is the "special" pipeline.** Its sources are scattered across `~/Obsidian` (scope = whole vault minus excludes: `KDB/`, `.*/`, …) rather than self-contained under `KDB/raw/`, and it has **no feeder** (see Feeder contract). Everything downstream of the scanner treats it identically to any other pipeline.

---

## Component: Feeder

### Purpose
A feeder is the **acquisition + materialization adapter** from a heterogeneous external source-stream into the project's homogeneous substrate. It exists so that everything downstream of it — scanner, manifest, ingestion (Pass-1), compiler (Pass-2), GraphDB — never has to know *which* stream it is handling.

### Function
1. **Normalize** — convert a native external source (RSS item, Gmail message, podcast audio, web page, …) into a markdown `.md` file.
2. **Place** — write the normalized `.md` into that pipeline's raw directory under the convention `KDB/raw/pipeline-<name>/` (e.g. `KDB/raw/pipeline-rss/`, `KDB/raw/pipeline-gmail/`).

### Triggering — decoupled from the orchestrator
A feeder runs on its **own cadence** (manual / scheduled / event-driven). It is **NOT** fired at the same time the orchestrator triggers the scanner. By the time the orchestrator runs, the feeder's output `.md` files are already on disk. Consequence: **the orchestrator never executes feeders** — it scans whatever has already been materialized. From the scanner's point of view, vault-authored files and feeder-produced files are indistinguishable: both are simply *already present* in the pipeline's scope when the scan runs.

### Position in the flow — strictly upstream of the scanner
```
[ feeder, own trigger ]  →  KDB/raw/pipeline-<name>/*.md
                                     ⋮  (independently, later)
[ orchestrator ]  scanner(scope) → {NEW, MODIFIED, DELETED}
                  → ingestion (Pass-1) → compiler (Pass-2) → manifest + GraphDB
```
The feeder sits *before* the scanner because the scanner is a filesystem diff and can only operate on things that are already files. (If the feeder sat *after* the scanner, the scanner would need feed-awareness per pipeline — breaking P2.)

### Deletion semantics (design guideline for feeder authors)
To keep DELETED detection common (P2), a feeder should **mirror the current external state** on each run (full re-materialization of what is presently in the source). The scanner then infers a DELETED source from its *absence* on disk vs. its presence in the manifest — the identical mechanism the vault uses when a file is removed. No deletion signalling channel is needed between feeder and scanner.

### Vault-in-place special case
The vault pipeline's feeder is the **identity function**: Joseph authors `.md` files directly in `~/Obsidian`, so this pipeline has **no feeder**, and the scanner reads the vault scope in place. This is the precise sense in which vault-in-place is "special" — it is the pipeline whose feeder is null and whose scope is in-place rather than under `KDB/raw/`.

### Scope boundary for v1
This task does **not** ship any concrete feeders (RSS, Gmail, …). Concrete feeders are filed as separate tasks per `[[feedback_concrete_first_extract_later]]` when there is a real stream to ingest. What this design fixes is the feeder *contract* (function, placement convention, triggering model, deletion semantics) so that downstream components can be built pipeline-agnostic.

> **Implication to revisit when we reach the orchestrator CLI:** because feeders are independently triggered (not run by the orchestrator), the v0.2 blueprint's `--feeders=NAME` flag (which ran feeders *before* scan, D-91-11) needs to be dropped or reconceived. Flagged here so it is not lost.

---

## Component: Scanner

### Purpose
A single common component that, given the selected pipeline's `root_dir` + scope config, identifies the subset of sources that changed since the last run and feeds them to ingestion, leaving UNCHANGED sources behind. It is a dumb filesystem diff — no pipeline-specific or feed-aware logic (P2). This generalizes the existing `kdb_scan.py`, which today does exactly this but is hardcoded to the `KDB/raw/` root.

### Inputs
- `root_dir` of the selected pipeline
- the pipeline's **scope config** (excludes, file-types — `.md` only per D-91-2)
- the unified `KDB/state/manifest.json` (P3)

### Action
1. Enumerate `*.md` recursively under `root_dir`, applying excludes (equivalent to `find root_dir/ -name "*.md"` minus excluded dirs; hidden `.*/` dirs pruned at walk time).
2. Hash each file; compare to the manifest entry for its vault-relative path.
3. Classify: **NEW** (not in manifest), **MODIFIED** (hash differs), **UNCHANGED** (hash matches — left behind), **DELETED** (in-scope per manifest but absent on disk).

### Pipeline membership — explicit `pipeline_id` tag (decision 2026-05-28)
Because one manifest holds *every* pipeline's sources (P3), the DELETED pass must consider only the entries belonging to the pipeline being scanned — otherwise scanning `pipeline-rss` would flag all vault sources as deleted. **Each manifest source entry carries an explicit `pipeline_id`** referencing an `id` in the global pipeline registry (see *Component: Pipeline registry*). The scanner — which knows the pipeline it is scanning (selected at orchestrator start) — stamps `pipeline_id` on its scan entries; the manifest writer persists it. (Manifest schema bump: a `pipeline_id` field on the v3.0 source record.)

> **DELETED pass = manifest entries where `pipeline_id == selected` and path absent on disk.**

Chosen over deriving membership from the scope-config predicate ("the path prefix is the tag"): explicit tagging is more readable and safer, and it is **robust to scope-config changes** — a source's pipeline membership persists in the manifest regardless of later edits to roots/excludes. This closes the stale-entry watch-for noted in the previous draft.

### Source-deletion handling (confirmed against D-91-14 "Shape A" + `graphdb_kdb/ingestor.py:224-246`)
A DELETED source does **not** pass through Pass-1 or Pass-2 — there is no file left to enrich or compile. It is carried as a reconcile op and replayed through the *existing* compile-event path with an **empty `compiled_sources`** list (zero new mutation channel):

1. **Manifest:** source flagged deleted / tombstoned; DELETED op in `last_scan.to_reconcile`.
2. **Graph-sync** (`apply_compile_result` → `_handle_source_deleted`): drops the source's `SUPPORTS` edges and sets `Source.status='deleted'`. Does *not* delete the `Source` node, does *not* touch entities directly.
3. **`kdb-clean orphans`** (final orchestrator step, D-91-4): reaps any entity left with no active supporting source.

So the per-source routing splits:

> **NEW / MODIFIED → ingest (Pass-1) → compile (Pass-2) → graph-sync.**
> **DELETED → reconcile → graph-sync (sever `SUPPORTS` + tombstone source) → cleanup (reap orphaned entities).**

### Interruption / resume — DEFERRED to a later version (explicit decision, 2026-05-28)
The scanner has **no interruption-resume in v1**. Rationale: the scan is cheap and fully idempotent — re-running from scratch costs seconds and yields the identical diff. The genuinely expensive work, per-source LLM ingest/compile, already has natural resume via **per-source manifest commits**: each file is enriched → compiled → graph-synced and committed individually, so an interruption costs at most the single in-flight file, with or without resume machinery. Recovery = re-run (per `[[feedback_no_imaginary_risk]]`). This also confirms the **per-source commit granularity** the orchestrator loop will formalize.

---

## Component: Pipeline registry (global config)

### Purpose
A single global configuration — the source of truth for *which* ingestion pipelines exist and *how* each is scoped — accessible across all code modules (scanner, orchestrator, manifest writer, …). It is what the orchestrator reads at startup to present the selection list, and what the manifest `pipeline_id` tag references. Modules import the loader rather than hardcoding pipeline knowledge.

### Location & loader
- **Config file:** `KDB/state/pipelines.json` — hand-authored *config*, not derived run-state. Respects `[[feedback_no_parallel_storage_to_authority]]`: it defines inputs, it does not duplicate the manifest's source-state authority. *(Open: could live in a dedicated `KDB/config/` to keep config and state separate; placed in `state/` for now to match existing convention.)*
- **Shared loader module:** `kdb_compiler/pipeline_registry.py` exposing `load_pipelines()`, `list_pipelines()`, `get_pipeline(pipeline_id)`.

### Schema (per pipeline entry)
- `id` — stable pipeline identifier (e.g. `vault-in-place`, `rss`); the value stamped into each source's manifest `pipeline_id`.
- `type` — `in-place` | `raw` (`in-place` = scattered across the vault; `raw` = self-contained under `KDB/raw/pipeline-<id>/`).
- `root` — scan root dir.
- `excludes` — dirs **never scanned or enriched** — out of the pipeline entirely (`KDB/`, `.*/`, `node_modules/`).
- `force_noise` — "ignore"/blacklist dirs: **scanned + enriched but forced to `kdb_signal=noise`** (tracked as `metadata_only`, never graphed; e.g. `Daily Notes/`). Symmetric `force_signal` whitelist also supported. *(Today these live in a global `load_scope_config()`; here they become per-pipeline settings, and the override applies the selected pipeline's lists.)*
- `file_types` — `.md` only (D-91-2) for v1.
- `feeder` — **optional, descriptive metadata only.** The feeder is independently triggered; the orchestrator does not run it. v1 ships no concrete feeders.

### Consolidation note
This **unifies** the v0.2 blueprint's two separate config files — `scan_roots.json` (§5.1) and `feeders.json` (§8.2) — into one pipeline registry, matching P1 (the ingestion pipeline is the unit). Each pipeline's scope and (future) feeder reference live in a single entry.

### Validation (`load_pipelines()`)
- unique `id`s
- roots exist
- no two pipelines whose scopes can produce the same vault-relative path (blueprint §5.5 collision invariant)

---

## Component: Ingestion (Pass-1 enrich) + post-Pass-1 fan-out

### Per-source flow & Pass-1 egress
For each NEW / MODIFIED source the scanner emits:

```
source body + Pass-1 prompt + schema
   → LLM Pass-1 → frontmatter envelope (incl. kdb_signal)
   → [A] embed frontmatter into .md → recalculate whole-file hash       (always; instant)
   → gate on kdb_signal:
        signal → [B] handoff = (source_id, body, keep-frontmatter) → LLM Pass-2 (compile)
        noise  → STOP — no Pass-2; recorded as enriched-not-compiled (compile_state = metadata_only)
   → commit manifest (post-embed hash)
```

- **Strip is already handled.** Pass-1 (`enrich_one`) feeds the LLM the **body only** (`parse_existing_frontmatter`), and `embed_frontmatter` **owns the Pass-1 field namespace** (`_PASS1_FIELDS`) — a MODIFIED source's stale enrichment is rebuilt fresh, merging back only the author's non-Pass-1 keys. Old enrichment is **replaced, never fed back**. No separate strip step.
- **[A] then [B], sequential** (not parallel). [A] (embed + recalculate whole-file hash; deterministic — fixed field order + `yaml.safe_dump`) is instant and unconditional; [B] is the expensive LLM step. B uses the in-memory result so it doesn't *need* [A] first, but `[A]→[B]` is simplest. *Self-healing edge:* embed precedes a possible [B] fail-fast, so a failed signal-source can leave frontmatter on disk with no committed manifest entry — the next run re-enriches + re-embeds, overwriting. Acceptable for single-user v1.
- **Force override (deterministic, config-driven) — applied inside Pass-1 enrich.** If the source path falls under one of the selected pipeline's **`force_noise` ("ignore"/blacklist) dirs**, `apply_overrides` (`enrich.py:58`) forces `kdb_signal = noise` regardless of the LLM's judgment (a symmetric `force_signal` whitelist is also supported), per `[[feedback_post_llm_deterministic_override]]`. **Distinct from scanner `excludes`:** excluded dirs are never scanned/enriched at all; `force_noise` dirs ARE scanned + enriched (Pass-1 runs, frontmatter embedded, source manifest-tracked) but forced to noise so they never compile into the graph (example: `Daily Notes/` — enriched but not graphed, D-89-14). The override mutates the field *before* the gate sees it.
- **`kdb_signal` egress gate.** The gate acts on the **final (post-override)** `kdb_signal`: **signal → Pass-2; noise → stops at enrich.** Noise sources are still scanned, enriched, hash-recorded, and manifest-tracked (`compile_state = metadata_only`) so they are not re-enriched every run — they simply never enter the graph. The orchestrator enforces this gate at egress.
- **Egress handoff payload** (signal only) = `(source_id, body, keep-frontmatter)`. "Keep" frontmatter = the GraphDB-input fields (`kdb_signal, domain, source_type, author, summary, key_themes, entity_search_keys`); audit fields are Pass-1's own (Pass-2 ignores). Split already exists as `frontmatter_embedder._GRAPHDB_INPUT_FIELDS` vs `_AUDIT_FIELDS`. This payload is what crosses into **Pass-2 ingress** (next section); [B] consumes it **in-memory** — no re-read of the embedded file.

### Hash basis — whole-file, recalculated after embed (decision 2026-05-28)
Change-detection keys off the **whole-file hash**, recalculated **after** [A] embeds the Pass-1 frontmatter; the manifest stores that post-embed hash. This breaks the re-enrichment loop: on the next run the scanner re-hashes the on-disk file and matches the stored post-embed hash → UNCHANGED. A source is re-processed only when the user actually edits it (changing the whole-file hash).

- **Rejected — body-only hash:** more efficient on frontmatter-only edits, but it depends on splitting frontmatter from body cleanly (whitespace / delimiter edge cases make the hash fragile). The whole-file byte hash is unambiguous and simpler.
- **Non-issue:** a `PASS1_PROMPT_VERSION` bump does *not* mass-flag the corpus — UNCHANGED files are never re-enriched, so their stored hash and on-disk frontmatter stay put until the body itself changes.
- **Requirement:** `embed_frontmatter` must be deterministic (same envelope → byte-identical output). It is today (fixed field tuples + stable YAML dump).
- **Embed-timing — RESOLVED (decision 2026-05-29, Joseph): embed during enrich + recompute the post-embed hash right there.** `enrich_one` keeps its immediate `embed_frontmatter` and, right after, recomputes the **post-embed whole-file hash** and returns it (plus the body) for the orchestrator's manifest commit. The cleaner-but-reworking "embed-at-commit" alternative is **rejected** per [[feedback_no_imaginary_risk]]: with fail-fast, the only downside is the **self-healing edge** — a source that enriches then fails compile leaves frontmatter on disk with no manifest entry, which the *next* run auto-corrects (no manifest entry → re-enrich → `embed_frontmatter` deterministically strips-and-rewrites → re-compile). The window is bounded to one source per failed run, transient, single-user, and `kdb-audit` (#93) reconciles it out-of-band. Accepted for v1.

### Pass-2 no longer scans — `kdb-compile` rebuild (decision 2026-05-28)
Pass-2 takes the egress handoff `(source_id, body, keep-frontmatter)` for **one source directly — no scan at the Pass-2 stage** (the orchestrator already scanned once). Resolution (make-before-break, Task #73 precedent):

- **`kdb-old-compile`** — the current monolithic `kdb-compile` is renamed and frozen as a transitional safety net / reference. Retired once the orchestrator is validated.
- **`kdb-compile` (rebuilt)** — the per-source **compiler core**: a **produce-not-write** library function (`compile_source(source_id, body, frontmatter, …) → cr`) holding stages **3 → 6** (Pass-2 compile · validate · reconcile · canonicalize). It writes **nothing** to disk and returns the compiled `cr`. The orchestrator imports it directly (no subprocess, per D-91-12). May retain a thin CLI for single-source debug compiles.
- **`kdb-orchestrate`** — the E2E conductor: scan (1–2) + per-source loop calling the compiler core + **apply-pages (8) + manifest commit (7+9) + graph-sync (10), all at the per-source commit boundary** + cleanup.

Stage redistribution (revised 2026-05-29 per panel review — apply-pages moved to the orchestrator; see *Produce-don't-write* below):

| Stage | New home |
|---|---|
| 1–2 scan + validate-scan | orchestrator |
| 3 Pass-2 compile | compiler core (`kdb-compile`) |
| 4 validate compile_result | compiler core |
| 5 reconcile | compiler core |
| 6 canonicalize | compiler core (per-source; not cross-source-batch-bound) |
| 7 manifest delta | orchestrator commit (uses post-embed hash) |
| **8 apply pages** | **orchestrator (at commit boundary)** — `build_page_patches` + write; owns provenance (`current_hash`/`current_mtime`) |
| 9 persist | orchestrator (per-source commit) |
| 10 graph sync | orchestrator |

---

## Component: Pass-2 ingress — `compile_source` input contract

### What Pass-2 actually consumes (grounded in current `compile_one`, `compiler.py:209`)
Per source, `compile_one` needs only:
- `source_id` (vault-relative path)
- `source_name` — basename (today `Path(job.abs_path).name`)
- `source_text` — the **body** (prompt + word count)
- `frontmatter` (`SourceFrontmatter`) → `source_meta_dict = {domain, source_type, author, summary}` threaded into the prompt (D-89-17; `summary` = Pass-1 verbatim + `key_themes` appended, D-89-19)
- `context_snapshot` (from GraphDB)

Today `CompileJob` carries only `(source_id, abs_path, context_snapshot)`, so `compile_one` **re-reads the source from `abs_path`** (`:259`). Combined with the planner's own read (to seed the snapshot), the source is read from disk **twice per compile** — and Pass-1 enrich read it a third time.

### Ingress contract
The egress handoff `(source_id, body, keep-frontmatter)` already carries everything `compile_one` needs (keep-frontmatter maps directly onto `source_meta_dict`). The rebuilt core exposes:

```
compile_source(source_id, body, frontmatter, conn, *, context_snapshot=None, mode, resolver, …) → CompileSourceResult
   1. context_snapshot = context_snapshot or build_context_snapshot(conn, source_id, source_text=body, frontmatter, mode, resolver)  # only GraphDB read; or pre-built by caller
   2. Pass-2 (compile_one internals) on in-memory (source_id, source_name, body, frontmatter, context_snapshot)   # NO disk read
   3. validate (4) → reconcile (5) → canonicalize (6)
   → CompileSourceResult(cr, failure_stage, exception_type, error)   # produce-not-write: NO apply-pages, NO disk writes
```

This eliminates **both** downstream re-reads — Pass-2 runs entirely on the in-memory egress payload — and writes nothing. The orchestrator consumes `cr` for **stage 8 apply-pages (`build_page_patches` + write)**, **graph-sync**, and **manifest commit**, all at the per-source commit boundary.

### Produce-don't-write — `compile_source` returns `cr`, orchestrator owns writes (decision 2026-05-29, 5-model panel)
Earlier drafts had `compile_source` run apply-pages (stage 8) and write wiki files itself. The external panel (`docs/task91-plan1-review-synthesis.md`) flagged two coupled problems, both resolved by moving stage 8 out:

- **Dirty disk on pre-commit failure (5/5 unanimous).** Wiki writes inside `compile_source` land *before* the orchestrator's manifest commit, so a case-(a) failure (D-91-13) could leave wiki pages on disk for an un-committed source — violating "manifest untouched." **Fix:** `compile_source` writes nothing; the orchestrator runs `build_page_patches` + write at the commit boundary, alongside manifest + graph-sync, so wiki/manifest/graph commit together (subject to the D-91-13 case-(a)/(b) boundary).
- **Provenance leak.** `build_page_patches` needs the source's `current_hash`/`current_mtime` for page frontmatter — orchestrator-owned values. With stage 8 in the orchestrator, `compile_source` sheds the `source_hash`/`source_mtime` params entirely; the orchestrator already holds the post-embed hash + stat mtime at commit.

**Cross-source page-merge — accepted single-user trade-off (4/5, code-confirmed).** In the monolith, `canonicalize._merge_page_intents` merged same-canonical-slug pages *across* a batch of sources (union of `outgoing_links`/`supports_page_existence`). Per-source compilation passes a **one-element `cr`**, so that cross-source merge is vacuous — two sources defining the same concept page in one run become **last-writer-wins** on the wiki page. This is **accepted for v1**: the **graph stays authoritative** (each source's `apply_compile_result` lands its `SUPPORTS` edges correctly, so the graph knows all supporters); only the wiki *page body* loses the union, and per `[[feedback_obsidian_wikilinks_are_vanity]]` the wiki is a projection. `kdb-audit` (Task #93) is the out-of-band reconciler that detects + (opt-in `--fix`) repairs wiki↔graph `source_refs` drift from the graph's `SUPPORTS` truth.

**Error model.** All pre-commit failure modes (model / validate-gate / canonicalize / context-snapshot read) return `CompileSourceResult(cr=None, failure_stage, exception_type, error)` — the orchestrator routes on `failure_stage` (no string parsing) for the D-91-13 case-aware run summary.

**Optional pre-built snapshot.** `compile_source` builds the snapshot from `conn` by default, but accepts an optional `context_snapshot` so the orchestrator can own all graph reads if a later connection strategy or the #92 context-loader redesign wants it — and so the core can be unit-tested graph-free.

> **Validated content seam (test evidence).** `kdb_compiler/tests/test_t2_end_to_end_pass1_path.py::test_t2_structured_path_live` (Task #90 Phase E, Joseph-fired live) proves the *content* contract this ingress depends on: Pass-1's `entity_search_keys` → `build_context_snapshot` → `ContextSnapshot.pages` resolves to the seeded entities (keys → T2 hits). This is the "two ends of the tunnel meet in the middle" run. **Caveat:** it exercises the *old* plumbing — `enrich_one` writes to disk, then `planner.plan` re-reads from disk (`planner.py:157`) and opens its own batch connection. The new in-memory egress→ingress handoff (`compile_source` with zero disk reads) is **not** covered by it; the Phase-2 test plan must add coverage for the in-memory path.

### Adaptation to existing `compile_one` (minimal surgery, reuse)
Extend `CompileJob` with optional in-memory fields:
```python
source_text: str | None = None              # in-memory body from egress
frontmatter: SourceFrontmatter | None = None
```
`source_text_for(job)` prefers these when present, else falls back to `parse_source_file(job.abs_path)`:
- **Orchestrator path:** populated → zero disk reads in compile.
- **Legacy `kdb-old-compile` / planner path:** left `None` → reads from disk as today (backward-compatible).

`source_name` derives from `source_id` (`Path(source_id).name`). The egress frontmatter (a Pass-1 envelope dict) converts to `SourceFrontmatter` via `SourceFrontmatter.from_dict`.

### Input 4 — prompt + schema (the container the other three enter)
The four per-call Pass-2 inputs all land inside the single prompt `prompt_builder.build_prompt` assembles (verified 2026-05-29):

| Input | Prompt destination |
|---|---|
| source body | `## SOURCE CONTENT` |
| kept frontmatter (`source_meta`) | `## PASS-1 SOURCE METADATA` — domain/source_type/author/summary, **TRUSTED: "do NOT re-derive"** (D-89-17; `build_prompt(source_meta=…)`, `prompt_builder.py:154,135`) |
| existing_context_list | `## EXISTING CONTEXT (graph snapshot)` (`context_snapshot.to_dict()`) |
| prompt + schema (the container) | system = vault-owned `KDB-Compiler-System-Prompt.md` + `RESPONSE_CONTRACT`; user tail = `## RESPONSE SCHEMA` (`compiled_source_response.schema.json`) + `## EXAMPLE RESPONSE` |

- **Reused unchanged by the rebuild.** `compile_source` calls `build_prompt` with the **in-memory** `source_text` + `source_meta` (from kept frontmatter) + `context_snapshot`. No prompt-builder surgery — pure reuse.
- **System prompt is vault-owned + `@cache`'d per `vault_root`** → read once per run, not per source. Operator edits the invariants doc without a code change.
- **Standing invariant (not a rebuild concern):** `RESPONSE_CONTRACT` mirrors `validate_compiled_source_response.semantic_check` — prompt-contract and validator must not drift (enforced by code comments).
- **One Phase-2 test-plan item (input-4's only live action):** the **model benchmark** exercises this prompt to score models against the *old monolithic* compile path. Post-rebuild it must re-point to `compile_source`/`build_prompt` directly — a *cleaner* target than the disk-scanning monolith. Flagged with the in-memory-path coverage gap.

> **Ingress status: all four Pass-2 inputs accounted for and wired.** Input 3's T2/T3 redesign is parked in `docs/nw9-context-list-t2-t3-redesign-hypothesis.md` (does not block); input 4's benchmark re-point is a test-plan item, not a design gap.

### Forward flag — RESOLVED in *Component: Orchestrator loop* (2026-05-29)
Context for source N+1 must see source N's **committed** graph mutations. Resolved empirically against Kuzu 0.11.3 → **single read-write connection threaded through the loop** (read-after-write is immediate and free). See the orchestrator-loop section's *Graph connection structure* for the probe evidence and rejected alternatives.

---

## Component: Orchestrator loop

### Graph connection structure — single read-write connection (decision 2026-05-29, empirically grounded)

The load-bearing question carried forward from Pass-2 ingress: across a per-source loop where each source commits graph mutations, how must connections be structured so source N+1's context read sees source N's committed writes?

Probed directly against **Kuzu 0.11.3** (`/tmp/kuzu_raw_probe.py`, `/tmp/kuzu_loop_probe.py`):

| Observation | Result |
|---|---|
| Single connection: write → read (auto-commit) | reader sees its own write **immediately** |
| Two connections off the *same* read-write `Database` | reader-conn sees the other conn's commit **live** |
| Separate `read_only` `Database`, held open across a writer's commit | **pinned to its open-time snapshot — never sees later commits**; only reopening picks them up |

**Decision:** the orchestrator opens **one read-write `GraphDB` for the whole run** and threads its connection through every per-source `compile_source(...)` (context read) and graph-sync `apply_compile_result(...)` (graph write). Read-after-write across sources is immediate and free; no per-source reopen, no snapshot staleness. This **replaces the planner's batch read-only connection** (`_graph_conn_or_raise`, `read_only=True`, `planner.py:206`) — the orchestrator owns the connection lifecycle for the loop, and `build_context_snapshot` (already `conn`-parameterized) receives the orchestrator's shared connection instead of the planner self-opening one.

- **Why not "keep one reader open + trust Kuzu to surface writes" (old spec option 1):** disproven — a separate `read_only` Database is snapshot-pinned at open (row 3). Non-viable.
- **Why not reopen a read-only reader per source (option 2):** correct (a fresh reader sees prior commits) but strictly more overhead — a `Database` open + schema check per source — for no benefit, since the loop never needs read-only isolation.
- **Failure behavior:** `apply_compile_result` is atomic per source; a failed source rolls back only its own mutation and leaves the shared connection usable. Combined with fail-fast (D-91-8), connection longevity across the run is safe.

> **Latent bug surfaced (flag, not fix — out of #91 scope, per surgical-changes discipline).** `GraphDB._open()` (`graphdb_kdb/graphdb.py:54`) **ignores the `read_only` constructor flag** — it always constructs `kuzu.Database(path)` read-write. So the planner's `read_only=True` yields a read-write Database (which is also why `_ensure_schema`'s DDL never fails on the supposedly read-only path). Harmless for the orchestrator (we *want* read-write), but it means there is currently **no true read-only guard anywhere in the codebase**. File as a separate cleanup task.

### Per-source routing (walked 2026-05-29)

The loop runs on the single shared read-write connection. Scan output splits into a **compile queue** (NEW + MODIFIED) processed first, a **delete queue** (DELETED + MOVED reconcile ops) processed after, then a **finalize** stage. Three per-source branches:

**Branch 1 — NEW/MOD + `kdb_signal=signal` (full path).**
```
Pass-1 enrich_one → embeds frontmatter into the .md AND recomputes the
                    post-embed whole-file hash right there (decision 2026-05-29);
                    returns (body, envelope incl. kdb_signal, post_embed_hash)
  → gate: signal
  → Pass-2 compile_source(source_id, body, frontmatter, conn)   # validate→reconcile→canonicalize inside; returns cr
  → COMMIT sequence:
       apply-wiki pages (build_page_patches + write, stage 8)
       manifest write (post-embed hash)            ← COMMIT BOUNDARY (D-91-13 case a│b)
       archive sidecar + run journal (replayable for graphdb-kdb rebuild)
       graph-sync: apply_compile_result(cr, single-source scan, conn, detect_orphans=False)
```
Next source's context read sees this source's committed graph mutation (verified: interleaved auto-commit read + explicit `BEGIN/COMMIT` write on one connection).

**Branch 2 — NEW/MOD + `kdb_signal=noise` (metadata-only).**
```
Pass-1 enrich → gate: noise (LLM judgment OR config force_noise override)
  → NO Pass-2, NO graph-sync
  → commit: [A] embed frontmatter + recalc hash → manifest write (compile_state=metadata_only, post-embed hash)
```
Tracked so it is never re-enriched; never graphed (e.g. `Daily Notes/`).

**Branch 3 — DELETED / MOVED (reconcile path, no file).**
```
no Pass-1 / Pass-2
  → graph-sync: apply_compile_result(empty compiled_sources, single-source scan{to_reconcile:[op]}, conn, detect_orphans=False)
       DELETED → _handle_source_deleted (drop SUPPORTS, Source.status='deleted')
       MOVED   → _handle_source_moved   (transfer SUPPORTS; D-91-9 scoped per-root)
  → manifest: tombstone (DELETE) / path-update (MOVE)
```
Per D-91-14 (Shape A): zero new mutation channel — reuses the existing compile-event path with empty `compiled_sources`.

### Orphan-marking is deferred to end-of-run — NOT per-source (decision 2026-05-29; Joseph delegated to assistant judgment, principle-checked)

> **Ratification basis:** Joseph delegated the call (insufficient context to sign off directly) on the condition it follows core principles. Checked: the deferral is the *simpler* design (restores monolith batch semantics, removes the redundant per-source orphan scan, one default-`True` flag + extract an existing function) — it lands on the right side of [[feedback_no_imaginary_risk]] (removes complexity, not adds it), reversibility (legacy path unchanged), and make-before-break. The one judgment exercised: prevention (keep entity visible) over cure (canonicalize cleanup), justified because cure only catches variants with known/emitted aliases and variant-prevention is the project's central thesis.

**The catch.** `_detect_and_mark_orphans` (ingestor Phase 4, `ingestor.py:679`) does `SET p.status='orphan_candidate'`, **overwriting `'active'`**; context construction loads only `WHERE e.status='active'` (`_load_active_entities`, `graph_context_loader.py:141`). If Phase 4 ran inside each per-source `apply_compile_result`, a MODIFIED source dropping its old SUPPORTS could transiently orphan an entity that a *later* source in the same run is about — hiding it from that source's context read and re-introducing the **variant creation** the context list exists to prevent.

**Decision.** Per-source `apply_compile_result` runs with **`detect_orphans=False`** (Phases 1–3.5 only — source-upsert, reconcile, compiled_sources, aliases). Orphan-marking/revival (Phase 4) runs **once, globally, at finalize** — immediately before cleanup — restoring batch semantics (orphan status computed once, after every SUPPORTS drop+add). This *also* eliminates the redundant per-source global orphan scan flagged earlier — one change, two wins.

- **Minimal surgery:** add `detect_orphans: bool = True` to `apply_compile_result` (default preserves `kdb-old-compile`/legacy behavior); extract Phase 4 as a standalone `detect_orphans(conn, run_id)` the orchestrator calls at finalize.
- **Residual gap (parked for #92):** a *prior-run* `orphan_candidate` re-supported early this run stays invisible to later context reads until finalize Phase 4 revives it — minor variant risk, caught by the canonicalize cure layer. Flag for the context-loader redesign (`docs/nw9-context-list-t2-t3-redesign-hypothesis.md`), where the context-read filter could become "has-current-support OR active."

### Fail-fast (D-91-8 + D-91-13 carried forward)
Any source's Pass-1 OR Pass-2 failure aborts the whole run immediately — no skip-and-continue, no partial commit. Two-phase boundary = the manifest write:
- **(a) pre-commit failure** (model / validate / canonicalize / patch-apply / manifest-write) → source NOT committed, manifest untouched; the in-flight graph-sync (if reached) `ROLLBACK`s cleanly (verified: rolled-back txn leaves no leak). A **patch-apply** failure may leave orphan wiki pages on disk with no manifest entry — the accepted **self-healing edge**: the next run re-detects the source (hash mismatch) and overwrites, and `kdb-audit` (#93) reconciles any orphan wiki pages out-of-band.
- **(b) post-manifest graph-sync failure** → manifest + wiki + sidecar committed, live graph stale → remediation `graphdb-kdb rebuild`. Exit 4; summary distinguishes "not committed" vs "committed-but-graph-sync-failed."

**Connection-model note (D-91-13 still maps cleanly):** graph-sync moved from batch-end to per-source on the live shared connection, but the commit boundary is unchanged — manifest-write still separates case (a) from (b); the per-source `BEGIN/COMMIT` is what makes a case-(a) rollback leak-free.

### Ordering correctness
Compile-queue-before-delete-queue is **correctness-invariant**: because orphan status is computed once at finalize (after all SUPPORTS drops *and* adds), transient within-run orphan/revival states don't affect the final graph. Within the compile queue, per-source read-after-write holds (verified).

### Finalize stage (walked 2026-05-29)
Runs **only after a fully-successful source loop** — a fail-fast abort (D-91-8) exits before finalize. On the shared read-write connection, in order:

1. **`detect_orphans(conn, run_id)`** — the deferred global Phase 4 (the single orphan-status computation point per the decision above): mark `orphan_candidate` / revive re-supported entities.
2. **`kdb-clean orphans` (D-91-4)** — `apply_cleanup` `DETACH DELETE`s entities left `orphan_candidate` with zero support. Direct Python API (D-91-12), not subprocess. Full reconciliation per run.
3. **`last_orchestrate.json` (D-91-10)** — slim run summary, written **always** (success *and* abort): `run_id`, timestamps, exit code + reason, counts, `manifest_delta`. On abort it records the failing source and the D-91-13 case-(a)/(b) distinction.

- **Abort interaction:** an aborted run skips orphan-mark + cleanup entirely — safe, because nothing this run marked orphans (deferral) and the next successful run reconciles. The summary still records the abort.
- **`--dry-run`:** no side effects → no embed/manifest writes, no graph-sync, no orphan-mark, no reaping; summary still emitted. (Supersedes D-91-11's feeder-skip premise — see entry point.)

### Entry point — pipeline selection (walked 2026-05-29)
```
load pipeline registry (KDB/state/pipelines.json via pipeline_registry loader)
  → list pipelines → select one (interactive pick OR --pipeline=ID)
  → load selected pipeline's scope (root, excludes, force_noise/force_signal, file_types)
  → open the shared read-write GraphDB connection
  → scan(root, scope) → {NEW, MOD, DEL} → enter the per-source loop
```

**Resolves the flagged `--feeders` drop (Feeder section).** The orchestrator does **NOT** run feeders — they are independently triggered, strictly upstream of the scan. So the v0.2 blueprint's `--feeders=NAME` flag (D-91-11, which ran feeders *before* scan) is **dropped**; pipeline selection only chooses the scan scope. D-91-11's "`--dry-run` skips feeders" clause is therefore moot for the orchestrator (it never runs them) — `--dry-run` now means "scan + plan, no writes." **This supersedes D-91-11's feeder-running premise.**

### Parked (implementation-plan altitude, not routing decisions)
- Artifact-shape mapping: `compile_source` return → the `cr` dict `apply_compile_result` consumes (`compiled_sources[].pages`, `canonical_meta.aliases_emitted`).
- Transaction granularity of the finalize mutations (`detect_orphans` + cleanup) on the shared connection.
