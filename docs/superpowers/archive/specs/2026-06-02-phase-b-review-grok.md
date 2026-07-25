# Phase B Migration — Grok Code Review

**Verdict:** GO

## Findings

### (a) correctness bugs
- [Low] tools/replay.py:8 (docstring) and the root `tests/fixtures/response_replay/` layout: the replay fixtures live at repo-root `tests/fixtures/` (outside any package) and the CLI docstring hard-codes the path for `kdb-replay --replay tests/fixtures/response_replay/`. This works from a source checkout but will not be present after a non-editable wheel install (tests/ is excluded from packaging). Pre-existing (not introduced by the move); the fixtures are dev/regression pins, not runtime data. No behavior change for the intended single-user workflow.
- [Low] compiler/validate_compile_result.py:300 (main): `kdb-validate --help` (and any non-path argv[1]) does `Path(sys.argv[1]).read_text()` and emits "ERROR: [Errno 2] No such file or directory: '--help'" + exit 2. The sibling `kdb-validate-response` has proper argparse. The entry point resolves and the module loads, but this CLI never supported --help gracefully. Pre-existing (the move only updated the entry-point target string); the plan's verification loop would have printed "FAIL: kdb-validate". Not a regression.

No Critical/High/ Medium behavior-drift or contract-violation bugs found in the executed moves.

### (b) test-fidelity gaps (vacuous/false-green/lost coverage)
- [Low] compiler/tests/test_resp_stats_writer.py (whole file): filename and module docstring still refer to the removed `resp_stats_writer` / `kdb_compiler.resp_stats_writer`. It now does `import common.llm_telemetry as resp_stats_writer` + `from compiler.resp_summary import ...` and continues to provide the old coverage (safe_source_id, build_resp_stats, write, etc.). Not vacuous — the tests still execute the new locations and the new split tests (`test_resp_summary_split.py`, `test_parsed_summary_gate.py`) exist — but the stale filename is misleading post-split. (Commits mention prior de-vacuum work on other guards.)
- [Low] common/tests/test_layering_leaf.py:27: still contains `m.startswith("kdb_compiler.enrich") or ...` alongside the live `ingestion.enrich` check. Harmless (the old name will never match now) and serves as a regression belt for the Phase-A inversion fix, but is noise.
- [None] The D34 producer-agnostic guard in kdb_graph/tests/test_snapshot.py was updated (per commit f13fecb) from checking the removed `kdb_compiler` literal to live names (`compiler`, `ingestion`, `orchestrator`). No other obvious string-literal guards on removed package names were found in production tests after sweeping.

No lost coverage detected; the +16 new guard/split tests and redistributed test count (~1191 non-live) align with the plan's claims. The boundary guard (`tools/tests/test_package_boundaries.py`) passes cleanly.

### (c) packaging & data-file risks
- [Low] pyproject.toml + CLI verification: the plan's Task 13 gate includes a loop that does `"$c" --help >/dev/null 2>&1 && echo ok || echo "FAIL: $c"` for the 9 entry points. `kdb-validate` will always hit the "FAIL" path (see (a)). The other 8 resolve. The package-data globs and `[project.scripts]` targets are correctly updated for the six packages. `pip install -e .` succeeds for all.
- [Low] Root-level `tests/fixtures/` (response_replay cases) and `benchmark/` (data corpus: sources/truth/runs/scores): these are excluded via `exclude = ["...tests*", "benchmark*"]` and are not under package dirs. They are intentionally dev-only artifacts (replay pins + benchmark corpus). `kdb-replay --replay ...` and `kdb-benchmark` commands expect them relative to CWD in a checkout. Not packaged into wheels (correct), but the docstring in tools/replay.py still advertises the path. No runtime breakage for the documented use.
- Package-data globs were verified against actual files:
  - `ingestion = ["config/*.json", "config/*.yaml", "enrich/*.j2"]` → matches `domains.json`, `source_types.json`, `scope-config.yaml`, `pass1_prompt.j2`.
  - `compiler = ["schemas/*.json"]` → the two compiler schemas.
  - `tools = ["benchmark/models.json", "diagnostics/*.json", "viewer/*.html"]` → models.json + last_scan.schema.json + the main `kdb_graph_viewer_template.html` (bakeoff/ subdir files are not claimed by the glob and are review artifacts).
