# Session Handoff — 2026-05-30 — Task #95 Pass-1 contract fix + docs reorg

## DONE & COMMITTED
- **docs/ reorg** committed (`4201258` on `main`, NOT pushed): 180→33 top-level files;
  `reference/` (live arch+state docs), `archive/{handoffs,tasks,rounds,early}/`. 147 git
  renames + 163 ref-rewrites. Memory written: `project_docs_reorg_2026_05_30.md` + MEMORY.md.

## DONE, NOT YET COMMITTED — Task #95 atomic contract fix (two-stage validation)
All edits applied on disk. This is ONE atomic commit (prompt + code together — committing
prompt alone would break Pass-1, since old schema required 4 code-owned fields).

Files changed:
1. `kdb_compiler/ingestion/pass1_schema.py` — split into `build_content_schema()`+`validate_llm_content()`
   (Stage 1, 11 LLM-owned fields, NO override/model/prompt_version/schema_version) and
   `build_json_schema()`+`validate_envelope()` (Stage 2, full assembled envelope). Shared
   `_content_properties()` / `_validate_against()` helpers. `_CONTENT_REQUIRED` (11) +
   `_CODE_OWNED_REQUIRED` (4) lists.
2. `kdb_compiler/ingestion/overrides.py` — NEW `build_override_block(llm_original, *, applied, rule,
   match, reject_reason_cleared)` = SOLE producer of override block. `apply_overrides` now uses it.
3. `kdb_compiler/ingestion/pass1_caller.py` — reordered: parse → `validate_llm_content` (Stage 1,
   retry gate) → stamp prompt_version+model+schema_version → return (override built downstream).
   Import changed to `validate_llm_content, PASS1_SCHEMA_VERSION`. Caller NO LONGER builds override.
4. `kdb_compiler/ingestion/enrich.py` — import `build_override_block` + `validate_envelope,
   PASS1_SCHEMA_VERSION`. After `apply_overrides`, added `validate_envelope(envelope)` (Stage 2).
   `_empty_source_envelope` + `_write_sidecar_failed` now use `build_override_block(...)`.
5. `kdb_compiler/ingestion/pass1_prompt.py` — `PASS1_PROMPT_VERSION = "1.2.0"`. Arrow symbols
   (↑ ↔ ⇄) → "vs" + prose in `_DOMAIN_BOUNDARIES` + `_SOURCE_TYPE_BOUNDARIES` (DeepSeek #4).
   `human↔AI` → `human-to-AI`. (`pass1_prompt.j2` already rewritten in a prior session — the
   11-field content-only template, user reviewed & OK'd.)
6. Tests added/edited: `test_pass1_schema.py` (+7 Stage-1 tests), `test_pass1_overrides.py`
   (+3 build_override_block tests), NEW `test_pass1_caller.py` (3 tests, uses ModelResponse with
   fields: text,input_tokens,output_tokens,latency_ms,model,provider,attempts,stop_reason,raw),
   `test_pass1_enrich.py` (fixed PRE-EXISTING BUG: `_signal_parsed` had `source_type:"essay"` which
   is NOT a valid NW-7 id → changed to `"paper"`. Stage 2 correctly caught it — proof it works).

## VERIFIED
- New caller tests pass (direct repro: `OK schema_version=1 has_override=False`).
- The 2 enrich failures were the pre-existing "essay" fixture bug, now fixed.
- **PENDING: final full `pytest -m "not live"` confirmation** — was running when context ran out.
  RE-RUN: `cd /home/ftu/Droidoes/Obsidian-KDB && python3 -m pytest -q -m "not live" kdb_compiler/`
  (MUST use `-m "not live"` — .env auto-loads API keys, plain pytest fires live $ tests.)

## NEXT STEPS
1. Confirm full non-live suite green.
2. Commit #95 atomically (prompt .j2 + .py + schema + caller + overrides + enrich + tests).
   Suggested msg subject: `fix(task95): Pass-1 two-stage validation — drop 4 code-owned fields`
   Body: contract fix (LLM emits 11 content fields only; code stamps provenance + builds override),
   single-producer build_override_block, Stage-2 envelope validation gap-closer, arrow→prose
   boundaries (DeepSeek #4), prompt v1.1.0→1.2.0. Get Joseph's commit OK (commit gate).
3. Update `docs/TASKS.md` #95 entry + `docs/orchestrate-real-run-1-to-2-tasklist.md` task A/A.1.
4. Remaining real-run-1-to-2 tasklist: #96 error-handling architecture, #94 quarantine-and-continue,
   #97 viewer bake-off (D3.js), #98 Pass-1 benchmark (GATE; Joseph fires), #99 --limit N, #100 rename.

## GIT STATE
- `main` at `4201258` (reorg), unpushed. 8 prior task91 commits also unpushed. PUSH GATE held.
- Uncommitted: the 6 #95 source files + 4 test files + this handoff + untracked tools/,
  task95-pass1-review/, orchestrate-real-run-1-to-2-tasklist.md, superpowers/specs/.

## ENV NOTE
This session had a badly lagged Bash output channel (results delivered ~1 call behind, sometimes
many). Use write-to-file-then-Read pattern and don't trust first read of a just-written file.
