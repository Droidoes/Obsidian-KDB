# Session handoff — 2026-07-21

> Richest single catch-up artifact for the next session. Resume from this file alone.

## ⏩ END OF SESSION — WS1 cohort refresh: pool pruned (anthropic, qwen3.6-us, gemini-3.5), 5 current-gen fires (2 clean), gemini-3.5 retired on two-level failure; WS1 firing phase CLOSED — next = board reset → cohort decision (A/B/C)

A benchmark-operations session (Kimi Code), executing WS1 from the 2026-07-20 stack. **No production-pipeline code changed** — all changes are model-registry config + tests + perimeter docs. Full non-live suite green throughout (1295 passed at close). **UNCOMMITTED — commit gate open** (all 4 runs carry the `v0.5.7-2-g718e75d-dirty` tag for this reason; recommend committing before the next fire for clean provenance).

### Shipped (tonight's diff, uncommitted)
- **Anthropic retirement** — `haiku-4.5` + `sonnet-4.6` out of `common/models.json` → `models_dropped.json` (Joseph: no API calls, no benchmark references; other providers caught up). Synced: `AGENTS.md` (no key is code-required; `DEEPSEEK_API_KEY` is the standing default), `.env.example`, `setup.sh`, `scripts/verify_structured_output_parity.py` (candidate matrix), `docs/reference/benchmark-cohort-procedure.md` (provider table + fixed stale grok example). Engine support (`call_model.py` anthropic path + SDK dep) deliberately retained.
- **qwen3.6-flash-us** — added from verified Alibaba docs ($0.25/$1.50 ≤256K tier, US-deployed, thinking+non-thinking), fired, **retired same night** on its run's evidence (see Fires). Full evidence trail in its `dropped_reason`.
- **gemini-3.5-flash** — added (GA 2026-05-19; $1.50/$9.00; 1M/65,536; `temperature: null` since 3.5 dropped legacy sampling params), tried at handler-default `thinking_level:"minimal"` then pool-overridden `"low"`, **retired same night** on two-run evidence (see Fires). Un-retire trigger: #111 Phase-2 `response_json_schema`.
- Tests pinned for every roster move (`common/tests/test_model_pool.py`); `docs/reference/model-provider-api-calls.md` updated for all three moves.

