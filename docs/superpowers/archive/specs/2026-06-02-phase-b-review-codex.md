# Phase B Package Split Review - Codex

## 1. Verdict

**GO-WITH-FIXES**

I did not find a core pipeline correctness regression in the package split itself. The compiler/orchestrator telemetry split preserves the old `build_resp_stats` parse-summary gate, schema/config/template paths appear covered by package data, and the documented `orchestrator -> tools.cleanup` exception is explicit and tested.

The one issue I would fix before tagging `v0.5.2` is the viewer packaging surface: current tests exercise it from the source tree, but the wheel/package configuration does not appear to ship or expose the Python viewer module.

## 2. Findings

### (a) Correctness Bugs

None found.

I specifically checked the riskiest Phase B behavior paths:

- `common/llm_telemetry.py` contains only leaf-safe imports and still receives `parsed_summary` from the compiler.
- `compiler/compiler.py` computes `parsed_summary` only when `parse_ok` is true and the parsed JSON is a dict, matching the old `kdb_compiler.resp_stats_writer` behavior.
- Schema/config/template path moves are internally consistent: compiler schemas remain under `compiler/schemas`, ingestion configs/templates remain under `ingestion/config` and `ingestion/enrich`, diagnostics schema remains under `tools/diagnostics`.
- `orchestrator/kdb_orchestrate.py` imports `tools.cleanup` only for the documented D50 cleanup exception.

### (b) Test-Fidelity Gaps

**Low - Package-boundary test can false-green on old package roots.**

`tools/tests/test_package_boundaries.py:4-5` defines:

```python
INTERNAL = {"common", "ingestion", "compiler", "kdb_graph", "orchestrator", "tools", "kdb_compiler", "kdb_graph"}
```

That set duplicates `kdb_graph` and omits old package roots such as `graphdb_kdb` and `kdb_benchmark`. Current live code does not appear to import those old roots, so this is not evidence of a present runtime bug. It does mean the guard would not catch a future stale import from `graphdb_kdb` or `kdb_benchmark`.

Recommendation: expand the forbidden/known roots to include all old package names from Phase A/B (`kdb_compiler`, `graphdb_kdb`, `kdb_benchmark`) and remove the duplicate `kdb_graph`. Add a direct assertion that non-test package sources do not import old roots.

### (c) Packaging & Data-File Risks

**Medium - `tools/viewer/kdb_graph_viewer.py` is tested from source but not packaged or exposed.**

Evidence:

- `tools/viewer` has no `__init__.py`, so it is not discovered as a package by `pyproject.toml:41`.
- `pyproject.toml:46` includes `tools` package data for `viewer/*.html`, but not `viewer/*.py`.
- `pyproject.toml:25-34` defines console scripts for the main tools, but none for the graph viewer.
- `tools/tests/test_kdb_graph_viewer.py:4-7` imports the viewer by filesystem path with `importlib.util.spec_from_file_location`, bypassing installed-package behavior.
- `tools/viewer/kdb_graph_viewer.py:1-16` presents the file as a single-command builder, but its usage text still references `python tools/kdb_graph_viewer.py`, which is not the current path.

Impact: source-tree tests can pass while an installed wheel omits the viewer Python module. If the viewer is part of the intended shipped tool surface for Phase B, this is a packaging regression. If it is intentionally source-checkout-only, the docs/package data should say that clearly and avoid partially packaging only the HTML asset.

Recommendation: either:

- make `tools.viewer` a real package with `tools/viewer/__init__.py`, add a console script such as `kdb-graph-viewer = "tools.viewer.kdb_graph_viewer:main"`, and update tests to import the installed module path; or
- explicitly document the viewer as source-tree-only and remove/adjust package data so the packaging contract is not ambiguous.

**Low - Test packages may be included in built distributions.**

`pyproject.toml:41-42` includes `common*`, `ingestion*`, `compiler*`, `kdb_graph*`, `orchestrator*`, and `tools*`, while excluding only top-level `tests*`. Because tests live inside package directories, package discovery may include modules such as `compiler.tests`, `kdb_graph.tests`, and `tools.tests` in the wheel.

Impact is mostly distribution cleanliness unless these tests pull optional/dev-only dependencies at import time. It is not a merge blocker for Phase B, but it is worth tightening before publishing broadly.

Recommendation: exclude `*.tests` and `*.tests.*` from package discovery, or confirm that shipping internal tests is intentional.

### (d) Cleanliness / Naming Nits

**Low - Historical migration scripts remain executable-looking but import removed packages.**

`scripts/migrate_task64_supersession.py:26-30` and `scripts/migrate_task66_compiled_hash.py:36-37` still import from `kdb_compiler.manifest_update`, which no longer exists after the split. Both files have comments saying they are historical one-shot migrations and not part of the live pipeline, so this is not a live correctness bug. They still live under `scripts/` with runnable shebangs, which makes the failure mode confusing.

Recommendation: move them to an archive/docs location, or make them fail fast under `if __name__ == "__main__"` with a clear archived-script message before importing removed modules.

**Low - `tools/cleanup.py` user-facing text is stale after D50 graph-backed cleanup.**

The cleanup implementation now states that the manifest no longer stores page/orphan state (`tools/cleanup.py:207-209`) and performs live graph sync (`tools/cleanup.py:279-286`). But the module and CLI help still mention older behavior:

- `tools/cleanup.py:4-7` refers to `kdb-compile` deriving current wiki contents and a `kdb-compile` cleanup flag.
- `tools/cleanup.py:300-304` says cleanup removes manifest `pages`/`orphans` and does not resync GraphDB-KDB.

Impact: operator-facing help contradicts the current architecture. That is exactly the kind of stale text that can cause bad manual recovery decisions.

Recommendation: update the docstring and argparse description/help to describe D50 graph-backed cleanup behavior and `kdb-orchestrate` as the live conductor.

**Low - Viewer usage text still references pre-move paths.**

`tools/viewer/kdb_graph_viewer.py:12` refers to fallback assets under `tools/viewer-bakeoff/`, but the current tree uses `tools/viewer/bakeoff/`. `tools/viewer/kdb_graph_viewer.py:15` says to run `python tools/kdb_graph_viewer.py`, but the file now lives at `tools/viewer/kdb_graph_viewer.py`.

Recommendation: update these strings alongside the packaging decision above.

## 3. Bottom Line

I would merge and tag `v0.5.2` only after resolving the viewer packaging ambiguity, because it is the one finding where source-tree tests can pass while the installed artifact is missing an intended tool.

Everything else is safe to handle as follow-up cleanup: tighten the boundary test roots, decide whether package-internal tests belong in distributions, archive or fail-fast the historical migration scripts, and refresh stale operator-facing text in cleanup/viewer modules.

Tests were not run during this review, per the prompt's read-only review posture and because the findings above came from source/package inspection.
