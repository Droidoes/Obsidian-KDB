# #123 Blueprint v0.2 — opus5 concurrence

Date: 2026-07-26 · Respondent: **opus5** · Reviewing: blueprint **v0.2** per `…-blueprint-v0.2-concurrence-prompt.md`
Prior: round-1 response · synthesis review · vision review · spec v0.1/v0.2/v0.3 reviews · blueprint v0.1 review (F1–F8)

## Verdict: **CONCUR-WITH-ITEMS**

All eight of my v0.1 findings are absorbed faithfully — none is misread, and two (F3, F7) came back stronger than
I asked. D1–D4 are Joseph's calls and I take them as settled; **D1 and D3 need no further comment from me, and D2
I argued for.** The items below are not re-litigation: three are places where a *correction* introduced a new
defect, and one is where two rulings landed in the same version and their interaction wasn't checked.

**Blocking for P1: G2, G3, G4** (each changes a shape or a test that P1 encodes). **G1 is blocking only under one
of two readings** — stated explicitly in the finding so it isn't treated as ambient noise. G5–G8 ride along.

---

## 1. Do the absorptions land? (my F1–F8)

| # | Absorbed as | Reads correctly? |
|---|---|---|
| F1 | §2.2 N≤M thin-failure ⇒ proceed to fat, `concordance: null`, `thin_failed_nonbinding` | **Yes.** One wording nit — §2.2's note "the branch is on load-bearingness, not on size" is circular (the branch *is* `N ≤ M`); the substance is right: retain-all already made stage-2 input size-conditioned, so no new conditionality enters. |
| F2 | §3.3 `matched_first_run_id` + `match_recency` on `key_outcomes` | **Substance yes, carrier wrong — see G2.** The Entity-property basis is verified and correctly reasoned (no resolver). |
| F3 | P3a/P3b split; P3b lands after P5a experiments pass | **Yes, and stronger than I asked** (I asked for post-gate; v0.2 puts it post-experiments). One clarification in G9. |
| F4 | §11 P3a `pass1_5` measurement reader; "boards show three cost centres" | **Direction yes, mechanics under-specified — see G1.** |
| F5 | D2 (State C runs, `query_kind: state_c`, D-90-8 retired) | **Yes.** Incidence claim verified exactly (2/36, both Buffett). |
| F5b | §5 query-side P10 + H03 in the probe artifact | **Yes.** 39 probes, H01–H03 present. |
| F6 | §7 "never underestimates" withdrawn; guardrail rests on 0.8 headroom; calibration gate | **Yes on the withdrawal — see G4 on the gate's executability.** |
| F7 | D3 + `thin_retained_zero` watched class | **Yes.** |
| F8 | §5 frozen grammar (2-space delimiters, content at 4 spaces, exact-terminator rule + guard counter); sizing recomputed | **Yes — and the table reproduces byte-exactly. Two clauses missing: G8.** |

## 2. D1–D4 as recorded rulings

- **D1** — closes the process question in the form codex required (gate-owner ruling, not blueprint
  interpretation). Nothing further from me. One note: the **pre-P1 calibration measurement is live API spend**
  (§7). It is not a selector experiment, so it doesn't cross D1's line — but it is a paid run, so it is Joseph's
  to fire, and P1 is blocked on it. Worth stating in §11 so the dependency is visible.
- **D2** — I carried this; nothing to add. Mechanics interact badly with F2's absorption (G2).
- **D3** — Joseph's reasoning ("no fat call that isn't a thin→fat call") is coherent and the scenario is
  unreachable below 150-entity domains. Settled. codex's `abstain_stage1_empty` alternative would have bought a
  cleaner terminal-state taxonomy; `thin_retained_zero` on `status: completed` carries the same signal, provided
  it is watched — which §3.3 does.
- **D4** — no objection. Verified all three ids are live in the pool with the stated windows.

## 3. Findings

### G1 — F4's absorption doesn't say whether pass-1.5 enters the *scored* aggregate (load-bearing **under one reading**)

