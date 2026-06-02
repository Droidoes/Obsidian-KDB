# Codebase Realignment — Panel Review Synthesis

**Date:** 2026-06-01. **Panel:** Codex (C) · DeepSeek (D) · Qwen (Q) · Gemini (G) · Grok-build (K).
**Inputs:** the five `2026-06-01-codebase-realignment-review-*.md` files. All five reviewers verified claims
against the repo (read-only). **Verdict: unanimous GO** — execute the A-then-B refactor before 0.6.

---

## 1. Convergence tally

| Item | C | D | Q | G | K | Consensus |
|---|:-:|:-:|:-:|:-:|:-:|---|
| Whole refactor is GO, before 0.6 | ✓ | ✓ | ✓ | ✓ | ✓ | **5/5 load-bearing** |
| A-then-B cut is the right seam | ✓ | ✓ | ✓ | ✓ | ✓ | **5/5** |
| All 5 renames correct | ✓ | ✓ | ✓ | ✓ | ✓ | **5/5** |
| Retire `kdb_compile.py` + 427-ln `run_journal.py` is safe | ✓ | ✓ | ✓ | ✓ | ✓ | **5/5** |
| `kdb-compile` must NOT stay bound to legacy driver | ✓ | ✓ | ✓ | ✓ | ✓ | **5/5** |
| `validate_last_scan`: keep as diagnostic, not delete | ✓ | ✓ | ✓ | ✓ | ✓ | **5/5 (keep module)** |
| Layering fix = move parser DOWN to common (+ `SourceFrontmatter`→`common/types`) | ✓ | ✓ | – | ✓ | ✓ | **4/5** (Q: invert call) |
| `context_loader` module stays compiler; raw reads → graph API | ✓ | ✓ | ✓ | ~ | ✓ | **5/5 once A.3 done** (G wanted graph; satisfied by API) |
| CLI: drop `kdb-old-compile`/`kdb-compile-sources`/`kdb-plan` bindings | ✓ | ✓ | ✓ | ✓ | ✓ | **5/5** |
| `resp_stats_writer` home | comp+common (split) | comp | comp | common | comp | **SPLIT** |
| `pipeline_registry` home | ingestion | orch | orch/common | orch/common | orch | **SPLIT (orch plurality)** |
| A.3/A.4 in A vs early-B | A | A | A | A(~) | early-B | **3–4 for A** |
| `kdb-compile`: drop vs re-point | either | drop | drop | re-point | drop | **drop plurality** |

---

## 2. Load-bearing — fold in, no debate (5/5)

1. **Execute the refactor before 0.6.** Every reviewer affirmed the timing thesis independently.
2. **A-then-B seam holds.** Fix-in-place, then mechanical relocation.
3. **All five renames stand:** `reconcile→repair`, `patch_applier→page_writer`, `ingestion→enrich`,
   `source_state_update→source_state_writer`, `validate_compiled_source_response→validate_source_response`.
   *(G note: `source_state_*` is a pure-logic module, not I/O — `source_state_updater` marginally more precise;
   non-blocking.)*
