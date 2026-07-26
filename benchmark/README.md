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
| `truth/task123_search_snapshot_v1/` | #123 SearchSnapshot fixture — frozen 2026-07-25 gemini cold-run end state (163 identities + excerpts + checksums); rebuild via `scripts/build_task123_snapshot_fixture.py`, verified by `tools/benchmark/tests/test_task123_search_snapshot_fixture.py` | yes |
| `truth/task123_search_probes_draft_v1.json` | #123 truth-set probes draft-v1 (39 probes, classes A–H) — Kimi-drafted labels pending Joseph's adjudication (becomes `task123_search_probes_v1.json` at adjudication_version 1); companion `task123_search_adversarial_v1.json` = P10 injection fixtures | yes |
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
