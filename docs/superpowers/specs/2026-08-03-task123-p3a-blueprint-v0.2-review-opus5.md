# #123 P3a Blueprint v0.2 — review (Opus 5, 2026-08-03)

Reviewed as an amendment fold: did each accepted finding survive contact with the code it
amends? Every claim below cites the file and line it was checked at.

**Verdict: the fold is substantively right, and three accepted amendments did not land.**

Nineteen of twenty-one dispositions in §11 are correct, and several are better than what was
recommended — A16's warn-and-continue is simpler than codex's typed carrier and achieves the
same guarantee. But **A1, A14 and A15 are nominal acceptances**: the prose says the right
thing, and the mechanism it names does not exist or loses the sub-clause that made it work.
One is a crash, one silently kills a binding measurement ruling, one is a public API change
described as a field addition.

**This does not block ratification** if the owner ratifies with V2-1..V2-3 folded into P3a.0.
It **does block implementation start** on the phases that touch them — P3a.1 (V2-1, V2-2) and
P3a.4 (V2-3). One edit pass away from ready; not a re-review loop.

---

## Blocking before implementation starts

### V2-1 — `Pass15Outcome.t1_slugs` passes an unscoped set the builder must scope. **[§4.1 step 2, §4.3]** *(A1 — my own R-1, half-landed)*

§4.1 step 2 defines the space as
`domain_entity_slugs ∩ active_entities − source_supported_slugs`, and passes the same T1 read
through on `Pass15Outcome.t1_slugs` so the builder does not repeat it.

**The space half is correct.** `source_supported_slugs` carries no active filter — its docstring
is explicit: *"Raw slugs of entities a Source SUPPORTS (no active filter — caller scopes)"*
(`kdb_graph/queries.py:274`). Subtracting an unscoped set from an active-only set is a no-op on
the extras, so the search space is exactly right and `eligible_space_size` keeps its meaning as
claimed.

**The pass-through half is a crash.** Today the builder scopes that read before using it:
`queries.source_supported_slugs(conn, source_id) & active_slugs` (`context_loader.py:315`, via
`:196` where `slug_set = set(active_entities.keys())`). §4.3 replaces that read with the
adapter's value. An entity the source SUPPORTS that has since been retracted or deactivated is
in the raw set, not in `active_entities` — and the projection does an unguarded lookup:
`ent = active_entities[slug]` (`context_loader.py:247`). Any such entity is a `KeyError` in the
prompt-building path.

**Fix: one intersection on the pass-through, not a rework of step 2.** Either the adapter
publishes `t1_slugs` already scoped (`& active`, which it has in hand from the space read), or
§4.3 states that the builder re-scopes what it receives. The former is better — it keeps "single
read" true and puts the scoping where the active set already lives. Add the retracted-SUPPORTS
case to the P3a.1 test list; it is not in §9 today.

### V2-2 — The compact success envelope deletes the numerator of the bytes-per-token series. **[§5.1, §3.1, §4.6, §4.7]** *(A14 — codex 3, sub-clause dropped)*

§5.1's success form persists *"stage/attempt, prompt ref, model stamp, token usage, cost, stop
reason, validation counts, `retained_identities`"* and explicitly drops `rendered_messages`,
`raw_response_text`, `parsed_output`, evidence bodies. §3.1 asserts *"§5.1 now conforms to this
policy."*

It conforms to the logging policy and breaks the ruling directly above it in the same section.
`measured_bytes_per_token` is a **derived property computed from exactly the bytes that were
dropped** (`kdb_search/artifact.py:176-192`):

> *"Derived, never stored: the bytes are already in `rendered_messages`, so persisting the ratio
> too would be a parallel store of something the record computes — and the two could then
> disagree."*

So on the success path — which is the path that produces the series; failures are the minority —
the ratio is not computable from anything v0.2 persists. `provider_input_tokens` survives as
"token usage"; the byte count does not survive anywhere. And `SearchPassMeasurement`'s field list
(§4.7) has no byte count and no ratio either, so the run-time-computed escape hatch does not
carry it. §4.6's `search_bytes_per_token{stage, model}` series has no input.

That takes out §3.1's *"Live bytes-per-token series (2026-08-02, #10)"* — Joseph's ruling closing
Fork C, the reason `ESTIMATOR_BYTES_PER_TOKEN = 4` stopped being provisional, and the thing the
08-02 handoff §2(b) called out as *"without this, every live run measures the real ratio and
throws it away."*

**Fix: `sent_bytes` per stage on the compact receipt.** Bytes are not the ratio, so the
"derived, never stored" rule stays intact — and this is precisely what codex's finding 3
recommended (*"a compact success receipt carrying the hashes, **sent-byte counts**, token usage,
costs, prompt references, and validation totals needed by measurement"*). The sub-clause was
dropped in transcription while the finding was marked Accepted. Carrying it also makes the
compact form self-sufficient for the whole series, so §4.7's "computed at run time, never
re-parsed" stays an optimization rather than a load-bearing dependency.

### V2-3 — `RunMeasurements` does not exist; the "separate channel" is a public signature change. **[§4.7, §6, §9 P3a.4]** *(A15 — codex 4, right call, wrong mechanism)*

§4.7 states: *"the measurement loader bundle (`common/measurement.py`, `RunMeasurements` with
pass1/pass2 lists at `:315`/`:353`, loaders at `:380`/`:394`) gains a separate
`search: list[SearchPassMeasurement]` list."*

