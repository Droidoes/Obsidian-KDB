# Session Handoff — 2026-04-19 → next session (Sonnet 4.6)

**Branch**: `main`  **Last commit**: `85d4383` M1.6 patch_applier
**Tests**: 193/193 passing (1.0s; 3 env-blocked modules excluded)
**Ahead of `origin/main`**: 11 commits (no remote push yet — deliberate)
**Next milestone**: M1.7 — end-to-end dry-run orchestrator

## Who's driving and why

Opus 4.7 drove M0 → M1.6. The design (D1–D22) is locked; the seam modules are stable; the pure-core + I/O-shell pattern has shipped twice and is proven. M1.7 is **wiring** — call built stages in order — with binary success criteria. That's a clean handoff point for Sonnet 4.6.

**Sonnet scope**: execute M1.7 Phases 2–5 (blueprint → implement → commit).
**Opus returns for**: M2 (planner + compiler + prompt design + first real compile). That's architectural work where stronger reasoning earns its cost.

## Where we are in the roadmap

```
M0        ✅ scaffold + LLM contract
M0.1      ✅ Codex review remediation
M1.1      ✅ foundation modules (atomic_io, paths, run_context, types)
M1.2      ✅ validate_compile_result
M1.3      ✅ call_model + retry (LLM seam)
M1.4      ✅ kdb_scan (hardened v2)
M1.5      ✅ manifest_update (pure core + I/O shell + CLI)
M1.6      ✅ patch_applier (YAML + page/index/log + CLI)
M1.7      ⬜ end-to-end dry-run orchestrator (kdb_compile.py)  ← YOU ARE HERE
M2        ⬜ planner + compiler + prompt_builder + first real compile
```

## M1.7 — locked selection

Phase 1 strategizing already done. Second-opinion (GPT-5.4) concurred. **Do not re-strategize.**

| Decision | Pick | Rationale |
|---|---|---|
| Architecture | **A** — dedicated `kdb_compile.py` orchestrator + integration test | Symmetric with `kdb_scan.py`; grows into M2 without rewriting outer contract |
| Dry-run scope | **(i)** — write nothing anywhere | Binary semantics; matches `manifest_update` / `patch_applier` CLIs |
| Module name | **(a)** — `kdb_compile.py` | Symmetric with `kdb_scan.py` |
| Fixture input | **(b)** — `<state-root>/compile_result.json` convention | Matches `patch_applier` / `manifest_update` CLIs; M2 compiler will write there too |

## M1.7 — blueprint sketch (confirm before implementing)

### Module layout (`kdb_compiler/kdb_compile.py`)

```python
# Public API:
def compile(vault_root: Path, *, dry_run: bool = False,
            run_ctx: RunContext | None = None) -> CompileRunResult

# CLI:
def main(argv=None) -> int  # --vault-root, --dry-run
```

### Pipeline steps inside `compile()`

1. Derive `kdb_root = vault_root / "KDB"`, `state_root = kdb_root / "state"`, `raw_root = kdb_root / "raw"`.
2. Build `RunContext.new(dry_run=dry_run, vault_root=vault_root)` if not supplied.
3. **Scan**: call `kdb_scan.scan(raw_root=..., prior_manifest=...)` — programmatic API, not its CLI. Returns `ScanResult`.
4. **Validate scan**: call `validate_last_scan.validate(scan_as_dict)` — accumulate errors; abort if any.
5. **Load compile_result**: read `<state-root>/compile_result.json` (fixture in M1.7; real compiler output in M2). If missing → return with clear error (do NOT raise NotImplementedError — M2 extensibility means the orchestrator should degrade gracefully).
6. **Validate compile_result**: call `validate_compile_result.validate(cr)` — accumulate; abort if any.
7. **run_id consistency**: scan.run_id must equal cr.run_id (same rule as patch_applier + manifest_update CLIs).
8. **Build next manifest (pure)**: `manifest_update.build_manifest_update(prior, scan_dict, cr, ctx)` → `(next_manifest, journal)`.
9. **Apply pages (or dry-run them)**: `patch_applier.apply(state_root, vault_root, next_manifest=next_manifest, run_ctx=ctx, write=not dry_run)`.
10. **Persist manifest**: `manifest_update.write_outputs(next_manifest, journal, state_root, ctx)` — skip if `dry_run`.
11. Return a `CompileRunResult` with per-stage summary.

### Critical gotcha — state_root ambiguity

`kdb_scan.scan()` reads prior manifest from `<kdb_root>/state/manifest.json` (line 377); it does **not** accept `state_root`. Other stages (`patch_applier`, `manifest_update`) accept explicit `state_root`.

**Resolution for M1.7 (locked)**: orchestrator exposes only `--vault-root`; it derives `state_root = vault_root/KDB/state` internally and passes that derived path to `patch_applier.apply` and `manifest_update.write_outputs`. This matches `kdb_scan`'s hardcoded assumption. No `kdb_scan` refactor needed. If we later want state-root-portable scans, that becomes its own milestone.

### Dry-run semantics (SQ1 = (i))

`--dry-run`:
- scan still runs (pure computation on real raw/), but `last_scan.json` is NOT written to disk.
- validate runs normally.
- build_manifest_update runs (pure).
- patch_applier.apply is called with `write=False` (its existing dry-run path).
- `write_outputs` is skipped entirely.
- Return a summary so the caller can inspect what would have changed.

