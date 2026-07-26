# #123 Semantic Graph Search — Blueprint v0.2 Codex Concurrence

**Date:** 2026-07-26  
**Reviewer:** GPT-5.6 / Codex  
**Concurrence packet:** [`2026-07-26-task123-blueprint-v0.2-concurrence-prompt.md`](2026-07-26-task123-blueprint-v0.2-concurrence-prompt.md)  
**Blueprint:** [`2026-07-26-task123-semantic-graph-search-blueprint.md`](2026-07-26-task123-semantic-graph-search-blueprint.md) v0.2

## Verdict: CONCUR-WITH-ITEMS

The v0.1 corrections substantially land, and I concur with the blueprint's
architecture and Joseph's D1–D4 rulings. The rulings are explicit gate-owner
decisions rather than blueprint interpretations, so they close my earlier D7
and R4 process objections. My D2/D3 dissent is represented accurately.

Five bounded corrections should land before **Proceed**. They do not require
another architecture review: one fixes contradictory call-count language, two
finish measurement contracts that v0.2 currently leaves ambiguous, one makes
the calibration gate executable in phase order, and one synchronizes the
binding rulings into the project's authoritative documents.

## Direct answers to the concurrence questions

| Question | Response |
|---|---|
| **(a) Does an absorption misread a Codex finding?** | All Codex v0.1 findings are represented fairly. The estimator/calibration absorption captures the intended safeguard, although its new “Pre-P1” mechanics are not executable as ordered. Opus5 F4 is directionally absorbed but not yet closed by a reader/glob alone. |
| **(b) Do D1–D4 close the process objections?** | **Yes.** D1 and D3 are explicit owner amendments; D2 and D3 preserve my contrary positions as dissent; D4 adopts the three-model cohort. The remaining D3 issue below concerns terminal-state mechanics, not Joseph's decision to skip fat. |
| **(c) Is anything in the rewritten blueprint now wrong?** | **Yes, locally.** “Exactly two attempts” and “two calls per executed search” contradict the retry flow and D3. Singular per-expression provenance is undefined for multi-hit expressions. “Boards show three cost centres” does not follow from the planned measurement reader. The Pre-P1 calibration depends on renderers introduced in P1/P2. |

## Closures verified against the repository

1. **Serializer and sizing — checks out.** Re-rendering the frozen fixture with
   two-space field/delimiter lines and four-space content reproduces the v0.2
   figures: thin whole graph **14,343 B**, thin value-investing **4,404 B**,
   fat whole graph **112,673 B**, fat value-investing **38,512 B**, and the
   largest 150-entry fat subset **107,885 B**. The corrected 88 B/entity
   vault projection and ~74k-token safety bound are internally consistent.

2. **Packaging — correction checks out.** Current package discovery, package
   data, pytest paths, and boundary declarations do not know `kdb_search`;
   §1 now names each required addition, includes the `tools` consumer edge,
   and defers the MCP edge until its materialization owner is defined.

3. **Adapter/audit wiring — correction checks out.** Explicit `vault_root`,
   `ModelSpec`, and source ordinal address the real production seams. Routing
   reason-stamped empty spaces through the core establishes one typed audit
   path, and nulling `artifact_path` on a warn-only write failure avoids a
   phantom persistence claim.

4. **V2 loading and KPI retirement — correction checks out.**
   `orchestrator/emit_kpis.py` is V1-specific today, and
   `compiler/kpi/graph.py` performs the post-run resolver read identified in
   v0.1. Version dispatch, mixed-history tests, preservation of a completed
   search through later context failure, and P3b removal of the KPI resolver
   read close those findings.

5. **Retry ownership — architectural correction checks out.** A
   `kdb_search`-owned loop around one raw `call_model` invocation per logical
   attempt can archive one `StageRecord` per attempt. Avoiding
   `call_model_with_retry` is necessary because that wrapper would collapse
   the logical audit boundary. The wording correction in item 1 remains.

6. **Probe artifact — checks out.**
   `benchmark/truth/task123_search_probes_draft_v1.json` contains **39**
   probes, including H01, H02, and the new query-side H03.

7. **Measurement gap — reconfirmed, but only partly absorbed.**
   `common/measurement.py` loads only `pass1/*.json` and `pass2/*.json`;
   `compiler/kpi/processing.py` partitions only those two values;
   `tools/benchmark/pass_boards.py` hard-codes the same two scopes; and
   `tools/benchmark/cli.py` generates only pass-1 and pass-2 boards.

## Items to close before Proceed

### 1. Freeze the actual stage/attempt count contract

**Severity: correctness; required**

Section 8 says “exactly 2 logical attempts per stage,” while §2.2 correctly
says at most two. The adapter and P3a tests then say “two selector calls per
executed search.” Neither statement survives the v0.2 flow:

| Terminal path | Logical selector calls |
|---|---:|
| Empty space or budget exceeded | 0 |
| D3 thin-retained-zero | 1–2 thin, 0 fat |
| Normal completed search | 1–2 thin + 1–2 fat = 2–4 |
| Exhausted thin failure, N>M | 2 thin |
| Exhausted thin failure, N≤M, then fat | 2 thin + 1–2 fat = 3–4 |
| Exhausted fat failure | 1–2 thin + 2 fat = 3–4 |