4. **Retirement of the legacy driver + its 427-ln journal is verified safe.**
5. **Layering fix (4/5):** move the pure frontmatter parser (`parse_existing_frontmatter`) **down** to
   `common` (in `source_io` or a tiny `common/frontmatter`); move `SourceFrontmatter` into `common/types` to
   kill the `types→source_io` `TYPE_CHECKING` edge. Then `common` is a true leaf. *(Q preferred inverting the
   call so enrich depends on source_io; the 4-way move-down is cleaner and the others' default.)*
6. **`validate_last_scan`: keep the module** as a scan diagnostic (relocate to `tools/diagnostics` or
   `ingestion/scan/validate`); decide its CLI binding separately (see forks).
7. **CLI drops:** `kdb-old-compile`, `kdb-compile-sources`, `kdb-plan` (bindings only — modules stay importable).

## 3. Settled by fact (resolves a 4-vs-1 panel split)

**`planner` + `compiler.run_compile` are dead** (Gemini correct). `run_compile` — the sole caller of
`planner.plan()` — is invoked only by `kdb_compile.py` (legacy) and compiler.py's `kdb-compile-sources` entry.
Live paths use `compile_source` (orchestrate) and `compile_one` (benchmark); neither calls `planner`. The
others' "planner is live" was import-reachability, not execution. **→ Retire `planner` + `run_compile` with the
batch path** (the only nuance: `run_compile` sits inside the live `compiler.py`, so excising it edits a live
file to remove dead code — low-risk, but it *is* a code change, so gate it with tests).

## 4. New catches beyond the brief — fold in

- **`manifest.json` is a disk-noun that lies (Codex — his top catch; Grok echoes).** `source_state_writer`
  writes to a file still named `manifest.json`, though D50 made it source-state-only. The thesis ("names that
  lie") applies to the **persisted state layer**, not just modules. → Rename to `source_state.json` (with a
  one-time migration) **or** document `manifest.json` as a retained compat filename. **Decision needed.**
- **Dual `run_journal` collision (DeepSeek + Grok — high-value).** After the 427-ln one retires, rename the
  surviving `ingestion/run_journal.py` → `enrich_journal.py` to prevent a future orchestrator-journal collision.
- **Add `graph_context_loader → context_loader` to the A.1 rename list (DeepSeek).** And **A.3 is bigger than
  "replace imports" (Codex):** the loader runs ~7 distinct raw-Cypher operations; `graphdb_kdb.queries` doesn't
  yet expose a context-snapshot API. A.3 needs an **intentional graph read-API design**, not a mechanical swap.
- **Stale-reference sweep belongs in A.5:** deleted `manifest_update.py` still referenced in
  `CODEBASE_OVERVIEW.md` + two `scripts/`; `kdb_compiler/__init__.py` advertises the old linear pipeline;
  `adapters/` + `canonicalize.py` comments name `kdb_compile.py`.
- **Test infra (Gemini + Qwen):** delete `test_kdb_compile.py` + `test_validate_last_scan.py` in A; **B.5 needs a
  conftest/fixtures separation plan** (centralized `tests/conftest.py` + shared fixtures don't split for free);
  retire/relocate `last_scan.schema.json` with its validator.
- **B must update `pyproject` package-discovery, package-data (schemas/Jinja), and pytest testpaths** (Codex,
  Qwen) — else imports pass locally but installed entry points miss data files.
- **`graphdb_kdb → graph` rename caution (Codex):** plain `graph` collides mentally with graph libraries; prefer
  Python pkg `kdb_graph` (or keep `graphdb_kdb`) while keeping the `graphdb-kdb` CLI name.
- **Pre-existing live-test bug (Gemini), tangential to refactor:** `test_t2_*` seeds concepts but no
  `Domain`/`BELONGS_TO`, so the same-domain gate empties the context snapshot. Log as a separate bug.

## 5. Open forks — your call (panel genuinely split)

1. **`resp_stats_writer` home — compiler vs common.** Compiler (D, Q, K: fan-in is actually **1** today, purely
   Pass-2 telemetry) vs common (G, C: enrich/feeders also make LLM calls and **can't import compiler** under the
   dependency contract). C's clean middle: **split** — generic record-building → `common/llm_telemetry`,
   compiler-specific `ParsedSummary` → `compiler`. *Lean:* C's split (future-proofs the contract cheaply); or
   keep in compiler now and promote when enrich actually needs telemetry (data-before-principle).
2. **`pipeline_registry` home — orchestrator vs ingestion.** Orchestrator (D, K, Q/G default) vs ingestion-config
   (C: it *describes* ingestion; 0.6 feeders *are* pipeline definitions). *Lean:* orchestrator for B; revisit when
   feeders land — or pre-empt with `ingestion/config` per C.
3. **A.3 + A.4 in A, or early-B?** In A (C, Q, D — they're the fixes that make the relocation correct) vs first
   steps of B if they balloon (K; G neutral). *Lean:* keep in A, but **scope-check A.3** — if the graph-API
   design grows, let it lead B instead.
4. **`kdb-compile` — drop or re-point to `kdb-orchestrate`?** Drop (D, Q, K — "compile" is dead vocabulary) vs
   re-point with a deprecation warning (G — muscle memory; C: either, just not on the legacy driver). *Lean:*
   re-point with a one-release deprecation notice, then drop — kind to your fingers, still honest.
5. **`manifest.json` on disk — rename to `source_state.json` (with migration) or document as compat?** (from §4).
   *Lean:* rename — it's the same lie the whole refactor exists to kill; do it with a migration in A.
6. **`graphdb_kdb` package name — keep, or `kdb_graph`, or `graph`?** *Lean:* `kdb_graph` (avoid generic `graph`),
   keep `graphdb-kdb` CLI.

## 6. Next step

Fold §2–4 into the brief as **v2** (the locked scope), and record §5 as your adjudicated decisions. Then the brief
becomes the ratified blueprint → writing-plans for the Phase A implementation plan.
