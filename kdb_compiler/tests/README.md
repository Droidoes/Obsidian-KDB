# kdb_compiler tests

Fixture-based tests for the deterministic layer (M1). Each test operates on a synthetic `KDB/` tree under `fixtures/` — no real vault access.

## Structure

- `fixtures/` — synthetic scan inputs, manifests, compile_result samples
- `test_kdb_scan.py` — scanner edge cases (symlinks, binaries, renames, empty vault, first-run)
- `test_manifest_update.py` — manifest transitions (NEW/CHANGED/MOVED/DELETED, orphan marking, run history)
- `test_validate_compile_result.py` — schema acceptance/rejection matrix
- `test_end_to_end_dry_run.py` — scan -> (mock compile_result) -> validate -> apply -> manifest update, no LLM call

Run with `pytest kdb_compiler/tests/`.
