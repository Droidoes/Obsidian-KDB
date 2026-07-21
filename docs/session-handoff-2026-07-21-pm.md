# Session handoff — 2026-07-21 (PM)

> Richest single catch-up artifact for the next session. Resume from this file alone.

## ⏩ STATE — #114 SHIPPED on `feat/114-recovery-parse-stage` (11 commits, final review READY TO MERGE, suite 1379 green) — **MERGE GATE IS THE ONLY OPEN ITEM**; then #115 (prompt/schema contract audit) → WS2 OneNote preflight → WS3

A benchmark-ops + task-execution session (Kimi Code). Two arcs: (1) WS1 fully closed — board reset, GLM-5-Turbo wired/fired/retired, grok-4.20 retired on xAI deprecation, WS1 diff committed to main; (2) Task #114 (recovery-oriented Pass-2 parse stage) taken from a repair-ladder question through Joseph's first-principle reframe → spec v0.3.6 (8 Codex rounds) → plan v1.5 → subagent-driven execution → final review READY TO MERGE. Everything is committed except the merge itself.

---

### WS1 closure (committed to main, 3 commits)

- **Board reset** to current-gen rows only (`benchmark/scores/leaderboard.{json,md}` deleted + re-scored from run dirs; backups at `/tmp/leaderboard.*.pre-reset-2026-07-21`). Board is now single-generation (`@v0.5.7-2-g718e75d-dirty` on all rows).
- **GLM-5-Turbo (zai provider)**: wired (`zai` dispatch → `https://api.z.ai/api/paas/v4`, `ZAI_API_KEY` in Settings, verified thinking-disable `{"thinking": {"type": "disabled"}}`), fired (`glm-5-turbo-2026-07-21T10-45-04_EDT` — 5/36 quarantined, $1.22, slowest, board **26.00 rank 4/5**), **retired same day**. Failure anatomy: 4× systematic `page_type` omission on non-summary pages (feeds #115) + 1× z.ai content-filter 400.
- **grok-4.20-0309-non-reasoning retired** — xAI deprecated the model (successor: `grok-4.3`, the natural future xai candidate: $1.25/$2.50, 1M ctx, verified strict json_schema).
- **Cohort decision A/B/C: ANSWERED — no more model additions** ("done with trying new models"). Survivors: gpt-5.4-mini **85.75** / deepseek-v4-flash **65.25** (5-row board incl. 3 retired-evidence rows).
- Pool state: 6 active models; 12 archived in `models_dropped.json` with evidence trails; anthropic/zai/xai wired-but-model-less.
- Commits: `ac50449` (zai provider) · `83895fc` (pool curation, 5 retirements) · `3b4e300` (handoffs 7-20/7-21).

### Cost telemetry validated against both provider dashboards

- **Token telemetry is exact**: OpenAI dashboard matched our 707,134 input + 70,634 output **to the digit**. DeepSeek residual consistent (784K of 892K; rest was deepcode).
- **`cost_usd` is a list-price UPPER BOUND**: real spend runs ~20–35% lower (gpt run: recorded $0.8482 vs actual $0.69; deepseek: $0.1183 vs ~$0.08) due to automatic prompt/context caching on the shared Pass-2 prefix (~33% of input cached at ~0.1× rate). Gap: we don't read `usage.prompt_tokens_details.cached_tokens` — noted for WS3 cost modeling, not a fix-now.
- **Model comparison is whole-run** (one model does both passes; no per-pass split exists in the CLI). Per-pass diagnostics (`quarantine_rate_pass1/pass2`, `latency_pass1/pass2`) are how failure classes get localized. A cheap-Pass-1/quality-Pass-2 hybrid is a possible WS3 candidate (Pass-1 ≈ 6–9% of run cost).

### Provider content-filter pattern (vault-scale risk for WS3)

The **Li Lu lecture trips BOTH Chinese providers' mandatory compliance layers** — DashScope Green Net (`data_inspection_failed`) AND z.ai (400 code 1301) — while OpenAI/DeepSeek process it cleanly. No disable switch exists (official remedy: modify input / submit ticket). On a 1,586-note vault, provider choice determines whether sources are simply unprocessable, unpredictably.

---

### Task #114 — recovery-oriented Pass-2 parse stage (SHIPPED, pending merge)

**The principle (Joseph's reframe):** the LLM response is a *carrier*, the JSON document is the *payload*. The parse stage recovers the payload with maximum tolerance for carrier noise; it may only **select** (locate the complete document), never **edit** decoded content; failure only on (a) no complete document, or (b) content failing the schema/semantic gates. A format deviation alone never fails a source. Origin: the #104 coerce-don't-reject principle had been implemented as whack-a-mole per-class exceptions; the 20 gemini-3.5 carrier-noise failures (19 recoverable + 1 genuinely incomplete) proved the posture wrong.

**Spec** v0.3.6 (`docs/superpowers/specs/2026-07-21-recovery-oriented-parse-stage-design.md`) — 3 Codex design rounds + 5 plan rounds, all findings verified + accepted, final verdict GO. Key contracts: shared `recover_json_response` (unwrap + strict-eval + 5-step selection-first ladder, used by `compile_one` AND `tools/replay.py`); root-preserving boundary-decode (never carves a nested object out of a failed array root; literal classification both-directional — `nul` attempted-root, `nulljunk` root+tail, `note:` prose); `recovered: bool` sentinel (JSON null ≠ failure); any-value recovery (schema judges content); coercion dict-guarded; recovery-before-truncation (ratified behavior change); `boundary_recovered` + prefix/tail counts threaded into `recovery_rate`/`repair_rung_rate`; `extract_ok` non-gating; `failure_stage="extract"` retired.

**Execution** (subagent-driven, 9 tasks, each spec+quality reviewed): commits `253af03` docs → `d205189` util → `b82fe41` unwrap → `88ec454` recovery → `0b643cb` telemetry → `76d6cd7` fixtures (20 curated, `compiler/tests/fixtures/pass2_recovery/`) → `055f515` compile_one → `20bd8f7` KPI → `81e5690` replay → `334baad` closure → `de11e2f` final-review minors. Final whole-branch review: **READY TO MERGE, 0 Critical/Important**. Suite **1379 passed** green. Progress ledger: `.superpowers/sdd/progress.md` (git-ignored).

**MERGE**: `feat/114-recovery-parse-stage` → `main`, fast-forward expected (base `3b4e300`). **This is the only open gate.**

---

### Next (in order)

1. **Merge the branch** (Joseph's gate) + delete branch.
2. **#115 — Pass-2 prompt/schema contract audit** (ledger row filed): (1) version-stamp the Pass-2 prompt FIRST (`pass2_prompt_version` is empty in telemetry — edits currently invisible; stamp + file-SHA anchor, THEN edit); (2) `status` → Python-stamped (#95 precedent — the prompt says "always active", models parrot-and-fumble it: qwen `status:'high'`); also investigate the glm `page_type`-omission class as possible prompt ambiguity; (3) slug-space/source-id-space jargon removal (Joseph-directed 7-20). Validation: cohort fire (Joseph) — KPIs shouldn't move.
3. **WS2 — OneNote preflight**: `kdb-enrich` ~100 of 1,258 OneNote files, analyze distributions, tune vocab only if the sample says so.
4. **WS3 — vault-in-place rollout design** (the big one): #94 fix + D39 sidecar restoration (one work item), main-vault pipelines.json, graph default flip, chunked-run sizing, prompt-capture minimalism + context_snapshots.jsonl, llm_resp→pass2 unification, `~/Obsidian/KDB` reset precondition, cached_tokens cost-capture, Chinese-provider content-filter policy.
5. WS4 MCP revisit / WS5 graph extraction (parked behind WS3).

### Housekeeping

- **Subagent usage limit hit** during final-review fixes (403 mid-dispatch) — the fixer had completed its edits uncommitted; I verified + tested + committed inline. For the rest of this billing cycle, prefer inline work over subagent dispatches.
- `kdb-orchestrate` on PATH is broken (system python lacks deps) — **always use `.venv/bin/`** binaries.
- `pytest -q` stacks with pyproject `addopts -q` → `-qq` suppresses the summary line; run bare `pytest` when you need the count.
- GWS auth healthy (12 scopes).
- Board backups at `/tmp/leaderboard.{json,md}.pre-reset-2026-07-21` (tmp — ephemeral).

### Pointers

- Spec: `docs/superpowers/specs/2026-07-21-recovery-oriented-parse-stage-design.md` (v0.3.6, change log §7)
- Plan: `docs/superpowers/plans/2026-07-21-task114-recovery-oriented-parse-stage.md` (v1.5)
- Board: `benchmark/scores/leaderboard.md` (5 rows, current-gen)
- GLM evidence: `common/models_dropped.json` (tail 2 entries: glm-5-turbo, grok-4.20)
- Prior handoffs: `docs/session-handoff-2026-07-21.md` (overnight WS1 firing), `docs/session-handoff-2026-07-20.md` (WS stack + locked decisions)
