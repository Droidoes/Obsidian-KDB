# Session Handoff — 2026-04-19 → next session (Opus 4.7)

**Branch**: `main`  **Last commit**: `4e2eb87` M1.7 kdb_compile orchestrator
**Tests**: 207/207 passing (1.4s; 3 env-blocked modules excluded)
**Ahead of `origin/main`**: 12 commits (push deferred — user's call after M2 first compile)
**Next milestone**: M2 — planner + compiler + prompt design + first real compile

## Who's driving and why

Sonnet 4.6 drove M1.7 (wiring work — deterministic, binary criteria, no design ambiguity).
**Opus returns for M2**: prompt engineering, context shaping, LLM output quality judgements, and the architectural decisions around chunking, context snapshots, and response normalization. That's where stronger reasoning earns its cost.

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
M1.7      ✅ kdb_compile orchestrator (scan → validate → apply → write)
M2        ⬜ planner + compiler + prompt_builder + first real compile  ← YOU ARE HERE
```

## M1 pipeline — what's proven end-to-end

The dry-run smoke test (run this to verify any time):

```bash
cd ~/Droidoes/Obsidian-KDB
python3 -m pytest kdb_compiler/tests \
  --ignore=kdb_compiler/tests/test_call_model.py \
  --ignore=kdb_compiler/tests/test_call_model_retry.py \
  --ignore=kdb_compiler/tests/test_config.py
```

End-to-end flow (M1.7 wired it together):
1. `kdb_scan.scan()` → `ScanResult` (with `write=False` for dry-run)
2. `validate_last_scan.validate(scan_dict)` — abort on error
3. Load `state/compile_result.json` — fail clearly if missing (no partial writes)
4. `validate_compile_result.validate(cr)` — abort on error
5. Assert `scan.run_id == cr.run_id`
6. `manifest_update.build_manifest_update(prior, scan_dict, cr, ctx)` → `(next_manifest, journal)` — pure
7. `patch_applier.apply(state_root, vault_root, next_manifest=..., run_ctx=..., write=not dry_run)`
8. `manifest_update.write_outputs(next_manifest, journal, state_root, ctx)` — skip if dry_run

**Critical**: `patch_applier.apply()` reads `compile_result.json` from disk itself (line 369). The file must be present when it's called (already validated in step 3).

## M2 — what needs to be built

### Stubs already in place (read before implementing)

```
kdb_compiler/
  planner.py            # M0 stub — reads last_scan.json, chunks to_compile
  compiler.py           # M0 stub — per-source LLM call, accumulates compile_result.json
  prompt_builder.py     # reserved split-point (D21) — prompt authorship
  context_loader.py     # reserved split-point (D21) — manifest snapshot for LLM
  response_normalizer.py # reserved split-point (D21) — parse LLM JSON response
```

Read all five stubs before designing — they contain the intended responsibility boundaries and open design questions.

### M2 responsibilities

**`planner.py`** — reads `state/last_scan.json`, chunks `to_compile` list into batches (10–20 sources/batch per D9). Returns a `CompilePlan` — ordered list of `CompileJob` items each with source_ids + context. No LLM calls.

**`compiler.py`** — orchestrates per-source compile: for each job, calls `context_loader` (manifest snapshot) + `prompt_builder` (full prompt), fires `call_model_with_retry`, passes response to `response_normalizer`, accumulates into `compile_result.json`. Writes the file atomically when complete.

**`prompt_builder.py`** — builds the full prompt string given source content + context snapshot. This is the core of M2's quality work. Must encode the LLM contract invariants (D8: no paths/timestamps, D18: full-body replacement, slug-only links).

**`context_loader.py`** — builds the manifest snapshot the LLM sees: existing page slugs, existing concept graph, prior summaries for this source (if re-compiling). The shape of this snapshot directly determines link quality and deduplication.

**`response_normalizer.py`** — parses LLM response text → validated `CompileResult` dict. Must handle: JSON-in-markdown fence, partial responses, invalid slugs. Should call `validate_compile_result.validate()` as final check.

### How M2 slots into kdb_compile.py

M1.7's orchestrator in `kdb_compile.compile()` already has the slot:

```python
# Step 5 (current): Load compile_result.json from disk (fixture)
# M2 replaces this with:
#   plan = planner.plan(scan_result, state_root)
#   cr = compiler.compile(plan, vault_root, ctx)
#   write compile_result.json
# Steps 6–11 unchanged
```

The orchestrator contract does not change. M2 fills the gap between scan and apply.

### Key design questions for M2 Phase 1 (strategize before coding)

1. **Chunk size**: D9 says 10–20 sources/batch. Single-source batches are simplest for M2 v1 — iterate from there. Confirm before implementing.

2. **Context snapshot shape**: What does the LLM see about existing pages? Options: (a) full list of existing slugs only, (b) full page titles + slugs, (c) truncated body snippets for related pages. Shape determines link quality and token cost.

3. **Prompt structure**: System prompt (invariants) vs user prompt (source content + context). Where does `KDB/KDB-Compiler-System-Prompt.md` live in the prompt? Is it system or user?

4. **Re-compile policy**: If a source hasn't changed (UNCHANGED action in scan), should M2 skip it? Probably yes for v1. But what about concept propagation (a concept page touched by an unchanged source)?

5. **run_id threading**: The compiler must stamp `compile_result.json` with the same `run_id` as the scan. Pass `run_ctx.run_id` through the whole call chain — never generate a new one.

6. **Error tolerance**: Should a single LLM failure abort the whole compile, or continue with other sources and report partial results? `success: false` in compile_result handles it; the orchestrator already degrades gracefully.

## `call_model` seam — already available

`kdb_compiler/call_model.py` + `call_model_retry.py` are implemented (M1.3). The retry wrapper:

```python
from kdb_compiler.call_model_retry import call_model_with_retry

result = call_model_with_retry(
    model="claude-opus-4-7",
    system=system_prompt,
    messages=[{"role": "user", "content": user_prompt}],
    max_tokens=4096,
)
# result is the raw Anthropic API response object
```

Config lives in `kdb_compiler/config.py` — reads `~/.config/kdb/config.toml` or env vars. Three env-blocked test modules (`test_call_model.py`, `test_call_model_retry.py`, `test_config.py`) are excluded from CI; they need a live API key.

## KDB/KDB-Compiler-System-Prompt.md — the LLM's invariants

Read `~/Obsidian/KDB/KDB-Compiler-System-Prompt.md` before writing any prompt. It encodes:
- D8: LLM never emits paths, timestamps, versions
- D18: full-body replacement (no patch ops)
- Slug format policy
- Link format: `[[slug]]` only, no paths, no `.md` suffix

## Working conventions (inherited — do not change)

- **Test command**: `python3 -m pytest kdb_compiler/tests --ignore=kdb_compiler/tests/test_call_model.py --ignore=kdb_compiler/tests/test_call_model_retry.py --ignore=kdb_compiler/tests/test_config.py`
- **Python binary**: `python3` (no `python` alias on this WSL env)
- **Commit gate**: wait for explicit user approval before committing (global CLAUDE.md Phase 5 in `~/.claude/CLAUDE.md`)
- **D14/D22**: atomic writes only; no locks, no retry ladders
- **D15**: journal written BEFORE manifest in `write_outputs` — never reorder
- **D22**: single user, single process — no complexity for imaginary risk

## Auto-memory to consult

- `feedback_no_imaginary_risk.md` — drop locking/retry ceremony
- `feedback_measurability_over_defensive_complexity.md` — invest in latency/tokens metadata, not machinery
- `project_eval_framework_deferred.md` — don't build eval framework now

## Open items (pre-M2)

- [ ] Resolve Open-1..Open-8 in `docs/CODEBASE_OVERVIEW.md` (carry-forward from M1 — do during M2 Phase 1 strategize)
- [ ] Push `main` to `origin` once M2 first compile is green (user's call, 12 commits banked)
- [ ] Update `CODEBASE_OVERVIEW.md` roadmap to mark M1.7 ✅ (quick, do at M2 session start)

## Green-light criteria for M2

- `python3 -m pytest kdb_compiler/tests/test_compiler.py` (new) — all pass
- Full suite stays green: 207 + new M2 tests
- First real compile: seed `KDB/raw/` with 3–5 docs from `~/Droidoes/*/docs/`, run `kdb-compile`, inspect `wiki/` output for quality
- `compile_result.json` has correct `run_id` matching the preceding scan
- User approves commit
