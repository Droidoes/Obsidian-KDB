# benchmark/ — data directory for KDB cross-model benchmarking

This directory holds **data only**. The benchmark engine lives in the
`kdb_benchmark/` package at the repo root.

## Layout

| Path | Purpose | Tracked? |
|------|---------|----------|
| `sources/` | Curated markdown inputs fed to every model | yes |
| `truth/`   | Human-authored ground truth (Task #20) | yes |
| `runs/`    | Per-run outputs, one `run-NNN/` dir per invocation | **no** (gitignored) |
| `scores/`  | Scorecards (Task #22) — project artifact, historical record | yes |
| `inspect/` | Ad-hoc failure snapshots for manual triage | **no** (gitignored) |

## Why the split

Code (`kdb_benchmark/`) is pinned by commits. Data (`benchmark/`) grows
per-run. Keeping them separate keeps the engine installable as a Python
package and keeps the data dir easy to gitignore / rsync / archive.

## Related

- `kdb_benchmark/` — engine code
- `kdb_benchmark/models.json` — pinned model registry
- `docs/TASKS.md` — Task #5 parent + sub-tasks #16–#23