- Path resolution (Path(__file__).parent) for schemas, templates, models.json, and last_scan.schema were spot-checked and match the moves (e.g. validate_last_scan now looks beside itself in diagnostics/, no "/schemas/" subdir; pass1_prompt uses _TEMPLATE_DIR = parent of .py which contains the .j2).
- No `importlib.resources` / pkg_resources usage found that would be sensitive to editable vs wheel; all loads are sibling-Path based (works for both once package-data includes the non-.py files).
- `[tool.setuptools.packages.find]` include/exclude and testpaths are updated and list the six packages + their tests (including the explicit `tools/benchmark/tests`).
- The root `conftest.py` (graph isolation + factories) + per-package tests/ redistribution succeeded; full non-live collection under the new testpaths works.

No wheel was built (per project norm), but the declarations + Path loads + guard test for template render + data-smoke imports give high confidence.

### (d) cleanliness/naming nits
- [Medium] Naming collision inside the "compiler" package: the directory `compiler/` contains `compiler.py` (the Pass-2 orchestration). This produces import paths of the form `from compiler.compiler import compile_source` (and `compiler.compiler.compile_one` in some traces). Functional and consistent with the old `kdb_compiler.compiler`, and explicitly shown in the ratified B.2 map, but it is an awkward double-name that will confuse readers, IDE jump-to, and stack traces. Could have been `compiler/pass2.py` / `from compiler.pass2 import ...` or `compiler/compile.py` with an `__init__` re-export for a cleaner public surface. Not a bug, but a lasting smell from preserving the old module name inside the new peer package.
- [Low] Several modules (e.g. compiler/compiler.py, ingestion/kdb_scan.py) received updated module docstrings describing the new six-package pipeline positions. Good hygiene, but some still carry long "Pipeline position" blocks that duplicate the North Star.
- [Low] The `orchestrator → tools.cleanup` edge is the one deliberate contract exception (orchestrate.finalize calls reap/build_cleanup inline). The dependency guard (`test_package_boundaries.py`) and North Star explicitly document it and assert that nothing else imports tools. Per the plan, full decoupling is a behavior change (would alter when/ how the cleanup journal is written) and was out of move-only scope. Acceptable for Phase B; worth a follow-up task post-merge if desired.
- [Low] `kdb_graph` (the package) vs. `graphdb-kdb` (unchanged CLI name) is correctly handled (package rename only). A few direct-run scripts (viewer/*.py, bakeoff/export) still do `sys.path.insert` + absolute import; they were updated for the new name.
- Stale-ref sweeps (kdb_compiler.*, graphdb_kdb, resp_stats_writer, etc.) return clean results in production .py files outside the intentional alias in the legacy-named test file and historical scripts/ (the latter are explicitly marked "one-shot, already applied, modules no longer exist").
- `__version__` moved to common/__init__.py; importers (benchmark) updated.
- No new circular imports introduced (smoke imports of all six packages + boundary guard pass; leaf-first extraction order was followed).

## Bottom line

Safe to merge and tag (e.g. v0.5.2 / v0.5.1 per the North Star). The Phase B execution is a faithful, leaf-first, move-don't-rewrite split. The critical `resp_stats_writer` split correctly lifted the `build_parsed_summary` gate (condition is byte-identical to the old internal one), `common/llm_telemetry` is a true leaf, the B.3 contract is guard-tested with the one documented exception, all entry points resolve, data-file paths and package-data globs are correct, redistributed tests + new guards pass, and sampled diffs show only import rewrites, doc updates, and the two intended splits/lifts. 

The only items are pre-existing UX details (kdb-validate's strict argv handling) and naming awkwardness (`compiler.compiler`) plus minor stale test filenames/comments that do not affect correctness or the run-7 gate. No hidden behavior drift or lost coverage was found. Once Joseph confirms the live run-7, this is ready. (Any post-merge polish on the double-"compiler" name or CLI help consistency can be a tiny follow-up.)

**All investigation used only read-only commands and file reads per the hard guardrail. Output written exclusively to this file.**