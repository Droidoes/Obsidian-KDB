# Session Handoff — 2026-05-28 EOD — `kdb-orchestrate` E2E design session

Design/brainstorming session (no code changed). Walked the end-to-end orchestrator architecture component-by-component with Joseph, capturing each settled piece into a **living design spec**: `docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md`.

**Framing pivot from where Task #91 v0.2 left off:** the v0.2 blueprint (`docs/task91-kdb-orchestrate-blueprint.md`) modeled a per-source world against the *pre-split monolithic* `kdb-compile`. This session reflects the real, decomposed architecture: `feeder → ingestion (Pass-1) → compiler (Pass-2) → GraphDB`, with `kdb-orchestrate` as the conductor. The new spec **supersedes the blueprint's §4 compile-driving assumptions** where they conflict.

---

## Settled this session (all in the spec)

- **Commonality principles** — P1 ingestion pipeline = unit of selection; P2 one common scanner (dumb filesystem diff); P3 one unified `KDB/state/manifest.json`; P4 vault-in-place is the "special" pipeline (no feeder, in-place scope).
- **Feeder** — acquisition/materialization adapter (native source → `.md` in `KDB/raw/pipeline-<name>/`); **independently triggered, NOT run by the orchestrator**; strictly upstream of the scanner; full-mirror so deletes fall out of the common scanner. Vault feeder = identity (Joseph authors in place).
- **Scanner** — `(root_dir, scope_config)` → NEW/MOD/DEL; `find … -name "*.md"` + hash-vs-manifest.
- **Pipeline membership / DELETED scoping** — explicit **`pipeline_id` tag** on each manifest source entry (Joseph reversed the earlier "path-prefix is the tag" lean → readable + safe + robust to scope-config edits). DELETED pass = `pipeline_id == selected` & absent on disk.
- **Pipeline registry (global config)** — `KDB/state/pipelines.json` + loader `kdb_compiler/pipeline_registry.py`; unifies the old `scan_roots.json` + `feeders.json`. Schema: `id / type / root / excludes / force_noise / file_types / feeder`. **`excludes` (never scanned) vs `force_noise` (scanned+enriched but forced noise → tracked, not graphed, e.g. Daily Notes)** are distinct.
- **Hash basis** — **whole-file hash, recalculated AFTER embed** (Joseph's call; body-hash rejected as fragile to whitespace/split). Manifest stores the post-embed hash → breaks the re-enrich loop. (Assistant conceded its `PASS1_PROMPT_VERSION` mass-reflag worry was wrong: UNCHANGED files are never re-enriched.)
- **Pass-1 egress** — `[A] embed + recalc hash` then `[B] compile`, sequential (not parallel). **Force-override** (config-driven `force_noise` dirs → force `kdb_signal=noise`) is distinct from the **gate** (final `kdb_signal`: signal → Pass-2, noise → stop at enrich, `compile_state=metadata_only`). Handoff payload = `(source_id, body, keep-frontmatter)`.
- **`kdb-compile` rebuild** — rename current monolith → `kdb-old-compile` (frozen safety net); rebuild `kdb-compile` as the per-source **compiler core** (`compile_source(...)`, stages 3→6+8, library fn + optional debug CLI); `kdb-orchestrate` owns scan (1–2) + loop + manifest commit (7+9) + graph-sync (10) + cleanup. Stage-redistribution table ratified.
- **Pass-2 ingress** — `compile_source(source_id, body, frontmatter, conn, …)` runs entirely on the in-memory egress payload; collapses today's **triple disk read** (enrich + planner + compile_one). Adaptation: extend `CompileJob` with optional in-memory `source_text`+`frontmatter`; `source_text_for` prefers them, falls back to disk for the legacy path.
- **Interruption/resume** — DEFERRED (re-run; per-source commits cost ≤1 file).

---

## Pick up first thing tomorrow — the orchestrator loop (#1)

Walk the orchestrator's own control flow, where the carried-forward flags come due:
1. **Per-source loop** — NEW/MOD (→ ingest→compile) vs DELETE (→ reconcile→graph→cleanup) routing; fail-fast (D-91-8); **embed-at-commit sequencing** (avoid orphan frontmatter on a failed source); per-source manifest commit + graph-sync.
2. **Graph read-after-write visibility** — context for source N+1 must see source N's committed mutations (planner opens one read-only conn per batch today; per-source loop needs re-open/refresh or confirmed Kuzu visibility).
3. **Cleanup** as final step (`kdb-clean orphans`, D-91-4).
4. **Run summary** (`last_orchestrate.json`, D-91-10).
5. **Entry point** — pipeline selection (list → pick → load config).

Then: finish the spec → spec self-review → Joseph reviews → `writing-plans` to produce the implementation plan → light review → Phase A–E execution.

---

## Repo / housekeeping state
- **Branch:** `main`, in sync with `origin/main` at `c87434a` (the "4 commits ahead" in yesterday's handoff had already been pushed).
- **Uncommitted:** the new design spec (`docs/superpowers/specs/2026-05-28-kdb-orchestrate-e2e-design.md`) + this handoff. **Not yet committed** — awaiting Joseph's go.
- **`gws tasks` CLI note:** `--params` can no longer repeat; use a single JSON blob (`--params '{"tasklist":"@default","showCompleted":false}'`). Worth updating the `session-catchup` skill.
- Carried-forward (untouched): NW-5 Pass-1 benchmark · tutorial promotion review · GraphDB-KDB stray-file anomaly.