The blueprint says "`pass1_5` measurement reader in `common/measurement.py` … boards show three cost centres." It
does not say whether the pass-1.5 projections join the measurement list that the scored axes are computed over.
The two readings are not equivalent:

- **If they join the union** (the natural reading of "a reader in `common/measurement.py`", whose loader returns
  `pass1 + pass2` as one list at `measurement.py:377`), then: `compiler/kpi/processing.py:46-47` computes
  `N = len(calls)` and `T = sum(input+output)` over **all** calls, and `scored = {quarantine_rate, recovery_rate,
  latency}` are per-1M-**token** rates over that `T` (`processing.py:1-30`, `tools/benchmark/pass_boards.py:25`
  `_AXES`). `orchestrator/emit_kpis.py:238-241` passes the union straight in. Pass-1.5 adds ~10.7k conservative
  input tokens per source (§7) against a pass-2 call of comparable size — i.e. `T` roughly doubles, and **all
  three scored axes on the main board move without any model behaving differently.** Every 2026-07-25 baseline
  row becomes non-comparable, and the #117 promotion rule is computed across that discontinuity.
- **If they are kept separate** (a third list, or filtered in `compute_processing`), nothing breaks.

I am not asserting the first reading is what's intended — it's an unwritten implementation choice. **The fix is to
write it down**: scored axes are computed over pass1+pass2 only (with a test that asserts a pass-1.5 record does
not move them), *or* Joseph declares an explicit board re-baseline. Either is fine; leaving it to the implementer
is not, because the failure is silent.

Four sub-items are gaps under **both** readings, and these are the ones I'd act on regardless:

1. `pass_boards._SPLIT` is `{p: {canon: f"{canon}_{p}"} for p in ("pass1", "pass2")}` (`pass_boards.py:26`), and
   `compute_processing` emits exactly `*_pass1` / `*_pass2` diagnostic keys. A third board needs both extended
   (`quarantine_rate_pass1_5`, `latency_pass1_5`, `cost_usd_pass1_5`, `cost_unknown_calls_pass1_5`,
   `retry_load_pass1_5`, `recovery_rate_pass1_5`).
2. `_completeness` (`pass_boards.py:51-77`) is the D-117-5 contract: it reads `stats[f"{pass_}_dir_exists"]`,
   `stats[f"{pass_}_malformed"]`, and compares a record count against a **header field** (`p1_attempted` /
   `p2_attempted`). `RunMeasurementHeader` (`measurement.py:198-220`) has no search analog. Without one, a
   pass-1.5 board can never be marked complete, so it renders permanently unranked — i.e. the cost centre never actually appears.
   Add `searches_attempted` (or equivalent) to the header.
3. **One measurement per source, or one per stage?** `PassCallMeasurement` carries a single `prompt_version`
   (`measurement.py:29`) but pass-1.5 has two prompt versions per search (thin + fat), and the pass-1 completeness
   contract flags `pass1_duplicate_source_id` when unique source_ids ≠ records — so a per-stage projection
   (2–4 records per source) needs that check defined differently. Decide and state it; both shapes are
   defensible, and the choice determines whether per-stage cost attribution survives.
4. `effective_top_weights` (`pass_boards.py:34-49`) returns the pass-1 pro-rated vector for anything that isn't
   `"pass2"` — so `"pass1_5"` accidentally gets the right weights (no graph term). Worth an explicit case rather
   than relying on the fall-through.

### G2 — F2 was absorbed onto the wrong carrier; the #122 confound control is null exactly where D2 routes new traffic (load-bearing)

F2 asked for provenance on the **matched entity**. §3.3 attaches `matched_first_run_id` / `match_recency` to
`key_outcomes`, which is "1:1 positional alignment with `keys_emitted`" — i.e. keyed to **expressions**. Two
consequences, both structural:

1. **State C has zero expressions and can have non-zero hits.** `keys_emitted: []` ⇒ `key_outcomes: []` ⇒ no
   provenance rows at all, while the search returns hits. Verified incidence: 2/36 enriched sources in the
   2026-07-25 gemini run (`run_state/pass1`, both Buffett sources) — and D2 is precisely the ruling that turns
   those from no-search into full searches. The one class of traffic D2 newly creates is the class where the
   warm/cold control disappears.