`grep -rn "RunMeasurements\b" --include=*.py .` returns **nothing**. There is no bundle type.
The cited lines are a `stats` dict and two local list initializations inside one function, and
`_load_run_measurements` returns `header, pass1 + pass2, stats` (`common/measurement.py:377`) —
a single concatenated list in a tuple.

So "gains a separate list" is not a field addition. It is a **return-type change to two public
loaders**, with existing callers:

- `orchestrator/emit_kpis.py:238` — `_hdr, calls = load_run_measurements(run_dir)`
- `tools/benchmark/pass_boards.py:161` — `header, calls, stats = load_run_measurements_with_stats(run_state)`
- `common/tests/test_measurement.py:708-710` — a test named
  `test_load_run_measurements_wrapper_unchanged_shape`, asserting **"2-tuple, as today."** That is
  a deliberately pinned contract, and the amendment breaks it without saying so.

The decision itself is right and I agree with it: `compute_processing(header, calls)`
(`compiler/kpi/processing.py:13-16`) takes a homogeneous `list[PassCallMeasurement]` and would
either raise or move scored axes on a heterogeneous append. But §4.7 should say what it actually
costs — introduce the bundle type (it would be new, not existing), or return a 4-tuple, and in
either case name the three call sites and the pinned-arity test as part of P3a.4. Right now
P3a.4 reads as additive and is not.

---

## Should-fix before ratification

### V2-4 — "Only pre-search validation errors propagate" contradicts the carried fail-hard posture. **[§4.1 failure channels, §3.1 B7]**

v0.1 propagated `InvalidGraphSearchRequest`, `SearchConfigError`, `ContractViolation`, **and any
unexpected exception**. v0.2's failure-channel paragraph reduces that to: *"Only pre-search
validation errors (`InvalidGraphSearchRequest`, `SearchConfigError`) propagate."*