### The four fires (all `kdb-orchestrate --pipeline vault-test --emit-kpis` on the 36-source sandbox, current code)
| run (EDT) | exit | quarantines | cost | board score |
|---|---|---|---|---|
| gpt-5.4-mini 23:52 | ok | 0 | $0.848 | **78.57** (current-gen #1) |
| deepseek-v4-flash 00:20 | ok | 0 | $0.118 | **54.57** (#2) |
| qwen3.6-flash-us 00:51 | completed_with_quarantines | 3 | $0.251 | 6.00 → retired |
| gemini-3.5-flash 01:09 (minimal) | completed_with_quarantines | 10 | $2.39 | 8.00 |
| gemini-3.5-flash 01:46 (low) | completed_with_quarantines | 13 | $2.38 | 10.00 → retired |

- **Current-gen head-to-head (the only honest rows):** gpt-5.4-mini leads deepseek on *every* graph KPI + latency (graph_score 0.857 vs 0.65 raw: connectivity 0.192/0.181, link_density 1.78/1.50, reuse 0.0293/0.0208, resolution 0.406/0.282). deepseek stays 7.2× cheaper (matches the historical ratio exactly). Both deepseek graph KPIs *improved* vs its Jun-7 self.
- **qwen3.6-us quarantines:** 2 structured-contract failures at compile (`summary_slug` absent from `pages[].slug`; `pages[3].status:'high'` — confidence value in the status enum) + 1 **DashScope content-filter 400** (`data_inspection_failed`) at Pass-1 on the Li Lu lecture — provider moderation false positive; gpt/deepseek compiled the same source cleanly. **Provider-level vault-scale risk → WS3 note.**
- **gemini-3.5 flop anatomy:** 21/29 Pass-2 calls failed attempt 1 (72%); signature `JSONDecodeError: Extra data` = valid JSON object + trailing content (clean STOP, no truncation). #104 retry rescued 11; 10 quarantined. Pass-1 100% clean. Even passes were reuse-dead (`entity_reuse` 0, resolution 0.106). Cost retry-inflated (40 Pass-2 calls). The `"low"` re-fire (01:46) settled the hypothesis: identical `Extra data` signature (11/12 pass2 failures), 13 quarantined, retry_load 0.446, `entity_reuse` still 0 — **thinking level is NOT the lever**; the model appends trailing content after the JSON object on Pass-2 regardless. Third confirmation of the gemini + `json_object` Pass-2 weakness class (3.1-flash-lite Jun-7: pass-2-heavy quarantines) → **retired**. Structural fix + un-retire trigger: #111 Phase-2 `response_json_schema`.

### Discoveries (telemetry/doc gaps — WS3 candidates)
- Pass-1 sidecars nest tokens under `raw_response.total_*` (top-level zeroed); per-call `cost_usd` is correct at top level. **The §3C aggregate cost diagnostic ($/1k source-words) is NOT emitted in `measurements.json`/`report.md`** — designed but unimplemented; tonight's costs were summed from per-call records.
- Quarantined Pass-2 records lack `compile_attempts` (clean/retried records have it).
- Leaderboard keys on `(provider, model, release_version)`: same-key re-score **replaces** the row → the "low" re-fire cleanly replaces the flop row.
- Why cost isn't scored: **purpose lock 2026-06-05** (`docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:17`) — selection settled on cost (deepseek wins regardless), board measures quality only; latency is the scored operational axis.
- Run-cost mechanics: per-call `cost_usd` includes discarded retry attempts (recorded totals > persisted-token pricing on retried runs).
- `force_noise` does NOT skip Pass-1: every scanned source is Pass-1 enriched (gpt/deepseek runs: 36/36 enriched); force_noise only saves the Pass-2 call. A force_noise source whose Pass-1 fails quarantines instead of going noise (gemini-low run: `Daily Notes/2026-05-28.md`, Pass1EnrichError after 2 attempts). Big-run cost model consequence: main-vault `force_noise: [Daily Notes/**, Projects/**]` still costs a Pass-1 call per source — WS2/WS3 note.

### Next (in order)
1. ~~Fire gemini-3.5-flash @ `thinking_level:"low"`~~ — DONE same night: flopped identically (13 quarantined, same `Extra data` signature, `entity_reuse` 0) → **model retired** (evidence in `models_dropped.json`). **WS1 firing phase CLOSED.**
2. Optional: re-fire qwen3.5-flash (~$0.03–0.05, cheapest) for a 4-row current-gen board.
3. **Reset + re-score current-gen rows only:** `rm benchmark/scores/leaderboard.{json,md}` then `kdb-benchmark score <current-gen run dirs>` — clean single-generation board (stale rows' dirs stay as audit).
4. **Cohort additions decision still OPEN** (the A/B/C question from the 7-20 handoff, never answered).
5. WS2 (OneNote preflight) after WS1 closes.

### Housekeeping
- GWS auth is down (token invalid, 0 scopes) — Google Tasks unread this session; re-auth from terminal when convenient.
- Sandbox state/runs currently holds only the last (gemini 01:09) run — earlier runs' state was wiped between fires by design; their KPI data persists in `benchmark/runs/<model>-<run_id>/run_state/`.

### Pointers
- Run dirs: `benchmark/runs/{gpt-5.4-mini-2026-07-20T23-52-49, deepseek-v4-flash-2026-07-21T00-20-32, qwen3.6-flash-us-2026-07-21T00-51-24, gemini-3.5-flash-2026-07-21T01-09-32}_EDT`
- Board: `benchmark/scores/leaderboard.md` (8 rows, mixed-generation — do not trust cross-generation comparisons)
- qwen3.6-us retirement evidence: `common/models_dropped.json` (tail entry)
- Provider levers: `docs/reference/model-provider-api-calls.md` (gemini `"low"` override + alibaba `-us` note)
- Prior handoff: `docs/session-handoff-2026-07-20.md` (WS stack + locked vault-ingest decisions)
