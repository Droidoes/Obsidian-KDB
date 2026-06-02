# Test Fixtures

Synthetic JSON files for fixture-based tests. None of these touch the real vault.

## Files

### `manifest.empty.json`
A freshly-initialized manifest with no sources, no pages, no runs. Used as the starting point for most `manifest_update.py` tests.

### `compile_result.minimal.valid.json`
Smallest possible compile result that passes schema validation. Two pages (one summary, one concept) derived from one source. Used for:
- `test_validate_compile_result.py` — positive path
- `test_end_to_end_dry_run.py` — scan → (fixture) → validate → apply → manifest update

### `compile_result.minimal.invalid.json`
Deliberately broken in three ways to exercise the schema gate:
1. `summary_slug` uses uppercase and underscore (violates slug pattern)
2. First page includes `compiled_at` and `page_id` (LLM must NOT emit runtime metadata / paths — D8)
3. Second page uses `page_type: "index"` (LLM cannot emit index pages — D19)
4. Second page has an empty `title` (schema requires minLength=1)
5. Second page's slug contains spaces (violates slug pattern)

Every one of these should be caught by `validate_compile_result.py`. When
M1 lands the validator, this fixture should produce at least 5 schema errors.

## Conventions

- Fixtures are committed — never generated at test time.
- Name pattern: `<artifact>.<variant>.json` (e.g., `compile_result.minimal.valid.json`).
- Valid fixtures are canonical examples we cite in docs.
- Invalid fixtures exist only to exercise negative paths.
