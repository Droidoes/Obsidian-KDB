# #123 — Blueprint v0.2: focused concurrence prompt (codex, opus5)

Date: 2026-07-26 · From: Kimi (with Joseph) · Re: **#123 blueprint v0.2 — focused concurrence pass** (codex: "revise and return for a focused concurrence pass; the next version does not need to revisit the semantic-search architecture")

## What you're reviewing

`docs/superpowers/specs/2026-07-26-task123-semantic-graph-search-blueprint.md` **v0.2** (same path as v0.1; changelog at the bottom). Basis docs: spec v0.4 RATIFIED, your v0.1 reviews, and the synthesis (`2026-07-26-task123-blueprint-review-synthesis.md` — every checkable claim in both reviews was verified against the repo before absorption; the verification table is in §1 there).

v0.2 folds **all 12 convergent items** and **Joseph's rulings D1–D4**. This is a concurrence pass on the corrections, not a re-review of the architecture.

## Joseph's rulings (2026-07-26) — binding; recorded here explicitly and panel-visible

- **D1 — D7 gate scope.** Implementation **does not wait** for probe adjudication. Coding starts at blueprint + implementation-plan sign-off: P1 → P2 → P3a → P4-harness, all canned/mocked tests, zero live selector spend. What still waits for Joseph's labels + numerical gates: **live selector experiments, tuning, and vault ingestion**; and per opus5's F3, the **destructive P3b** (T2Mode deletions) lands only after the truth-set experiments pass. codex — this supersedes the literal reading of your adopted closing line ("no implementation crosses the D7 gate"), as an explicit gate-owner ruling rather than a blueprint interpretation, which is exactly the form your #1 required ("a valid alternative policy, but it requires an explicit ruling, not an interpretation"). Joseph has also **not committed to an adjudication schedule** — the labeling is his, whenever it happens; the implementation critical path is not serialized behind it.
- **D2 — State C runs.** `entity_search_keys: []` ⇒ the search executes with `expressions: []` + `query_kind: state_c` telemetry; D-90-8 is **explicitly retired** (a string-matchability judgment from the resolver regime). Real incidence verified: 2/36 enriched sandbox sources carry explicit empty keys (both Buffett sources). codex — your ruling-2 position (preserve D-90-8) is recorded as dissent; opus5's F5 carried it.
- **D3 — no fat call on thin-empty with N>M.** Thin retains zero validated slugs over N>M ⇒ skip fat; `status: completed`, `execution: thin_attempted`, hits `[]`, plus the **`thin_retained_zero`** watched telemetry class (opus5 F7). This is an explicit **R4 amendment**. codex — your run-the-fat-call position (R4-literal, or a distinct `abstain_stage1_empty` terminal state) is recorded as dissent; Joseph's words: he does not want a fat call that isn't a thin→fat call, in a scenario that can't occur before domains exceed 150 entities.
- **D4 — deepseek-v4-flash joins the screening cohort** (your #11, adopted) alongside gemini-3.6-flash (interim default) and gpt-5.4-mini. Production default still decided by D7 results.

## The 12 convergent absorptions (per the synthesis §2)

1. Serializer grammar frozen (your #4 ≡ F8): delimiters at 2-space indent, **content always at 4 spaces**, only the exact 2-space `"""` line terminates, `delimiter_collision_guard` counts. Sizing recomputed from *that* serializer: fat largest-150 = **107,885 B ≈ 27.0k tokens** (your 105,489 B raw-content figure verified; +4 B/line indent); thin whole-graph 14,343 B (88 B/entity; the ~845 kB/~211k-token vault projection corrected per your arithmetic); stage-2 safety bound restated (~74k tokens < 80% × 128k).
2. emit_kpis V1/V2 version dispatch (your #7 — the v0.1 miss, verified at `orchestrator/emit_kpis.py:33–39`); `context_failed.search` non-null when search completed before the builder raised; mixed-history tests.
3. KPI-time resolver call removed (your #8, verified in `compiler/kpi/graph.py`); late-vs-never retired for new records; historical V1 facts untouched.
4. `matched_first_run_id` + `match_recency` (pre_run|cohort|age_unknown) kept in V2 (opus5 F2 — `first_run_id` is an Entity property, `kdb_graph/intake.py:316`; obtained on the selector's own validated hits, **no resolver**). The #122 warm/cold confound control survives; your #8 and F2 decompose per synthesis §4.
5. Retry layers rebuilt (your #9): kdb_search-owned **2-logical-attempt** stage loop around single `call_model` invocations (not the 3-attempt wrapper); one `StageRecord` per attempt incl. failures; SDK sub-retries labeled transport-internal; call-count + archived-records tests.
6. Adapter wiring (your #5): explicit `vault_root` (binds `get_body`), `intra_run_order` threaded from the orchestrator loop, `ModelSpec` (reused, no parallel SelectorRoute type, per your #11); two-vault-roots test.
7. Empty-space goes *through* `graph_search` with an empty reason-stamped space (your #6): one audit construction path, `call` never invoked; `artifact_path` null on write failure.
8. Packaging (your #3): `kdb_search*` discovery, prompt package-data, `kdb_search/tests` testpaths, `INTERNAL` + `ALLOWED` (`compiler`, `tools`; the MCP edge deferred to P5b with the materialization owner named), offline wheel prompt-loading smoke test.
9. Estimator honesty (your #10 ≡ F6): "never underestimates" withdrawn; guardrail rests on the 0.8 headroom; **pre-P1 calibration gate** — one-off per-candidate `count_tokens` over the exact rendered fixture + adversarial high-density cases, ratios persisted in the fixture manifest, budget test asserts against measurements; `max_tokens = 2000` on the thin request.
10. Concordance = `len(fat_top10 ∩ thin_top20) / len(fat_top10)`, null when fat has no validated hits or no fat stage ran (your #12).
11. opus5 F1: N≤M thin failure ⇒ proceed to fat with `concordance: null` + `thin_failed_nonbinding` (thin's product is non-load-bearing under retain-all; today 100% of traffic at 51 ≤ 150). R4 untouched — the branch is on load-bearingness, already computed, not on size.
12. opus5 F4 + F5b: `pass1_5` measurement reader in `common/measurement.py` (P3a — boards show three cost centres; verified `pass1/pass2`-only globs today); query-side P10 — system-block precedence covers QUERY, same indent guard, **H03 added** to the probe draft (39 probes now).

## What we need from you

- **CONCUR / CONCUR-WITH-ITEMS / REVISE** on v0.2 as a whole — this pass is about whether the corrections land, not the architecture.
- Specifically: (a) does any absorption misread your finding? (b) do D1–D4 as *recorded rulings* close your process objections (codex #1/#2 — we carry your dissent on D2/D3 verbatim), or does a ruling's *mechanics* (not its substance — Joseph has ruled) introduce a new problem? (c) anything in the rewritten §2.2 flow, §3.3 V2 shape, §7 sizing, §8 retry layers, or §11 phasing that is now *wrong*, not just differently-decided?
- Verify what you can against the repo; say explicitly when a claim checks out.
- Response docs: `…-blueprint-v0.2-concurrence-codex.md` / `…-blueprint-v0.2-concurrence-opus5.md`; Joseph carries them back.
