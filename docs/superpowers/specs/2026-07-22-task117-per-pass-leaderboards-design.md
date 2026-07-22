# Task #117 — Per-Pass Leaderboards (Pass-1 / Pass-2 split boards) — Design v0.3.1

**Status:** RATIFIED v0.3.1 (Joseph, 2026-07-22; Codex R1 + R2 + R3 folded)
**Filed:** 2026-07-22
**Parent context:** WS1 cohort analysis; #109 leaderboard machinery; #115 baseline sequencing

---

## Review log

- **v0.1 → v0.2 (Codex R1, "revise before ratification"):** all 7 findings
  code-verified and folded (cost selection column, downstream-outcome Pass-2 board,
  fail-closed fallback, board-honest weights/prose, competition ranking,
  recombination math, write boundary; North Star gate).
- **v0.2 → v0.3 (Codex R2, "revise before ratification", 4 High / 1 Medium / 1 Low):**
  all findings verified and accepted (eligibility/coverage metrics replace
  tautological `p2_attempted/signal`, cost-zero ≠ free, partial-`run_state/`
  completeness contract + unranked JSON, main-board contract (b), honest per-file
  atomicity, full-precision weights).
- **v0.3 → v0.3.1 (Codex R3, "revise before ratification", 1 High / 3 Medium /
  1 Low):** all findings verified against code/cohort data and accepted:
  - R3-F1 (**blocker**) Pass-1 count reconciliation — verified: `p1_attempted += 1`
    fires at loop entry (`kdb_orchestrate.py:610`), before `enrich_one`
    (`:620`), so a crash/partial-copy leaves `p1_attempted` > sidecar count and
    the v0.3 "all existing sidecars load" check stays green. → D-117-5 explicit
    three-line invariant.
  - R3-F2 eligibility conflates noise with failure — verified from headers: Qwen
    36 = 28 signal + 7 noise + **1 failed**; Gemini 36 = 29 + 6 + **1 failed**;
    DeepSeek 36 = 29 + 7 + 0. So Qwen's gap vs DeepSeek/GPT/GLM is a failure,
    but vs Gemini it is one extra noise classification. → D-117-4 disposition
    columns, corrected evidence text.
  - R3-F3 ranked-row raw-value location undefined → D-117-5/`§3`: one `raw_values`
    contract on ranked and unranked rows alike.
  - R3-F4 ledger entry out of sync with v0.3 → `docs/TASKS.md` #117 row corrected
    alongside this spec.
  - R3-F5 `updated_at` second-precision not a strict generation id → D-117-10
    wording weakened to the single-user execution model; mid-commit test added.

## 1. Motivation

Model performance is pass-specific: each pass has its own prompt, its own contract, and
its own failure modes. The current leaderboard ranks a model on the *combined* run
(processing KPIs normalize over pass1+pass2 tokens together), which blurs exactly the
signal Joseph wants when deciding e.g. whether a cost-effective model (deepseek-v4-flash)
suffices for Pass-1 while a quality model (gpt-5.4-mini) is needed for Pass-2.

Observation driving the timing: most models clear Pass-1 with flying colors — but that
is an *impression*; a Pass-1 board makes it measured. Split-model runs (cheap Pass-1 +
quality Pass-2) are explicitly **out of scope** here — that is Task #118. Until #118,
every run is single-model; the split boards merely re-slice data the runs already record.

## 2. Decisions

- **D-117-1 — Two new boards; main board's scoring contract untouched.**
  `kdb-benchmark score` writes `leaderboard-pass1.json/md` and
  `leaderboard-pass2.json/md` alongside the existing `leaderboard.json/md`. For the
  main board: **scored KPI set, ranking, composite, and scored columns are unchanged**,
  and output on legacy-shaped measurements stays byte-identical. Its raw-values table
  is intentionally data-driven (new diagnostic keys have always flowed through), so
  once future runs emit the #117 diagnostics those keys may appear there as additional
  raw columns — this is the existing passthrough contract, not a scoring change.
