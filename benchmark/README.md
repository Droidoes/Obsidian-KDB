# benchmark/ — data directory for KDB cross-model benchmarking

This directory holds **data only**. The benchmark engine lives in the
`tools/benchmark/` package (CLI: `kdb-benchmark`); the former top-level
`kdb_benchmark/` package was dissolved in the 2026-06 codebase realignment
(#105/#109).

## Layout

| Path | Purpose | Tracked? |
|------|---------|----------|
| `sources/` | Curated markdown inputs fed to every model | yes |
| `truth/`   | Human-authored ground truth (Task #20) | yes |
| `runs/`    | Per-run outputs, one `run-NNN/` dir per invocation | **no** (gitignored) |
| `scores/`  | Scorecards (Task #22) — project artifact, historical record | yes |
| `inspect/` | Ad-hoc failure snapshots for manual triage | **no** (gitignored) |

## Why the split

Code (`tools/benchmark/`) is pinned by commits. Data (`benchmark/`) grows
per-run. Keeping them separate keeps the engine installable as a Python
package and keeps the data dir easy to gitignore / rsync / archive.

## Related

- `tools/benchmark/` — engine code
- `common/models.json` — pinned model registry
- `docs/TASKS.md` — Task #5 parent + sub-tasks #16–#23
