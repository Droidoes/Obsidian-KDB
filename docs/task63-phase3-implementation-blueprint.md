# Task #63 — Phase 3 Implementation Blueprint: Rename Pass + B-lite Rebuilder + Stage 9 Wiring

**Status:** Implementation blueprint — awaiting explicit "Proceed" before any code lands.

**Date:** 2026-05-14.

**Scope:** Three sub-tasks bundled as a unified work package:

- **#63.5b** — Rename pass (D-A1: `Page → Entity`; D-A2: `Source.compile_*` field renames)
- **#63.6** — B-lite rebuilder (D-B1 generic replay core + Obsidian adapter; D-S2 blast radius; D-S3 version support; D-S1 namespace declaration scaffolding)
- **#63.7-pre** — Stage 9 wiring via adapter (D-S0: `sync_current_run` from `kdb_compile.py`); sidecar archival.

**Why bundled.** These three sub-tasks share files (the new adapter + the rename surface) and have a shared TDD cadence. Splitting them across commits is fine; designing them in isolation would create false abstractions.

**Companion docs** (locked in commit `e5caca5`):
- `docs/task-graphdb-kdb-blueprint.md` (§2 D-A1..S3, §14 L8, §14.1 TR-1/2/3)
- `docs/graphdb-kdb-extraction-roadmap.md`
- `docs/manifest-succession-arc.md`
- `docs/graphdb-kdb-producer-contract.md`

---

## 1. Pre-flight checks

Before any code change:

- [ ] Suite green at baseline: `pytest graphdb_kdb/` → 76/76 pass.
- [ ] No uncommitted local changes.
- [ ] One run journal in `~/Obsidian/KDB/state/runs/` opened end-to-end so the adapter author has a real example. (Already confirmed in handoff doc 2026-05-14: `state/runs/2026-04-21T17-48-32_EDT.json` is the latest; `schema_version` = `2.0`; eligibility fields present.)
- [ ] Live `state/compile_result.json` + `state/last_scan.json` are readable (canonical-corpus baton from 2026-04-21).

---

## 2. Sub-task #63.5b — Rename pass

### 2.1 Scope (D-A1 + D-A2)

**D-A1 (`Page → Entity`)**:
- Node table name in DDL.
- All Cypher strings referencing `:Page` label.
- `Page` dataclass in `graphdb_kdb/types.py` → `Entity` dataclass.
- All function/method signatures, variable names, and docstrings referencing `Page`.
- CLI label strings (e.g., `--top N pages` → `--top N entities`; user-facing output).
- All test assertions touching the above.

**D-A2 (Source field renames)**:
- `compile_state` → `ingest_state` (DDL + dataclass field + all readers)
- `compile_count` → `ingest_count` (same)
- `last_compiled_at` → `last_ingested_at` (same)