`ContractViolation` and the catch-all are gone. Read literally, an unexpected exception anywhere
post-search is now swallowed by warn-and-continue — which contradicts §3.1's B7 bullet, carried
unchanged in the same document (*"adapter defect ⇒ existing `context_failed` channel"*), and the
fail-hard posture the core is built on (`search.py:196-198`, Joseph's #121 ruling).

The intent is clearly narrower — steps 7 and 8 specifically. Say that: warn-and-continue applies
to **named exceptions from the envelope write and the provenance read** (`OSError` on the atomic
write; whatever `entity_first_run_ids` can raise), and everything else propagates as before.
Otherwise A16 quietly converts a fail-hard boundary into a fail-soft one, which is a bigger
change than the finding it answers.

### V2-5 — `stage2_budget_bound` is persisted but never aggregated, which was the point. **[§4.5, §4.6]** *(A7)*

§4.5 adds `stage2_budget_bound` to the V2 search section, correctly citing it as *"the 0/N
evidence required to ever delete the fail-safe on evidence rather than argument."* Two sentences
later the same bullet closes: *"retained, not aggregated … **No new KPI series.**"*

As written, the closing sentence covers the field just added. A value that lands in per-source
JSON and is never aggregated across a run cannot show you 0/N — you would be re-deriving it by
hand from 1,586 files, which is the situation that made the byte-ceiling and word-cap deletions
take a session of measurement rather than a KPI read.

Either scope "no new KPI series" to the rest of the sweep and add one series
(`search_stage2_budget_bound_rate`), or accept that A7 is a storage change rather than an
evidence change and say so. The former costs one line in §4.6 and is the whole reason the
finding was accepted.

### V2-6 — P3a.2 now carries most of the task. **[§8]** *(A13 consequence)*

Folding V2 serialization forward (correct — codex 2 is right that the old order had no green
gate) leaves P3a.2 holding: V2 types + factory + parser + writer, `KeyOutcomeV1`,
`compile_source` and orchestrator plumbing, the run-level selector seat, `--max-tokens`
validation, the full `context_loader` rewiring, and every §7 deletion. Its gate is
correspondingly compound.

Not a defect — the dependencies are real. But it is now the single phase where a failure is
hardest to localize, and the intra-phase ordering the gate already implies ("V2
factory/parser/writer tests green **before** the wiring lands") is really two checkpoints. Make
them **P3a.2a — V2 record types + factory + parser + writer, unwired** and **P3a.2b — wiring +
deletions**, and the gate language you already wrote becomes a phase boundary you can stop at.

### Noted, not blocking — A21's rejection of `provider_output_tokens`

The rejection is defensible and I withdraw the objection I would otherwise have raised:
`BudgetRecord.budget_side: "output"` with `finish_reason_normalized` (`result.py:60-63`) already
makes output-side truncation observable, so nothing is undetectable. What is lost is only the
*distribution* — how close the selector ever came to the 64K cap that R-P3a-6 and A18 introduce —
and that is speculative demand. YAGNI stands. Worth one sentence in §11/A21 acknowledging that
BudgetRecord is what makes the rejection safe, since that is the actual load-bearing reason
rather than the absence of a consumer.

---

## Verified correct in the fold — checked, no change needed

- **A2** (seven-series retirement, one rename / one re-baseline / three clean cuts) — matches
  `compiler/kpi/graph.py:131,146-153,162,171-178`; all seven confirmed outside `GRAPH_WEIGHTS`
  (`compiler/kpi/score.py:68-73`). The per-key → per-hit denominator change is stated as a
  re-baseline, which was the point. ✔
- **A3** (`context_explicit_empty_count` re-sourced to `query_kind == "state_c"` over
  search-ran records) — correct, and the population change is stated rather than buried. ✔
- **A4** (sort key `(-tier, rank_index, -pagerank, slug)`) — works. `-tier` dominates, so the
  constant chosen for T1/T3 is immaterial and PageRank ordering within those tiers is preserved
  exactly as `context_loader.py:240` does today. Naming fat-stage rank explicitly was the right
  call — thin is membership-only (`search.py:44-52`). ✔
- **A5** (`source_text` deleted) — the six cited call sites are exactly the deleted regex family;
  `active_entities` correctly retained for the projection. ✔
- **A6** (`unresolved_expressions` as unresolved authority, `Hit.matched_expressions` as
  attribution, partition invariant asserted in P3a.1) — exactly right. ✔
- **A8** (V1 read-only, factory retired, parser kept) — `build_context_record_v1` does read
  `telemetry.max_hops` (`context_record.py:160`), and its only non-test callers are
  `compiler.py:709,732`. ✔
- **A9** (`keys_emitted` falls back to `frontmatter.entity_search_keys`) — restores the exact V1
  guarantee at `compiler.py:717-719`. ✔
- **A10** (abstention produces a populated record, not a null search section) — the better
  reading of the two, and consistent with `build_audit_payload`'s stated rationale that zero-call
  outcomes still produce a record *"their emptiness is the finding"* (`artifact.py:344-347`). ✔
- **A13** (V2 serialization before/within wiring, no compat shim) — the ordering defect codex
  found is real and this resolves it. See V2-6 for the size consequence only. ✔
- **A16** (warn-and-continue instead of a typed carrier; summary built immediately after
  `graph_search` returns) — simpler than the recommendation and achieves the guarantee
  structurally. See V2-4 for the scoping wording only. ✔
- **A17** (`searches_attempted` + `searches_written`) — correct; a failed write genuinely leaves
  no artifact to read a null path from, so the two-counter form is the only one that works. ✔
- **A18** (run-level `ModelSpec` resolved once, fail before the source loop, `--max-tokens ≤
  selector.max_output_tokens` at run start) — correctly separates capability metadata from the
  behavioral cap, which was the substance of codex 7. ✔
- **A19** (`KeyOutcomeV1` persistence-local, V2 outcome type distinct) — right, and the
  "cannot mix accidentally" framing is worth keeping in the test name. ✔
- **A11, A12** (P3a.0 cost projection; split sandbox gate) — folded as intended. ✔
- **§12 OQ resolutions** — all four sound. OQ-3's addition is an improvement on both reviews:
  codex was right that "same-domain-gated exactly as today" hid the absent-domain whole-graph
  fallback (`context_loader.py:193`), and stating it beats inheriting it.

---

## The pattern worth naming

§11 marks nineteen of twenty-one findings "Accepted." Three of those acceptances — A1, A14, A15 —
fail in the **same way**: the prose is right, and the mechanism it names either does not exist
(`RunMeasurements`), drops the sub-clause that made it work (codex's "sent-byte counts"), or
carries a value that needs a scoping the source doesn't apply (`source_supported_slugs`). None
would be caught by re-reading the blueprint; all three take one grep.

For v0.3, the cheapest fix is a discipline the document already demonstrates: **every new
mechanism cites a `file:line`.** v0.2 does this well when it inherits (`context_loader.py:202`,
`result.py:136`, `score.py:68-73`, `artifact.py:368-379` are all correct) and stops doing it at
exactly the points where it invents. A type name, a field, or a function introduced without a
citation is either new — say so — or assumed to exist, and that assumption is where all three
blocking findings live.

## Recommendation

Fold V2-1, V2-2 and V2-3 into v0.3 — each is a paragraph, none reopens a decision. V2-4 and V2-5
are one sentence each; V2-6 is a table edit. Then ratify. The architecture has been stable across
two review rounds and both panels converged on structure; what is left is bookkeeping against the
code, not deliberation. If the owner prefers to ratify v0.2 now and carry the five as P3a.0
line items, that is defensible — but V2-1 and V2-2 must land before P3a.1 writes the adapter,
and V2-3 before P3a.4 touches the loader.