Note: `kdb_scan.scan()` as currently written **does** write `last_scan.json` in its CLI path. For dry-run, call its programmatic API (bypassing the CLI write) or pass a write-suppress flag if one exists. **Check `kdb_scan.scan()`'s signature before implementing** — if it lacks a programmatic "don't write" option, either (a) use it anyway and accept the scan-writes-in-dry-run carve-out, OR (b) add a minimal flag (small change, worth 2 lines). Prefer (b) for purity; document whichever you pick.

### Result dataclass

```python
@dataclass
class CompileRunResult:
    run_id: str
    success: bool
    scan_counts: dict        # from ScanResult.summary
    pages_written: list[str] # empty on dry_run
    manifest_written: bool
    journal_written: bool
    dry_run: bool
    errors: list[str]        # accumulated validation errors + stage exceptions
```

### CLI output

One line per stage for human operators, final summary line:
```
kdb_compile: scanned 5 raw files · validated scan ✓ · validated compile_result ✓ · 3 pages to write · dry-run (no writes)
```

## Test matrix (target: ~10–14 tests)

Integration tests in `kdb_compiler/tests/test_kdb_compile.py`:

1. **Happy path dry-run**: seed tmp vault with 1 raw file + fixture compile_result; `compile(dry_run=True)` → returns success, no writes.
2. **Happy path wet-run**: same seed; `compile(dry_run=False)` → pages/index/log/manifest/journal all exist; contents match expected.
3. **Missing compile_result.json**: returns non-success with clear error message (no exceptions bubbled).
4. **run_id mismatch between scan and compile_result**: validation fails, no writes.
5. **Malformed compile_result.json**: validation fails, no writes, errors surfaced.
6. **Scan with empty raw/**: succeeds with zero pages; manifest bootstrapped.
7. **Second run (incremental)**: run once, modify source, run again → MANIFEST reflects CHANGED action; page body updated on disk.
8. **Moved file (two-pass rename)**: rename source between runs → MOVED reconcile op; tombstone in manifest; page rekeyed.
9. **Dry-run leaves no artifacts**: scan.json, manifest.json, wiki/*.md all absent after dry-run on a fresh vault.
10. **CLI happy path exits 0**: `python -m kdb_compiler.kdb_compile --vault-root X` succeeds.
11. **CLI dry-run exits 0**: `--dry-run` flag works; verify zero files written.
12. **CLI missing --vault-root exits 2**.
13. **CLI invalid vault (no KDB/)**: exits 1 or 2 with clear message.
14. *(optional)* End-to-end with 3 sources + cross-source concept (exercises multi-source_refs path on both manifest_update and patch_applier).

## pyproject.toml update

Add to existing `[project.scripts]`:
```toml
kdb-compile       = "kdb_compiler.kdb_compile:main"
```
Existing scripts: `kdb-scan`, `kdb-validate-scan`, `kdb-validate`, `kdb-manifest`.

## CODEBASE_OVERVIEW.md update

§5 pipeline already reflects the 7-step corrected ordering (committed in M1.6). No further overview change required for M1.7 — just mention the orchestrator exists in the §5 narrative if you want, optional.

## Working conventions (inherited, do not change)

- **Test command**: `python3 -m pytest kdb_compiler/tests --ignore=kdb_compiler/tests/test_call_model.py --ignore=kdb_compiler/tests/test_call_model_retry.py --ignore=kdb_compiler/tests/test_config.py`. Three env-blocked modules; not M1.7's problem.
- **Python binary**: `python3` (no `python` alias on this WSL env).
- **CLI smoke after implementation**: seed `/tmp/m17_smoke/vault/KDB/raw/` with one markdown file + fixture compile_result at `/tmp/m17_smoke/vault/KDB/state/compile_result.json`, run `python3 -m kdb_compiler.kdb_compile --vault-root /tmp/m17_smoke/vault`, verify wiki/ + state/ outputs.
- **Commit only after explicit user approval** (global CLAUDE.md Phase 5 gate in `~/.claude/CLAUDE.md`).
- **Phase 5 summary format**: What landed, test count, CLI smoke result. Then ask.

## Non-obvious contracts to honor

- **D8**: LLM never emits paths/timestamps/versions. `kdb_compile` never regresses this.
- **D14/D22**: atomic writes only; no locks, no retries beyond the built-in single retry.
- **D15**: write_outputs writes journal BEFORE manifest. Never reorder.
- **D18**: full-body replacement. patch_applier already does this; orchestrator just calls it.
- **D19**: LLM never authors index.md/log.md — Python writes them from manifest + log_entries.
- **D22**: no complexity for imaginary risk. Single user, single process. If you find yourself adding retry ladders, lock files, or multi-phase commits — stop.

## Auto-memory to consult

- `feedback_no_imaginary_risk.md` — drop locking/retry ceremony.
- `feedback_measurability_over_defensive_complexity.md` — invest in metadata on responses, not machinery.
- `project_eval_framework_deferred.md` — don't bolt in eval framework now.

## Green-light criteria for M1.7

- `python3 -m pytest kdb_compiler/tests/test_kdb_compile.py` — all tests pass.
- Full suite stays green: 193 + new M1.7 tests (target: ~14) = ~207.
- CLI smoke run end-to-end on `/tmp/m17_smoke/` produces valid wiki + state.
- `pyproject.toml` has the `kdb-compile` entry.
- User-approved commit on `main`.

## After M1.7 ships

- Update `docs/CODEBASE_OVERVIEW.md` roadmap to mark M1.7 done.
- Push `main` to `origin` (user call — still deferred pending green end-to-end).
- Hand back to Opus for **M2 Phase 1** — planner + compiler design + prompt engineering. That's where the real LLM work begins.