- **D-117-2 — Rebuild from existing run data; no re-runs, no pipeline change.** Every
  leaderboard row's run dir carries `run_state/` (pass1 sidecars + pass2 resp-stats +
  `measurement_header.json`). Per-pass processing KPIs are **recomputed at score time**
  via `common.measurement.load_run_measurements(run_state)` +
  `compiler.kpi.processing.compute_processing`. Graph KPIs cannot be recomputed at score
  time (they reflect emit-time graph state) — they are read from the row's
  `measurements.json` as today. All 5 current rows (2026-07-21 cohort) carry
  `run_state/` complete.
- **D-117-3 — `compute_processing` gains per-pass splits + cost (pure, additive).**
  `PassCallMeasurement` gains optional `cost_usd` (Pass-1: sidecar top-level
  `cost_usd`; Pass-2: record `cost_usd`; **absent → None, never silently 0.0**).
  New diagnostic keys: `recovery_rate_pass1/pass2` (same survivor-retry/repair
  predicate as the combined `recovery_rate`, partitioned by pass),
  `retry_load_pass1/pass2`, `cost_usd_pass1/pass2` (sum over that pass's *priced*
  calls), `cost_unknown_calls_pass1/pass2` (count of that pass's calls with
  token usage > 0 but no positive cost attribution — unpriced or failed-before-
  attribution, cf. the #110 deferred item "Pass-1 failed-source `cost_usd=0.0`").
  Future emits carry them in `measurements.json`; score-time recompute uses the same
  function for old runs. No existing key changes.
- **D-117-4 — Both pass boards reuse the §6 `score_models` machinery, zero new scoring
  code; the Pass-2 board is labeled a downstream-outcome board.** Pass KPI values are
  mapped onto the canonical processing names (`quarantine_rate` / `recovery_rate` /
  `latency`):
  - **Pass-1 board:** scored = the three Pass-1 KPIs only (no graph term). The §6
    hierarchical composite pro-rates TOP_WEIGHTS to 4:1:1 (quarantine 2/3 / recovery
    1/6 / latency 1/6 effective) and applies the standard weak-spot penalty over the
    three axes. Expect many ties at the top (flying-colors hypothesis) — the Borda
    all-equal rule renders those as 0.5 "no signal", which is the honest answer.
  - **Pass-2 board (downstream outcome):** scored = the three Pass-2 KPIs + the four
    graph KPIs. Graph structure is **downstream of both passes** — Pass-1's noise
    gate *and* its failures decide which sources reach Pass-2, and its enrichment
    shapes Pass-2's context. Cohort evidence: Qwen compiled 28 sources vs 29 for
    DeepSeek/GPT/GLM — the gap there is one **failed** Pass-1 call (Li Lu,
    `enrich_failed`); vs Gemini the gap is one extra **noise** classification
    (Qwen 7 noise + 1 failure; Gemini 6 noise + 1 failure). So this board answers
    "which model's *run* produced the best compiled+graph outcome", not "which model
    is best at Pass-2 in isolation". Isolated per-pass causal attribution stays
    unavailable until #118 supplies controlled split-model runs; the board says so in
    its header note. Composite shape identical to the main board (40/40/10/10 +
    penalty).
  - **Coverage + disposition columns** (replacing the tautological
    `p2_attempted/signal`, which is 100% by construction since
    `p2_attempted = signal`):
    `pass2_eligibility_rate = signal / p1_attempted`,
    `pass2_measurement_coverage = loaded_pass2_records / p2_attempted` (both **None
    when their denominator is 0**), plus the raw Pass-1 disposition counts that keep
    the two gap mechanisms distinguishable: `p1_noise` and
    `p1_failed = p1_attempted − signal − noise`.
- **D-117-5 — Fail closed on incomplete rows: explicit per-board completeness
  contract + unranked JSON shape.** A row is **ranked on a pass board only if all**
  of the following hold for that pass: (a) `run_state/` and the pass directory
  exist; (b) `measurement_header.json` parses; (c) **Pass-1 count reconciliation** —
  `identified_pass1_sidecars == p1_attempted`,
  `loaded_pass1_measurements == p1_attempted − enrich_skipped_sidecars`, and
  `unique source_id count == identified_pass1_sidecars` (catches the missing-sidecar
  case: `p1_attempted` increments at loop entry, before `enrich_one` runs); (d) for
  Pass-2, loaded records == `p2_attempted`; (e) the board's required KPI inputs are
  present. Otherwise the row is **excluded from that board's Borda** and rendered
  `unranked` — this covers partial `run_state/` copies (emit's copy is best-effort),
  not just a wholly missing directory. JSON shape — one `raw_values` contract on
  ranked and unranked rows alike (`ranking` stays ranked-only):

  ```json
  {
    "ranking": [
      {
        "model": "provider/model@release",
        "rank": 1,
        "measurement_source": "run_state_recomputed",
        "raw_values": {
          "quarantine_rate_pass1": 0.0,
          "cost_usd_pass1": 0.05,
          "cost_unknown_calls_pass1": 0
        }
      }
    ],
    "unranked": [
      {
        "model": "provider/model@release",
        "run_dir": "<run dir>",
        "measurement_source": "run_state_partial | measurements_fallback",
        "missing_kpis": ["recovery_rate"],
        "raw_values": { "...": "available raw values" }
      }
    ]
  }
  ```

  Rationale: an incomplete row would score on fewer axes (weight redistributed
  pro-rata, weak-spot axis set shrunk) and could rank *more* favorably purely
  because evidence is missing. No current row needs this path.
- **D-117-6 — Same row keys, same invocation.** Row identity stays
  `provider/model@release_version`; pass boards derive from the same
  `models_to_rundir` map the invocation already builds, so a model's three rows always
  come from the same run dir. No new CLI flags, no new subcommand.
- **D-117-7 — Renderer and persisted metadata are board-honest, full precision.**
  `_render_leaderboard_md` gains an optional board-scope/title parameter (default
  preserves today's main-board output exactly). For pass boards it suppresses all
  graph-specific prose when graph is inactive (Pass-1) and states the
  downstream-outcome caveat (Pass-2). Each pass-board JSON persists `board_scope`
  (`"pass1"` | `"pass2"`), `effective_top_weights` at **full precision** (Pass-1:
  2/3, 1/6, 1/6, graph 0.0 — never rounded decimals; rounding is Markdown-display
  only), and per-row `measurement_source` — never the canonical graph-inclusive
  constants copied from `score_models` when they don't describe the board.
- **D-117-8 — Cost is a first-class selection column, never a Borda axis, and never
  overclaimed.** The composite stays reliability/throughput-only; `cost_usd_pass1` /
  `cost_usd_pass2` render as prominent raw columns on their respective boards (and
  persist in `raw_values`). Because zero cost can mean *unpriced/failed* rather than
  *free* (verified in the cohort: an `enrich_failed` Gemini Pass-1 call with 10,960
  tokens carries `cost_usd: 0.0`), a board with any `cost_unknown_calls > 0` renders
  the total as `≥$X (+N unknown)` rather than an authoritative total, and the footer
  notes cost = model-pool pricing × tokens (cohort-comparable, not an invoice).
  Fixing the underlying failed-call cost attribution is the #110 deferred item —
  out of scope here.
- **D-117-9 — Competition ranking on pass boards.** Equal composites share a
  rank and the next rank skips (1, 1, 3). Applies to pass boards only; the main
  board's sequential ranking is unchanged. Tests assert the *displayed* rank on a
  tied cohort, not just the 0.5 Borda value.
- **D-117-10 — Write boundary, honestly stated.** Compute, validate, and render all
  three boards **before writing any file**: a pre-write failure leaves every existing
  artifact untouched. Each file is then replaced individually-atomically (write-temp-
  then-rename). A failure *mid-commit* (after some replacements) can leave a mixed
  generation — the shared `updated_at` across the three JSON payloads makes that
  **normally detectable under the single-user execution model** (second-precision
  timestamps; two invocations within the same second can alias — accepted, per the
  single-operator workload), and rerunning the command heals it. No manifest
  pointer, no two-phase commit. Pass-board filenames derive from the `--leaderboard`
  path stem: `<stem>-pass1.json` / `<stem>-pass2.json` (+ `.md`).

## 3. Data flow

```
kdb-benchmark score RUN… (unchanged entry point)
  ├─ main board:  measurements.json → _scored_and_diag → score_models   (as today)
  ├─ pass boards, per row:
  │    run_state/ → completeness check (D-117-5)
  │        → load_run_measurements → compute_processing
  │        → pass1 scored {q,r,l}_pass1 → canonical names → score_models
  │        → pass2 scored {q,r,l}_pass2 + graph 4 (from measurements.json)
  │            → canonical names → score_models
  │    (incomplete → row unranked on that board, D-117-5)
  ├─ validate + render all three boards (single updated_at)
  └─ individually-atomic writes: leaderboard{,-pass1,-pass2}.{json,md}
```

`leaderboard-pass{1,2}.json` persist the same payload shape as the main board
(models → run-dir pointers, ranking, weights, penalty params, updated_at) **plus**
`board_scope` / `effective_top_weights` / `unranked[]`, with per-row
`measurement_source` and a `raw_values` map on every ranked and unranked row
(cost, unknown-cost count, eligibility, coverage, dispositions, and the raw
per-pass KPI values), so the pass boards are themselves incremental across
invocations.

## 4. Testing

- `compiler/tests/test_kpi_processing.py`: per-pass split correctness —
  token-weighted recombination:
  `combined_rate == (p1_rate×p1_tokens + p2_rate×p2_tokens) / (p1_tokens+p2_tokens)`;
  `retry_load` recombination weighted by call count; empty-pass → None; cost sums
  over priced calls; **failed/unpriced calls with nonzero tokens count as unknown,
  never as $0** (R2-F2); pin new diagnostic keys.
- `tools/benchmark/tests/test_score.py`: pass-board files written next to main board;
  main-board scoring/ranking/scored columns unchanged and byte-identical on legacy
  fixtures, while a **future-shaped measurement carrying the #117 diagnostics** shows
  them only as extra raw columns (D-117-1 contract b, R2-F4); recompute path from
  synthetic `run_state/`; **Pass-1 reconciliation: missing sidecar, malformed
  sidecar, and duplicate `source_id` each render the row unranked** (R3-F1);
  partial `run_state/` (missing pass dir, short Pass-2 record count vs
  `p2_attempted`) renders unranked with the exact D-117-5 JSON shape; tied
  cohort shares displayed rank (D-117-9); graph prose absent from Pass-1 render,
  downstream caveat + eligibility/coverage/disposition columns present in Pass-2
  render (D-117-4); persisted `board_scope` + full-precision
  `effective_top_weights` (D-117-7); cost columns render `≥$X (+N unknown)` when
  unknowns exist (D-117-8); pre-write failure leaves prior artifacts
  byte-identical, shared `updated_at` on success, and a **simulated mid-commit
  failure followed by a rerun heals to one consistent generation** (D-117-10);
  incremental re-incorporation updates pass boards.
- Full suite green before commit.

## 5. Sequencing vs #115 + process gates

- **North Star first (Codex process gate):** after ratification and **before
  implementation**, `docs/CODEBASE_OVERVIEW.md` §7 is updated to document the
  three-board contract (it currently describes only the combined board).
- **Rejected alternative recorded (gate):** emit-time-only new diagnostics (no
  score-time recompute) was rejected — historical runs would permanently lack the
  recovery/cost splits, degrading every existing row to a 2-axis score and splitting
  the cohort into two evidence classes. Score-time recompute keeps one scoring
  contract for all rows that carry `run_state/`.
- Implementation lands as its own commit(s), **not** folded into the #115 Gate-2
  commit. It changes no pipeline behavior, so the #115 baseline cohort may fire from
  Gate-0 HEAD `e9ca323` as planned regardless; landing #117 first only means Joseph
  can score the baseline into three boards the moment it finishes. Proposed branch:
  `feat/117-per-pass-leaderboards` off `main` (baseline HEAD stays untouched).

## 6. Out of scope

- Split-model runs (different models per pass) → **Task #118** (proposed; orchestrator
  CLI, header stamps, row-key semantics all need design; revive after #116). Until
  then, isolated per-pass causal attribution is unavailable (D-117-4 caveat).
- Pass-1 failed-call cost attribution fix → the #110 deferred item (D-117-8 renders
  around it).
- GT-based Pass-1 label correctness → stays with deferred #98.
- Pass-1 semantic quality beyond GT-free robustness/cost signals.
