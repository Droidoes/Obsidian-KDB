# Phase B Migration — Panel Review Synthesis

**Panel:** Codex · Deepseek · Qwen · Gemini · Grok (5/5 read-only, guardrail-clean). **Date:** 2026-06-02.

## Verdict tally
| Reviewer | Verdict | Named blocker |
|---|---|---|
| Codex | GO-WITH-FIXES | viewer packaging ambiguity |
| Deepseek | GO-WITH-FIXES | 2 scripts + setup.sh stale paths |
| Qwen | GO-WITH-FIXES | 2 scripts (broken import) |
| Gemini | GO-WITH-FIXES | test pkgs leak into wheel |
| Grok | **GO** | none (pre-existing nits only) |

**Consensus: GO-WITH-FIXES.** Zero correctness regressions in the live pipeline (unanimous). The one real restructure — the `resp_stats_writer` split — was independently verified **byte-identical + leaf-clean** by 4/5 (Codex, Deepseek, Qwen, Grok): the lifted `parsed_summary` gate matches the old internal condition exactly, and `common/llm_telemetry` imports nothing from `compiler` (not even under `TYPE_CHECKING` — a strict improvement). No new vacuous/false-green tests (Qwen, Gemini, Grok confirm; the two we already fixed — the parsed_summary gate + D34 guard — verified de-vacuumed).

## Findings by convergence

### Must-fix before tag
- **F1 — stale `kdb_compiler.manifest_update` imports in 2 historical scripts** `scripts/migrate_task64_supersession.py:27`, `scripts/migrate_task66_compiled_hash.py:37`. **[4/5: Deepseek-High, Qwen-High, Gemini-Low, Codex-Low]** Will `ModuleNotFoundError` on run. **Verified:** the functions (`assert_manifest_invariants`, `_supersede_omitted_pages`) no longer exist anywhere live (they were in the deleted `manifest_update`), so repointing is impossible → **hard-guard** (top-of-file `sys.exit("retired historical script…")` above the broken import) or archive. Both are already marked HISTORICAL at line 2; the guard just makes the failure honest. (Satisfies surface-don't-delete.)
- **F2 — `__version__ = "0.1.0-m0"` stale** `common/__init__.py:1`. **[1/5: Deepseek-Low — but essential for a v0.5.2 tag]** Bump to `0.5.2`.
- **F3 — `setup.sh:63,65` stale** **[1/5: Deepseek-Med]** line 63 references the dropped `kdb-compile --help`; line 65 references the moved `kdb_compiler/tests/test_m2_first_compile.py`. Fix to `kdb-orchestrate --help` + new test path (or drop the optional smoke line).

### Should-fix (cheap, fold in)
- **F4 — `test_package_boundaries.py:4-5` INTERNAL set** **[3/5: Codex, Deepseek, Gemini]** duplicate `"kdb_graph"`; missing removed roots `graphdb_kdb`/`kdb_benchmark`. Dedup + add the old roots so the guard catches a future stale import from a removed package (Codex's enhancement). Keep `kdb_compiler` (intentional — classifies a hypothetical stale import as illegal, per Deepseek).
- **F5 — exclude `*.tests` from wheel** **[2/5: Codex-Low, Gemini-Med]** package discovery ships `compiler.tests`/`kdb_graph.tests`/etc. into the wheel. Add `"*.tests", "*.tests.*"` to `[tool.setuptools.packages.find].exclude`. (Cleanliness; moot under the project's editable-only workflow but correct.)
- **F6 — stale operator-facing text** **[1/5: Codex-Low]** `tools/cleanup.py` docstring/argparse still describes pre-D50 manifest cleanup + `kdb-compile`; `tools/viewer/kdb_graph_viewer.py` usage text references old `tools/viewer-bakeoff/` + `python tools/kdb_graph_viewer.py` paths. Refresh.

### Defer to post-merge follow-up tasks (not blockers)
- **Viewer packaging ambiguity** **[Codex-Med, his only blocker]** `tools/viewer/` has no `__init__.py`, no console script, and package-data ships `viewer/*.html` but not `viewer/*.py` → a real wheel would omit the viewer module. **Moot today** (project is editable-install/source-checkout only, never builds wheels), but the partial packaging is ambiguous. Follow-up: either make `tools.viewer` a real package + `kdb-graph-viewer` console script, or document source-only and drop the HTML-only package-data.
- **`compiler.compiler` double-name** **[Grok-Med]** `from compiler.compiler import …` is awkward in traces/IDE. It was ratified in the B.2 map; rename to `compiler/pass2.py` (with `__init__` re-export) is an optional follow-up.
- **`orchestrator → tools.cleanup` decoupling** **[Gemini-Low; 4/5 accept the deferral]** Gemini suggests moving cleanup's core to `kdb_graph` so neither orchestrator nor the CLI couples to a tool. The deferral was a ratified decision (decoupling changes when the cleanup journal is written — behavior change, out of move-only scope). Acceptable for v0.5.2; follow-up if desired.

### Non-actionable
- Deepseek's "planner removal is a scope deviation from the brief" (Info) is a **misread** — the brief retired `planner`/`run_compile` in **Phase A** (Part 3 "settled by fact"), not Phase B. Already gone before this branch. No action.
- `kdb-validate --help` failing (Grok, Codex-noted) is **pre-existing** — the validator takes a path arg and has no `--help`; the move only updated the entry-point string. Not a regression.

## Bottom line
The migration is correct and safe to tag after a small pre-tag pass: **F1–F3 (must), F4–F6 (cheap, fold in)**. The three larger items (viewer packaging, `compiler.compiler` rename, cleanup decoupling) are ratified-or-moot and belong in follow-up tasks. Apply the fixes → merge `refactor/phase-b-package-split` → tag `v0.5.2`.