**NOT renamed**:
- `Entity.page_type` (values still Obsidian-flavored: `summary | concept | article`; rename waits for producer #2)
- `Entity.status`, `Entity.confidence` (same reasoning)
- The `compile_result.json` payload shape (that's the *producer's* terminology; adapter translates)
- The `pages` key inside `compiled_sources[*]` of the mutation payload (producer's terminology)

### 2.2 Affected files (inventory)

| File | Change |
|---|---|
| `graphdb_kdb/schema.py` | `CREATE NODE TABLE Page` → `Entity`; rename 3 Source fields in DDL |
| `graphdb_kdb/types.py` | `class Page` → `class Entity`; rename 3 `Source` dataclass fields |
| `graphdb_kdb/graphdb.py` | `get_page` → `get_entity`; Cypher strings; `Page` type hints |
| `graphdb_kdb/ingestor.py` | `_upsert_page` → `_upsert_entity`; Cypher strings; argument variable names |
| `graphdb_kdb/queries.py` | `(:Page ...)` → `(:Entity ...)` throughout; method names where appropriate; type hints |
| `graphdb_kdb/analytics.py` | Cypher topology fetch queries; result mapping |
| `graphdb_kdb/verifier.py` | Field-name comparisons (`compile_state` ↔ manifest's `compile_state` — caution: manifest still uses old names; the verifier's MANIFEST-side dictionary lookups stay unchanged; only graph-side reads update) |
| `graphdb_kdb/cli.py` | Subcommand help text; output labels; argparse option descriptions |
| `graphdb_kdb/__init__.py` | Public exports: `Page` → `Entity` |
| `graphdb_kdb/tests/test_*.py` | All assertions and synthetic fixtures touching renamed names (~76 tests; estimated 50-60 lines of test edits) |
| `docs/task-graphdb-kdb-blueprint.md` | §4 schema DDL; §5 ingestion algorithm Cypher; §6 API surface; §7 Stage 9 skeleton (also touched by #63.7-pre); §10 test descriptions; §11 sub-task wording (TR-1 sweep) |

### 2.3 Verifier subtlety — important

The verifier compares Kuzu graph to `manifest.json`. After the rename:

- **Graph side**: emits `entity_type`, `ingest_state`, `ingest_count`, `last_ingested_at` as Python dict keys when reading from Kuzu.
- **Manifest side**: still has `page_type` (under `pages.<path>.page_type`), `compile_state`, `compile_count`, `last_compiled_at` (under `sources.<id>.*`) because manifest is owned by `manifest_update.py` which we're NOT changing in #63.5b.

The verifier must **map** between the two name spaces in its comparison function. Add a small `_field_alias_map` dict in `verifier.py`:

```python
SOURCE_FIELD_ALIASES = {
    # graph_side_name: manifest_side_name
    "ingest_state":     "compile_state",
    "ingest_count":     "compile_count",
    "last_ingested_at": "last_compiled_at",
}
ENTITY_FIELD_ALIASES = {
    "entity_type": "page_type",  # if/when D-A2 renames page_type — currently NOT renamed
}
```

For #63.5b: only `SOURCE_FIELD_ALIASES` is populated; `ENTITY_FIELD_ALIASES` stays empty (D-A2 leaves `page_type` alone). Document the alias map's purpose in a comment: "manifest's vocabulary is producer-side; graph's vocabulary is ontology-side; the verifier bridges across when they diverge."

### 2.4 TDD approach

Mechanical rename is unusual for TDD because tests get renamed *alongside* the implementation, not before. Recommended approach:

1. Update test fixtures + assertions to expect new names (test file edits).
2. Run tests → expect failures (old code emits old names).
3. Update implementation (DDL + module renames).
4. Run tests → expect green.
5. Spot-check: drop the Kuzu test DB; recreate from new schema; verify shape.

**Important**: there is no behavior change. Tests that pass with old names should pass with new names. Any test failure post-rename is a typo in the sweep, not a real bug.

### 2.5 Acceptance criteria

- [ ] `pytest graphdb_kdb/` → 76/76 green (same count as before; no test added/removed in this sub-task).
- [ ] Fresh Kuzu DB created via `graphdb-kdb init` shows `Entity` table (not `Page`) via `CALL show_tables() RETURN *`.
- [ ] No `Page` string remains in `graphdb_kdb/*.py` (outside comments referencing historical names if any).
- [ ] No `compile_state` / `compile_count` / `last_compiled_at` strings in `graphdb_kdb/*.py` outside the verifier's alias map.
- [ ] Blueprint TR-1 sweep complete (§4, §5, §6, §10, §11 reflect new names).
- [ ] Manifest file unchanged (still uses producer-side names; verifier handles the bridge).
- [ ] `graphdb-kdb verify` on the canonical corpus (after a fresh `graphdb-kdb rebuild --backfill-baton`, see #63.6) reports zero divergence — *deferred until #63.6 lands*; during #63.5b in isolation, verify works against synthetic fixtures only.

### 2.6 Estimated effort

1-2 hours of mechanical sweep + 30 min blueprint update. Low risk; high mechanical churn.

---

## 3. Sub-task #63.6 — B-lite Rebuilder

### 3.1 Scope (D-B1 + D-S2 + D-S3 + D-S1 scaffolding)

**Generic replay core** in `graphdb_kdb/rebuilder.py`:
- `rebuild(graph_dir: Path, adapter: ProducerAdapter, *, confirm: bool = True) -> RebuildResult`
- Drops all tables + recreates schema (whole-DB per D-S2)
- Discovers runs via `adapter.discover_runs(...)`, sorts by `sort_key`, iterates chronologically
- For each: `adapter.is_eligible(...)` → eligible runs get `adapter.load_payload(...)` + `adapter.apply(...)`; ineligible get recorded with skip_reason
- Returns `RebuildResult` with replayed/skipped/failed counts + per-run details
- Prints whole-DB-drop warning before executing (unless `confirm=False` for tests)

**Adapter base interface** in `graphdb_kdb/adapters/base.py`:
- `class ProducerAdapter` (Protocol or abstract base; lean: duck-typed ABC for v1)
- `class RunDescriptor` dataclass (`run_id`, `sort_key`, `journal_path`)
- `class EligibilityResult` dataclass (`eligible: bool`, `skip_reason: SkipReason | None`)
- `SkipReason` Literal type (5 values)
- `class UnsupportedJournalVersionError(Exception)`

**Obsidian adapter** in `graphdb_kdb/adapters/obsidian_runs.py`:
- `class ObsidianRunsAdapter`
- ClassVars: `source_type = "obsidian-kdb-raw"`, `entity_id_namespace = None` (grandfathered per D-S1), `supported_journal_versions = ["2.0"]` (per D-S3)
- `discover_runs(journals_dir: Path) -> list[RunDescriptor]`
- `is_eligible(descriptor) -> EligibilityResult`
- `load_payload(descriptor) -> tuple[dict, dict, str]`
- `apply(mutation, scan, run_id, conn) -> SyncResult` (delegates to `graphdb_kdb.ingestor.apply_compile_result`)
- `sync_current_run(mutation, scan, run_id, graph_dir=None) -> SyncResult` (D-S0; #63.7-pre uses it but the method ships here)

**CLI subcommand**: `graphdb-kdb rebuild [--vault-root P] [--producer obsidian] [--backfill-baton] [--yes] [--json]`
- Default `--producer obsidian` (the only adapter for now)
- `--backfill-baton` (one-shot migration entry for the latest pre-#63 run, per Q3 outcome (d) — see §3.3)
- `--yes` skips the interactive whole-DB-drop confirmation
- `--json` outputs `RebuildResult` as structured JSON

### 3.2 Generic core architectural details

```python
# graphdb_kdb/rebuilder.py (sketch)

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from graphdb_kdb.adapters.base import ProducerAdapter, EligibilityResult, SkipReason
from graphdb_kdb.graphdb import GraphDB


@dataclass
class RunOutcome:
    run_id:      str
    state:       str  # "replayed" | "skipped" | "failed"
    skip_reason: SkipReason | None = None
    error:       str | None = None


@dataclass
class RebuildResult:
    replayed:  int = 0
    skipped:   int = 0
    failed:    int = 0
    outcomes:  list[RunOutcome] = field(default_factory=list)


def rebuild(
    graph_dir: Path,
    adapter:   ProducerAdapter,
    *,
    journals_dir: Path,
    confirm: bool = True,
) -> RebuildResult:
    """Drop the entire Kuzu graph and replay eligible runs in chronological order.

    Per D-S2: always whole-DB drop. Per D-B1: caller-supplied adapter handles
    producer-specific eligibility, payload loading, and mutation translation.
    """
    if confirm:
        _print_drop_warning(graph_dir)  # prints "this will drop the whole DB"

    with GraphDB(graph_dir) as graph:
        graph._drop_all_tables()
        graph._ensure_schema()

        descriptors = adapter.discover_runs(journals_dir)
        descriptors.sort(key=lambda d: d.sort_key)

        result = RebuildResult()
        for desc in descriptors:
            elig = adapter.is_eligible(desc)
            if not elig.eligible:
                result.skipped += 1
                result.outcomes.append(RunOutcome(desc.run_id, "skipped", elig.skip_reason))
                continue
            try:
                mutation, scan, run_id = adapter.load_payload(desc)
                adapter.apply(mutation, scan, run_id, graph._conn)  # internal handle
                result.replayed += 1
                result.outcomes.append(RunOutcome(run_id, "replayed"))
            except Exception as e:
                result.failed += 1
                result.outcomes.append(RunOutcome(desc.run_id, "failed", error=f"{type(e).__name__}: {e}"))

    return result
```

**Open implementation question**: `graph._drop_all_tables()` and `graph._conn` are notionally private. Decision needed at implementation time: expose these as public or refactor `rebuild` into a `GraphDB.rebuild_with_adapter()` method that has internal access. Lean: keep `rebuild` standalone for testability + composability; introduce a small internal API (`graph._drop_all`, `graph._raw_connection`) marked internal but accessible.

### 3.3 Backfill mode — Shape B per blueprint §13.1 outcome (d)

The handoff doc (2026-05-14) surfaced Shape A vs Shape B. Decision: **Shape B**, implemented via `--backfill-baton` CLI flag (off by default).

When `--backfill-baton` is supplied:
- Read `<vault-root>/KDB/state/compile_result.json` and `<vault-root>/KDB/state/last_scan.json` (the overwritten baton).
- Read `<vault-root>/KDB/state/manifest.json` and extract `runs.last_successful_run_id` as the synthetic `run_id` (this is the run that produced the baton).
- Verify no sidecar exists at `<vault-root>/KDB/state/runs/<last_run_id>/` (if one exists, the baton was already archived; skip the backfill silently — idempotency).
- Synthesize a `RunDescriptor(run_id=last_run_id, sort_key="0000-pre-63-backfill", journal_path=None)` so it sorts first chronologically.
- The adapter's `is_eligible` for descriptors with `journal_path=None` returns `EligibilityResult(eligible=True, skip_reason=None)` automatically (the existence of the descriptor implies opt-in).
- The adapter's `load_payload` for `journal_path=None` reads the baton files directly instead of a sidecar.

This is a one-time migration tool. After running once, the baton is in the graph; future runs write their own sidecars; the `--backfill-baton` flag becomes a no-op (idempotency).

**Why Shape B over Shape A**: closes the loop in a single `#63.6` sub-task; no manual migration step needed after merge; the only pre-#63 run that's recoverable gets recovered immediately.

### 3.4 Test plan

| Test | What it verifies | Source |
|---|---|---|
| `test_rebuilder_empty` | Empty journals dir + empty graph → no-op; `RebuildResult(replayed=0, skipped=0, failed=0)` | new |
| `test_rebuilder_one_run` | Single synthetic run with sidecar → 1 replayed; graph has expected entities | new |
| `test_rebuilder_chronological` | 3 synthetic runs out-of-filesystem-order → replayed in correct order (page MOVED through time validates ordering) | new |
| `test_rebuilder_eligibility_dry_run` | Run with `dry_run=true` → skipped with `skip_reason='dry_run'` | new |
| `test_rebuilder_eligibility_failed` | Run with `success=false` → skipped with `skip_reason='failed'` | new |
| `test_rebuilder_eligibility_missing_sidecar` | Run journal exists, sidecar missing → skipped with `skip_reason='payload_missing'` | new |
| `test_rebuilder_eligibility_unsupported_version` | Journal `schema_version='99.0'` → skipped with `skip_reason='unsupported_version'` (no raise; the rebuilder treats it as audit-skip) | new |
| `test_rebuilder_whole_db_drop` | Pre-populated graph + rebuild → existing data wiped | new |
| `test_rebuilder_idempotent` | Two consecutive rebuilds → identical final state | new |
| `test_rebuilder_replay_equals_live` | Same inputs to live ingestion vs rebuild → graph states equal (structural compare) | new |
| `test_rebuilder_backfill_baton` | Synthetic baton files in state/ → backfill produces expected entity set | new |
| `test_rebuilder_backfill_idempotent` | Run backfill twice → second is no-op (sidecar check) | new |
| `test_obsidian_adapter_discover` | Adapter discovers run journals from synthetic `state/runs/*.json` | new |
| `test_obsidian_adapter_normalize_eligibility` | Adapter reads producer's `success`/`dry_run` fields, returns canonical `EligibilityResult` | new |

**Total**: 14 new tests; brings suite to ~90.

### 3.5 Acceptance criteria

- [ ] All previously-passing tests still green (76 → 90).
- [ ] `graphdb-kdb rebuild --vault-root ~/Obsidian --backfill-baton` on the canonical corpus produces the same entity/source/edge counts as the current manifest (62 pages, 4 sources, 100 LINKS_TO, 62 SUPPORTS).
- [ ] `graphdb-kdb verify --vault-root ~/Obsidian` after rebuild reports zero divergence.
- [ ] `graphdb-kdb rebuild` without `--backfill-baton` on a fresh corpus (no sidecars yet) reports 0 replayed + 0 skipped + 0 failed (clean no-op).
- [ ] CLI prints the whole-DB-drop warning unless `--yes` supplied.
- [ ] Adapter's `entity_id_namespace = None` and `supported_journal_versions = ["2.0"]` declared; misuse (e.g., journal v3.0) returns clean skip.
- [ ] `pytest graphdb_kdb/` → ~90 green.

### 3.6 Estimated effort

3-4 hours: ~200 LOC for rebuilder.py + ~150 LOC adapter + ~250 LOC tests + CLI plumbing.

---

## 4. Sub-task #63.7-pre — Stage 9 wiring via adapter

### 4.1 Scope (D-S0)

Wire `kdb_compile.py`'s Stage 9 to call the Obsidian adapter's `sync_current_run` (which the adapter ships in #63.6).

**Files affected**:

| File | Change |
|---|---|
| `kdb_compiler/kdb_compile.py` | Add Stage 9 block after Stage 8 success; calls `obsidian_runs.sync_current_run(...)`; non-fatal per D38 |
| `kdb_compiler/run_journal.py` | Update `STAGE_NAMES` from 8 to 9 elements (`"graph_sync"` added); `_STAGE_TOTAL = 9` |
| `kdb_compiler/scanner.py` or wherever sidecars are written | After successful run, atomic-copy `state/compile_result.json` → `state/runs/<run_id>/compile_result.json` and `state/last_scan.json` → `state/runs/<run_id>/last_scan.json` (creates the sidecar dir if needed) |
| `kdb_compiler/tests/` | New integration test for end-to-end Stage 9 |

### 4.2 Stage 9 skeleton

```python
# kdb_compiler/kdb_compile.py — Stage 9

_stage_open(9)
try:
    from graphdb_kdb.adapters.obsidian_runs import ObsidianRunsAdapter
    adapter = ObsidianRunsAdapter()
    sync_result = adapter.sync_current_run(cr, scan_dict, run_id)
    _stage_close(
        9, ok=True,
        pages_upserted=sync_result.pages_upserted,
        edges_upserted=sync_result.edges_upserted,
        sources_upserted=sync_result.sources_upserted,
        orphans_detected=len(sync_result.orphans_detected),
    )
except Exception as exc:
    # Per D38: graph_sync failure is non-fatal. Log + journal, continue.
    note = f"{type(exc).__name__}: {exc}"
    _stage_close(9, ok=False, note=note, recovery_hint="run: graphdb-kdb rebuild --vault-root <path>")
    # NO call to _fail(); the overall run remains successful.
```

**Critical**: this Stage 9 imports `graphdb_kdb.adapters.obsidian_runs` (the adapter). It does **not** import `graphdb_kdb.GraphDB` or `graphdb_kdb.ingestor` directly. This is the literal expression of D-S0.

### 4.3 Sidecar archival

After Stage 8 (manifest write) succeeds and before Stage 9 (graph sync) — or as an early step of Stage 9; design choice — the compile pipeline copies the freshly-written baton into the per-run sidecar:

```python
def _archive_sidecar(state_root: Path, run_id: str) -> None:
    """Copy state/{compile_result,last_scan}.json to state/runs/<run_id>/."""
    sidecar_dir = state_root / "runs" / run_id
    sidecar_dir.mkdir(parents=True, exist_ok=True)
    for fname in ("compile_result.json", "last_scan.json"):
        src = state_root / fname
        dst = sidecar_dir / fname
        atomic_copy(src, dst)  # write-then-rename for atomicity
```

**Where to place this call**:
- **Option α**: Stage 8.5 (between manifest write and graph sync, in `kdb_compile.py`)
- **Option β**: Inside Stage 9's adapter call (the adapter's `sync_current_run` archives the sidecar as its first step, before calling apply)
- **Option γ**: Standalone Stage 9, separate from graph_sync

Lean: **Option α** — keep "archive sidecar" as a separate concern from "sync to graph." Archival should happen even if graph_sync fails (so the next rebuild can recover that run). Sidecar archival is fast (~100 ms for typical baton size), atomic-write, and non-fatal in its own right.

### 4.4 Test plan

| Test | What it verifies | Source |
|---|---|---|
| `test_stage9_lifecycle` | End-to-end: `kdb-compile` on synthetic corpus → Stage 9 fires; graph has new data; sidecar archived | new |
| `test_stage9_non_fatal` | Simulate adapter raising mid-Stage-9 → run journal records `success=true` overall + Stage 9 `ok=false` | new |
| `test_sidecar_archival` | Sidecar at `state/runs/<run_id>/{compile_result,last_scan}.json` exists post-run; byte-identical to baton | new |
| `test_sidecar_atomic` | Simulated crash mid-archival → no partial sidecar (atomic-write-then-rename) | new |
| `test_rebuild_after_compile` | Run compile → run `graphdb-kdb rebuild` → graph state identical to post-compile state | new |
| `test_stage9_imports_only_adapter` | Static assertion: `kdb_compile.py` imports `graphdb_kdb.adapters.obsidian_runs`, never `graphdb_kdb.GraphDB` directly | new (or invariant check) |

**Total**: 6 new tests; brings suite to ~96.

### 4.5 Acceptance criteria

- [ ] All previously-passing tests still green (90 → 96).
- [ ] One fresh `kdb-compile` run on the live vault: produces Stage 9 success in journal; sidecar exists at `state/runs/<run_id>/`; `graphdb-kdb verify` reports zero divergence post-run.
- [ ] `kdb-compile.py` does NOT contain `from graphdb_kdb import GraphDB` or `from graphdb_kdb.ingestor import apply_compile_result` — only the adapter import.
- [ ] Sidecar archival happens even when graph_sync fails (test simulates).
- [ ] `STAGE_NAMES` and `_STAGE_TOTAL` updated in `run_journal.py`.

### 4.6 Estimated effort

2-3 hours: Stage 9 wiring is small; sidecar atomic-copy needs care; integration test setup needs fixture work.

---

## 5. Commit sequencing

Three discrete commits, in order:

1. **`refactor(task63.5b): rename Page→Entity + Source.compile_*→ingest_*`**
   - All #63.5b changes.
   - `pytest graphdb_kdb/` → 76/76 green at commit.
2. **`feat(task63.6): B-lite rebuilder + Obsidian adapter`**
   - All #63.6 changes (`rebuilder.py`, `adapters/`, CLI plumbing, 14 new tests).
   - `pytest graphdb_kdb/` → 90/90 green at commit.
   - `graphdb-kdb rebuild --backfill-baton` validated against canonical corpus.
3. **`feat(task63.7-pre): Stage 9 wiring via adapter + sidecar archival`**
   - All #63.7-pre changes (Stage 9 in `kdb_compile.py`, sidecar archival, 6 new tests).
   - `pytest` (both `graphdb_kdb/` AND `kdb_compiler/`) → all green.
   - End-to-end live compile validated; `graphdb-kdb verify` reports zero divergence.

Plus the ledger close commits (`docs(tasks): mark #63.5b/.6/.7-pre done — <SHA>`) matching the existing pattern.

---

## 6. Rollback plan

Each sub-task is reversible by `git revert`:

- **#63.5b**: pure mechanical rename; revert restores original names. No data migration needed because the Kuzu DB regenerates from scratch on first connection (the schema check in `_ensure_schema` would detect the version mismatch and re-init).
- **#63.6**: revert removes the new files (`rebuilder.py`, `adapters/*.py`, new tests, CLI subcommand). Existing functionality unaffected.
- **#63.7-pre**: revert undoes the `kdb_compile.py` Stage 9 wiring. Sidecars already-archived become orphaned files on disk (harmless). Manifest write path is untouched throughout.

**The cleanest revert path**: if any of the three sub-tasks regresses badly, revert *that* commit and keep the prior ones. The bundle is *not* atomic; partial-rollback is by design.

---

## 7. Cross-references

- **D-A1, D-A2** (rename): `docs/task-graphdb-kdb-blueprint.md` §2.
- **D-B1** (B-lite split): same.
- **D-S0** (Stage 9 via adapter): same.
- **D-S1** (entity-id namespacing): `docs/graphdb-kdb-producer-contract.md` §3.5.
- **D-S2** (blast radius): blueprint §2 + §14 L8.
- **D-S3** (version support): blueprint §2 + `docs/graphdb-kdb-extraction-roadmap.md` PR9.
- **Producer-contract adapter interface**: `docs/graphdb-kdb-producer-contract.md` §4.
- **Q3 outcome (d) backfill rationale**: blueprint §13.1 Q3.
- **Manifest succession M0 precondition**: `docs/manifest-succession-arc.md` §5 M0 — explicitly notes Stage 9 wiring lands at #63.7-pre.

---

## 8. Open questions for team consensus (before Proceed)

| ID | Question | My lean |
|---|---|---|
| **OQ-I1** | `--backfill-baton` opt-in vs default-on for first invocation? | **Opt-in**. Don't surprise the operator with auto-backfill. The first invocation should be deliberate. |
| **OQ-I2** | `rebuild` confirmation prompt: interactive prompt vs `--yes` always required? | **Interactive prompt by default; `--yes` skips.** Match `rm -i` / `gh pr close` conventions. |
| **OQ-I3** | Sidecar atomic-copy: shell `cp` + `mv` or Python `shutil.copy` + `Path.rename`? | **Python**. Avoids subprocess overhead; portability; testable in pytest. |
| **OQ-I4** | Stage 9 wiring location: end of `kdb_compile.py` main loop, vs separate function called from main? | **Separate function**. `_stage9_graph_sync(cr, scan, run_id)` mirrors existing `_stage8_*` pattern. |
| **OQ-I5** | Test fixture for adapter: real Kuzu DB in `tests/tmp/` (per existing pattern) or mocked Kuzu? | **Real Kuzu**, matches existing #63.1–#63.5 discipline. Fast enough at this scale. |
| **OQ-I6** | `UnsupportedJournalVersionError` — eager raise vs return skip? | **Skip with reason**, per the SkipReason literal. Eager raise breaks replay tolerance; skip lets the rebuilder report and continue. |
| **OQ-I7** | Sub-task numbering: keep `#63.5b` or renumber as `#63.10`/`#63.11`/`#63.12`? | **Keep `#63.5b/.6/.7-pre`** — `.5b` is honest about being mid-stream; `.7-pre` signals it's the *adapter-wiring* piece of #63.7 (the full Stage 9 wiring per blueprint §11 also includes additional plumbing that might separate). |

---

## 9. "Proceed" gate

Before any code lands:

1. Review this blueprint and resolve OQ-I1 through OQ-I7.
2. Confirm sub-task sequencing + commit boundaries acceptable.
3. Explicit "Proceed" from the user.
4. Open `#63.5b`, `#63.6`, `#63.7-pre` in `docs/TASKS.md` (status `in-progress` for the first, `pending` for others).
5. Start with `#63.5b` via the mechanical sweep workflow described in §2.4.

---

## 10. What this document does NOT do

- Does not write any code.
- Does not change `docs/TASKS.md` (that's the open-the-tasks step at Proceed time).
- Does not commit anything (work-in-progress).
- Does not change the verifier's behavior beyond the alias-map note (true rewrite is post-M3 per TR-2).
- Does not address `kdb-graph` (the future Obsidian-view utility — out of #63 scope per locked decisions).