Change §8 to **“up to two logical attempts per executed stage; attempt 2 only
after an allowed retry class.”** Replace “two calls/executed search” in §3.1,
P3a, and `test_compile_source` with branch-specific assertions. The invariant
should be:

```text
logical_call_count == number of archived StageRecords
```

Provider SDK sub-retries remain excluded from both sides.

The D3 terminal also needs its complete controller-owned result contract:
every request expression is unresolved, `concordance` and fat-only yield/body
metrics are null or not-applicable as their schemas require, and
`evidence_status=not_applicable`. This specifies Joseph's ruling without
reintroducing a fat call.

### 2. Resolve multi-hit provenance cardinality

**Severity: load-bearing evaluation fidelity; required**

The spec permits a hit to answer multiple expressions, and an expression can
be attributed by multiple validated hits. V2 nevertheless gives each
expression one `matched_first_run_id` and one `match_recency`, without saying
which matched hit owns them. Two conforming implementations can therefore
produce different #122 warm/cold decompositions from the same search result.

Freeze one of these contracts:

- **All-match provenance:** each expression stores selector-ordered
  `matched_entities: [{slug, first_run_id, match_recency}]`; KPI aggregation
  operates over explicit expression/entity pairs. This preserves all evidence
  with a larger record.

- **Representative provenance:** `matched_first_run_id` and `match_recency`
  come from the highest-ranked validated hit attributed to the expression.
  This is smaller, but the cohort metric describes representative matches,
  not all matched entities.

The adapter must also name the non-resolver read. `queries.active_entities()`
currently returns only title and page type. It can either materialize
`first_run_id` alongside the initial eligible-space metadata or perform one
batched direct read over validated hit slugs. In either case, no alias/exact
resolver participates.

### 3. Finish the pass-1.5 board contract

**Severity: load-bearing cost integrity; required**

A `from_pass1_5` projection and `search/*.json` glob get records into the
measurement list, but they do not make a third cost centre appear.
`compute_processing`, loader statistics/completeness, `_SPLIT`, CLI board
generation, rendering, and tests all enumerate only `pass1` and `pass2`.

Two bounded designs satisfy F4:

- **Third pass board:** admit `pass1_5` throughout the header/count,
  processing, completeness, board, CLI, renderer, and test contracts, emitting
  `leaderboard-pass1_5.*`. This is explicit but requires defining which
  selector-quality axes are scored versus diagnostic.

- **Cost-centre diagnostics without a third ranked board:** keep the existing
  ranked board topology, but add `cost_usd_pass1_5`,
  `cost_unknown_calls_pass1_5`, retry/call count, tokens, and latency to the
  aggregate evidence and rendered raw columns. This is simpler but does not
  rank pass-1.5 independently.

Whichever is selected, add an integration invariant that total run cost and
call count reconcile to pass 1 + pass 1.5 + pass 2. The current sentence
“boards show three cost centres” is not an implementation blueprint until
that output contract is selected.

### 4. Put calibration after the exact renderer exists

**Severity: phase-order/implementability; required**

The calibration gate says “after the serializer is frozen” and counts the
exact rendered fixture, system template, user wrapper, and query block.
Production projection is built in P1, while prompt templates and golden
rendering are built in P2. A **Pre-P1** measurement therefore cannot be
generated from the production renderer it is intended to calibrate, and P1's
budget test cannot depend on that not-yet-derived artifact.

Two workable orderings are:

- Generate and persist calibration at the end of P2, after golden rendered
  bytes pass, and make it a gate before D7 live experiments.

- Keep a pre-P1 checked-in artifact only if a standalone frozen reference
  renderer produces it and P2 proves byte parity with that renderer.

Also record the counting source per candidate—provider endpoint or pinned
tokenizer, version/model identifier, input hash, token count, and measured
bytes/token. The repository has no provider-neutral `count_tokens` primitive,
so “each candidate's authoritative count_tokens” needs provider-specific
mechanics or a declared fallback. Finally, state whether non-generative remote
token-count calls are permitted by D1's zero-live-selector-spend rule; otherwise
schedule them after D7.

### 5. Synchronize the rulings into the ratified basis and North Star

**Severity: documentation gate; required before implementation**

D1–D4 are sufficiently explicit to close my decision-process objections, but
the currently ratified spec v0.4, `docs/TASKS.md`, and
`docs/CODEBASE_OVERVIEW.md` still say:

- no implementation crosses D7 before labels/gates; and
- R4 runs thin then fat every source, every run.

At ratification, publish a spec amendment or next spec version carrying D1–D4,
then update the task ledger and North Star before implementation begins. This
is synchronization of already-made owner rulings, not a request to vote on
their substance again.

One related editorial correction: B1 is marked “RATIFIED” in §13 although the
v0.2 packet is presently soliciting concurrence. Change it to
“selected/proposed pending blueprint ratification,” or cite the separate
Joseph ratification record if B1 alone was ratified earlier.

## Ratification disposition

I concur with v0.2's system design, the accurate representation of my v0.1
findings, and Joseph's D1–D4 authority decisions. Do not issue **Proceed**
against the text unchanged. Close items 1–5 and return only the targeted diff
for confirmation; no broad semantic-search architecture re-review is needed.
