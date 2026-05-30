# Task #89 Pass-1 — Provider Structured-Output Parity Findings

**Date:** 2026-05-26
**Purpose:** Per Task A.2 of `docs/superpowers/plans/2026-05-26-task89-pass1-ingestion-implementation.md`. Empirical verification of OQ-89-13 — which Pass-1 candidate providers reliably emit structured JSON for the Pass-1 envelope schema.
**Script:** `scripts/verify_structured_output_parity.py` (committed at `c2353e5` after fixes for C1 deepseek extra_body + C2 gpt-5.4-mini use_completion_tokens + C3 anthropic full dated model string).

## Method

5 candidate providers fired with a minimal Pass-1-shaped JSON envelope prompt:
- Schema: 8 fields (`kdb_signal`, `domain`, `source_type`, `author`, `summary`, `key_entities`, `key_themes`, `confidence`)
- temperature=0.0, max_tokens=1024
- Per-candidate knobs loaded inline (deepseek `extra_body={"thinking":{"type":"disabled"}}`; openai `use_completion_tokens=True`)
- `json_mode=True` requested (becomes `response_format={"type":"json_object"}` on OpenAI-compat paths; **silently ignored on the anthropic path** — pre-existing call_model.py limitation; see Findings below)

Joseph fired the script 2026-05-26 evening.

## Results

| Verdict | Provider | Model | Latency | Tokens (in/out) | Notes |
|---|---|---|---|---|---|
| ✅ PASS | deepseek | deepseek-v4-flash | 1505ms | 193/111 | Schema-compliant JSON; `extra_body={"thinking":{"type":"disabled"}}` correctly suppresses `<think>` tags |
| ✅ PASS | gemini | gemini-3.1-flash-lite | 1051ms | 187/137 | Fastest of the 5; schema-compliant |
| ❌ FAIL | anthropic | claude-haiku-4-5-20251001 | n/a | n/a | Non-JSON output (parse fails at line 1 char 0 — empty or prose-prefix). Root cause: `_call_anthropic()` in `call_model.py` does NOT read `req.json_mode`; the `response_format` enforcement is OpenAI-compat-only. Anthropic relies on prompt-level instruction; for this smoke's prompt that wasn't sufficient. |
| ✅ PASS | openai | gpt-5.4-mini | 3372ms | 171/145 | Confirms C2 fix (use_completion_tokens=True correctly routes max_tokens → max_completion_tokens) |
| ✅ PASS | xai | grok-4-1-fast-reasoning | 3754ms | 314/123 | Highest input-token count (likely added reasoning tokens) |

**4/5 PASS.** Anthropic excluded by call_model.py implementation gap, not by model capability.

## Latency + cost-quality picture

Sorted by latency (Pass-1 fires per-source; latency × source-count = wall-clock for full-vault enrichment):
1. gemini-3.1-flash-lite: 1051ms ⚡
2. deepseek-v4-flash: 1505ms
3. gpt-5.4-mini: 3372ms
4. grok-4-1-fast-reasoning: 3754ms
5. anthropic: blocked

Per the 2026-05-23 DeepSeek-direct experiment (project Milestone Changelog), `deepseek-v4-flash:direct` and `gemini-3.1-flash-lite` tied at FINAL=0.956 on the benchmark cost-quality frontier (deepseek wins on cost; gemini wins on latency). Today's parity smoke shows the same relative ordering.

## Pass-1 v1 candidate set lock

**Primary**: `deepseek-v4-flash:direct`
- Matches the existing compile-side default (`kdb_compiler/kdb_compile.py:51`)
- Cost-quality frontier winner per project benchmark
- Passes parity smoke (1505ms, schema-compliant)
- Aligns with the "tunnel ends meet" architecture (Pass-1 and Pass-2 default to the same provider)

**Backup**: `gemini-3.1-flash-lite`
- Fastest of the 5 candidates (1051ms; 1.4× faster than primary)
- Latency advantage matters if Pass-1 enriches large batches
- Independent provider — failover protection if DeepSeek API has issues

**Available but not configured by default**: `gpt-5.4-mini`, `grok-4-1-fast-reasoning` — both pass parity and could be added to `models.json` if needed. Higher latency = lower preference for default Pass-1 use.

**Blocked (deferred)**: `claude-haiku-4-5-20251001` — Anthropic provider blocked by call_model.py `json_mode` not being applied on the Anthropic path. Re-evaluate when:
- (a) `_call_anthropic()` learns to enforce JSON output (e.g., via response-prefilling pattern, or stronger prompt-level instruction with retry), OR
- (b) Anthropic adds native `response_format` support to their messages API

Filed as new follow-up: **OQ-Pass1-A1** — Anthropic JSON enforcement in `call_model.py`. Out of scope for current Task #89 v1; Pass-1 has 2 working candidates which is sufficient (per [[feedback_no_imaginary_risk]] — single-user, infrequent workload doesn't need 5-provider parity).

## Implications for downstream tasks

- **Task C.1** (`source_types.json` / `domains.json` / `scope-config.yaml` materialization): unblocked.
- **Task C.5** (`pass1_caller.py`): single-retry semantics from Task #89 §5.1 are sufficient given the primary candidate's stable parity.
- **Task C.11** (`kdb-enrich` CLI): defaults `--provider deepseek` and `--model deepseek-v4-flash` per the lock above.
- **Task E.1** (end-to-end acceptance test): `@pytest.mark.live` skip guards on `DEEPSEEK_API_KEY` env var (already specified in the plan).

## Cross-references

- Plan: `docs/superpowers/plans/2026-05-26-task89-pass1-ingestion-implementation.md` Phase A
- Memory: [[project_deepseek_v4_flash_dropped]] — the 2026-05-23 direct-route re-instatement; this finding extends that lineage
- Memory: [[feedback_flag_time_bounded_pricing]] — DeepSeek's "75% discount" pricing remains the post-cliff rate (per `1/4 of original` line in their pricing page); no Pass-1 cost surprise expected
- Earlier code review (Task A.1 commit `4882597`): I2 observation that `json_mode` is silently ignored on the anthropic path — this finding empirically confirms it