2. **Unattributed hits have no expression row either.** §3.3 already counts `unattributed_hit_count`; those hits
   are real graph entities with a real `first_run_id`, and under the spec's coercion rule (unknown
   `matched_expression` removed, "an unattributed hit stands") they are expected, not exceptional.

So the read spec §9 requires — "before/after on T2 delivered, `matched`, `match_recency`" — is computable only
over the subset of hits that happen to be expression-attributed. That is the confound #122 was built to kill,
reintroduced through a data-shape choice.

**Fix:** carry `first_run_id` + derived `pre_run | cohort | age_unknown` on the **hit** records in the V2 `search`
section (one read over the selector's own validated hits — same single query, same no-resolver property). Keep the
per-expression copy if it's convenient for the accounting series; it should be a projection of the hit-level
facts, not the only place they live.

### G3 — §7's stage-2 safety bound is falsified by the fixture it was measured from (load-bearing)

§7 states the bound as `150 × ~1,977 B (250w +10% + indent + field overhead) ≈ ~297k B ≈ 74k tokens`, and §9 is
told to assert this formula. Rendered from the frozen §5 grammar over fixture v1, **two entities exceed 1,977 B**:

| slug | words | rendered fat block |
|---|---|---|
| `value-investing-as-owner-mindset-and-analytical-rigor` | 251 | **2,209 B** |
| `pabrai-cannibal-formula-and-singleton-playbook` | 262 | **2,164 B** |

These are the two entries the fixture manifest itself lists under `capped` — the only pages the excerpt policy
actually truncates. So the per-entity figure isn't a bound at 163 entities, and a §9 test asserting it would pin a
ceiling the substrate already breaks.

Recomputed honestly: `150 × 2,209 B = 331 kB ≈ 83k tokens` at the observed maximum; at the policy ceiling
(250w + 25w extension ≈ 275w, at this text's ~8.8 B/word) ≈ 2,500 B/entity ⇒ `375 kB ≈ 94k tokens`. Against
80% × 128k = 102.4k that is an **8% margin, not the 28%** the ~74k figure implies. **No conclusion changes for the
configured pool** (400k / 1M / 1M — all verified), which is why I rate this load-bearing on the *test*, not on the
architecture.

**Fix:** derive the per-entity figure from the policy maximum and verify it against the fixture maximum, then
assert *that*. Optional, and flagged as spec-touching because R2 as ratified is a stage-1 rule: run the same
estimator before the **fat** call too. Fat's size is data-dependent through the excerpt tail, and it is the stage
that is 25× larger; guarding only the cheap stage is the asymmetry worth naming even if you decline to fix it now.

### G4 — the pre-P1 calibration gate is unexecutable as specified for two of the three candidates (load-bearing)

§7 requires "each candidate's authoritative `count_tokens` (a single network call per candidate)". `count_tokens`
appears **nowhere in the repo** (grep: zero hits), and only `google-genai` exposes a count-tokens endpoint —
OpenAI and DeepSeek have none, and there is no local tokenizer in `.venv` (the premise of B3). So the gate can be
run for `gemini-3.6-flash` and not for `gpt-5.4-mini` or `deepseek-v4-flash`, and P1 is gated on it.

**Fix:** calibrate against **reported usage** instead — one minimal real call per candidate, read the returned
input-token count (`call_model` already surfaces it for every provider). Same authority (it is the number the
provider bills), same one-off cost, no new per-provider code. Joseph fires it (standing rule on API-cost runs);
note the dependency in §11 so P1 isn't scheduled ahead of it.

### G5 — the "SDK sub-retries" label is wrong for the interim default selector (minor; **not** a regression)

§8 says SDK transport sub-retries are "`max_retries=2` inside the provider clients (#121 D8), labeled as such in
the stage entry's detail." `common/call_model.py:212` documents the opposite for gemini: *"No max_retries here —
google-genai has no such constructor kwarg; its retry knob is HttpOptions.retry_options (default None = no
SDK-internal retries). D8 preserves exactly that."* (:192 and :273 do set it for the openai-family clients.) And
`_RETRYABLE` (`call_model_retry.py:28-37`) lists only anthropic + openai exception types, so gemini gets no
backoff at any layer. With `gemini-3.6-flash` as the interim default, the selector's transport resilience is 2
immediate attempts, no backoff, no Retry-After.

To be clear: **this is not a regression.** Pass-1 already calls bare `call_model`
(`ingestion/enrich/pass1_caller.py:179`); only pass-2 uses the 3-attempt wrapper (`compiler/compiler.py:369`), so
the blueprint's choice matches existing precedent. The fixes are small: (a) the stage entry should record the
provider's *actual* sub-retry policy rather than asserting 2; (b) either give the kdb_search loop Retry-After/
exponential backoff for the openai-family classes, or state that it deliberately adopts pass-1's no-backoff
posture.

### G6 — §7's `selector.ctx_window` can be `None` (minor)

`ModelSpec.ctx_window` is `int | None = None` (`common/model_pool.py:58`, populated by `entry.get("ctx_window")`
at :137) and is **not** validated at Gate 1 — only route and `thinking` are. `floor(selector.ctx_window × 0.8)`
would raise `TypeError` inside budget estimation for a pool entry that omits it. Under §2.1's fail-hard posture
this belongs at resolution: assert it with a typed config error. All three D4 candidates carry it today
(verified), so this is future-proofing, not a live bug. Related: `common/model_pool.py:156` already has
`fits_context(est_input=…, requested_output=…, ctx_window=…)` — either reuse it under the 0.8 factor or say why
`budget.py` doesn't.

### G7 — the frozen grammar under-specifies the two clauses the sizing table depends on (minor, but it will cost a debugging session)

I reproduced §7's fat figures **byte-exactly** — 112,673 / 38,512 / 107,885 — but only after discovering two
serializer behaviours the grammar doesn't state:

1. The excerpt is split on `"\n"`, not `splitlines()`, so a trailing newline emits a final **whitespace-only
   `"    \n"` line** (161 of 163 excerpt files end with a newline).
2. **Blank lines are indented too** (377 blank lines across the fixture receive 4 spaces).

A faithful implementer reading §5 as written and using `splitlines()` with blank lines left empty renders
**111,868 B** whole-graph and **107,145 B** at 150 — 0.7% below the table, with golden byte tests failing for a
reason the grammar gives no hint about. Two clauses in §5 fix it. (Both behaviours are harmless in themselves; a
future "strip trailing whitespace" tidy would silently break the pinned bytes, which is the other reason to write
them down.)

### G8 — two small unnamed items (minor)

1. **`execution` on the F1 path is unnamed.** Thin failed, `N ≤ M`, fat succeeded — §2.2 doesn't say what
   `execution` carries. `two_stage` would assert two stages ran; `thin_attempted` is wrong the other way. Name it
   (`fat_after_thin_failure`, or whatever fits the enum) so the KPI can separate it; `thin_failed_nonbinding`
   makes it recoverable either way, hence minor.
2. **P3a's plumbing isn't in scope-text.** `compile_source` (`compiler/compiler.py:654-677`) has no ordering
   param and the orchestrator loop (`orchestrator/kdb_orchestrate.py:711-718`) passes no index; the selector
   reaches the compiler as provider/model/route scalars, not a `ModelSpec`. P3a therefore needs `intra_run_order`
   + a selector id threaded through `compile_source`, plus a CLI flag if the D4 candidates are to be switchable
   for the P5b live cohort. Implementation-plan detail, not a blueprint defect — noting it only so it isn't
   discovered mid-P3a. (Also worth checking whether the ordering is already recoverable from the manifest before
   persisting it a second time.)

## 4. Verified against the repo — claims that hold

**Sizing (§7) — every cell reproduced from fixture v1.** Thin: 14,343 B / 88 B per entity whole-graph; 4,404 B /
86 B for value-investing (51) — **exact**. Fat: 112,673 / 38,512 / 107,885 B and 691 / 755 / 719 B per entity —
**exact**, given G7's two clauses. bytes÷4 columns (3.6k / 1.1k / 28.2k / 9.6k / 27.0k) all check. Vault
projections check: 9,600 × 88 B = 845 kB ≈ 211k tokens; 3,000 × 88 B = 264 kB ≈ 66k. Corpus shape as previously
corrected: 163 entities, mean 73.2 words, median 65, max 262, and **2/163** pages exceed 250 words.

**D2 incidence — exact.** 36 enriched sidecars in `benchmark/runs/gemini-3.6-flash-2026-07-25T09-41-46_EDT/
run_state/pass1`, of which **2** carry `entity_search_keys: []`: *Berkshire Hathaway Annual shareholder meeting -
2023* and *Warren Buffett On Arbitrage*.

**F2's basis holds.** `kdb_graph/intake.py:316` — `ON CREATE SET p.created_at=$ts, p.first_run_id=$run_id`.
`first_run_id` is an Entity property set on create; reading it off a validated hit needs no resolver. The
reasoning in §3.3 is correct — only the carrier is wrong (G2).

**codex #7 holds.** `orchestrator/emit_kpis.py:33-39` imports `ContextRecordV1` and `parse_context_record_v1`
directly. Without version dispatch, V2 records load as malformed — the v0.1 miss is real.

**codex #8 holds, and is safer than it looks.** `compiler/kpi/graph.py:141` and `:298` call
`resolve_to_canonical_slugs`. Importantly, the two fields that retire — `search_key_late_resolution_rate` and
`search_key_never_resolved_rate` (`:172-173`) — are **not** in `GRAPH_WEIGHTS`
(`compiler/kpi/score.py:68-73` = graph_connectivity / link_density / supports_density / entity_reuse). So the
retirement touches **no scored axis** and no composite weight; it is a watched-series re-baseline only. This is
the objection I went looking for and did not find; worth recording, because it's the difference between "amend the
#122 eval doc" and "re-baseline the boards."

**Package/packaging claims hold.** `tools/tests/test_package_boundaries.py` gates on `root in INTERNAL` in the AST
walk, so codex #3's "silently ignored without the INTERNAL row" is exactly right; `ALLOWED` has the shape v0.2
describes. `pyproject.toml:43` `packages.find` include list indeed lacks `kdb_search*`; `testpaths` (:52) already
covers `tools/benchmark/tests`; `*.tests` exclusion means `kdb_search/tests` stays out of the wheel, consistent
with every other package. Minor: existing package-data convention is `prompts/*.md` (compiler); `.txt` is a
harmless deviation.

**Adapter API holds.** `kdb_graph/queries.py:260` `domain_entity_slugs`, `:247` `active_entities` both exist with
the signatures §3.1 assumes.

**Retry facts hold.** `call_model_with_retry` is `MAX_RETRIES + 1 = 3` logical attempts with exponential backoff
and Retry-After honouring (`call_model_retry.py:20, 60, 72-81`) — so codex #9's attempt-collapse concern is real,
and 2 kdb_search-owned attempts around bare `call_model` is a coherent replacement (subject to G5).

**Probe artifact holds.** `benchmark/truth/task123_search_probes_draft_v1.json` = **39** probes including H01,
H02, **H03**.

**D4 candidates hold.** `gpt-5.4-mini` ctx_window 400,000; `gemini-3.6-flash` 1,048,576; `deepseek-v4-flash`
1,000,000 — all three live in `common/models.json`, matching §7's "400k / 1M / 1M".

## 5. What I'd fold before P1 starts

- **G2** — changes the V2 record shape, so it has to precede the P3a tests that pin it (and it is the one item
  where a ruling's interaction, not a correction, created the defect).
- **G3** — a §9 test would otherwise encode a ceiling the fixture already exceeds.
- **G4** — the gate as written cannot be executed for two candidates, and P1 waits on it.
- **G1** — one sentence deciding whether pass-1.5 joins the scored union, plus the header count field, before the
  P3a measurement work is written.

G5–G8 are wording, telemetry-naming, and plumbing items that can ride along with the phases that touch them.
Nothing above reopens the architecture, and nothing contradicts D1–D4.
