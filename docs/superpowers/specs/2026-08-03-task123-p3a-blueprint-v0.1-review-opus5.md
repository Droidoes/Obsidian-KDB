# #123 P3a Blueprint v0.1 — review (Opus 5, 2026-08-03)

Reviewed against the code, not against the document's own terms. Every claim below cites the
file and line it was checked at. Findings are ordered by severity and each names the section
it amends, so they fold into v0.2 mechanically.

**Verdict: sound architecture, ready for v0.2 after four amendments.** The decomposition is
right — adapter owns materialization and persistence, the core stays I/O-free, the record
schema versions rather than mutates, the deletion is scoped to one module. The rulings are
carried faithfully. What v0.1 is missing is not structure; it is four places where a stated
mechanism does not survive contact with the code it will replace. One of those costs money
per source at vault scale. Three of them will produce a silently wrong implementation if
P3a.1 starts before they are amended.

---

## Blocking — amend before P3a.1 opens

### R-1 — The adapter's search space does not exclude T1; the builder's T2 does. **[§4.1 step 2, §4.3, §4.5]**

§4.1 step 2 builds the space as `domain_entity_slugs(conn, domain) ∩ active_entities(conn)`.
§4.3 then defines `T2 = t2_selection ∩ (active same-domain pool − T1)`.

Today those are the same operation, done once, before matching: `context_loader.py:202`
passes `candidate_slugs=pool - t1_slugs` into `_build_t2`. T1 is excluded *before* anything
looks at a candidate.

After P3a the exclusion moves to *after* the selector has run. A hit that lands on an entity
the source already SUPPORTS therefore costs a fat-stage body read, occupies one of
`max_results`, displaces a hit that would have survived — and is then silently dropped by the
builder. That is a regression introduced by P3a's space construction, not a pre-existing
condition.

It is also unobservable as specified. §4.5 retires the #122 disposition vocabulary in favor of
`matched | unresolved`, and neither value can express *"matched an entity you already had."*
The V1 record had `resolved_already_t1` (`context_loader.py:119`) for exactly this.

Both halves are one fix, and it is a decision rather than a redesign:

- **(a)** subtract `queries.source_supported_slugs(conn, source_id)` in the adapter's step 2 —
  the T1 read moves earlier or is shared with the builder; or
- **(b)** accept the overlap deliberately and add a counted watched class (`hit_already_t1`)
  so the waste is a measured series rather than an invisible one.

(a) is cheaper and matches today's semantics. (b) is defensible only if you want the selector
judged on the full domain rather than on a source-conditioned subset — in which case say so,
because it changes what `eligible_space_size` means as a trend series (SD-5).

### R-2 — The KPI retirement list is materially incomplete. **[§4.6, §7 row 5, OQ-P3a-4]**

§4.6 removes two series (`search_key_late_resolution_rate`, `search_key_never_resolved_rate`)
and §7 carries the same two. But the entire `search_key_*` family is built on the #122
disposition vocabulary and the `target_first_run_id` stamp that §4.5 retires:

| Series | Reads | `compiler/kpi/graph.py` |
|---|---|---|
| `search_key_resolved_at_load_rate` | `disposition != "unresolved"` | 131, 171 |
| `search_key_late_resolution_rate` | the KPI-time resolver read | 141, 172 |
| `search_key_never_resolved_rate` | arithmetic on that same read | 142, 173 |
| `search_key_resolved_pre_run_rate` | `o.target_first_run_id` | 150, 174 |
| `search_key_resolved_cohort_rate` | `o.target_first_run_id` | 151, 175 |
| `search_key_resolved_age_unknown_rate` | `o.target_first_run_id` | 148, 176 |
| `search_key_t2_seed_rate` | `disposition == "resolved_t2_seed"` | 162, 178 |

Seven series, not two. Five of them have no disposition in v0.1 at all. `search_key_t2_seed_rate`
reads a disposition that will no longer exist, so it is not merely unspecified — it is a
`KeyError` waiting for P3a.3.

Three of them also **overlap the new series** and the blueprint should say which replaces which,
because the denominators differ:

- `search_key_resolved_at_load_rate` ≈ §4.6's new `search_expression_matched_rate` — same
  population, rename.
- `search_key_resolved_{pre_run,cohort,age_unknown}_rate` are **per-key**;
  §4.6's new `search_hit_recency_*_rate` are **per-hit**. Not a rename — a denominator change.
  If that is intentional (and it should be: a hit is the thing with provenance), state it as a
  re-baseline, or the series looks continuous across P3a and is not.

None of the seven is in `GRAPH_WEIGHTS` — verified `compiler/kpi/score.py:68-73`, which holds
`graph_connectivity / link_density / supports_density / entity_reuse` only. The blueprint's
"watched-series re-baseline, not a board change" claim is **correct**, and holds for all seven.

### R-3 — `context_explicit_empty_count` cannot "read from the same fields." **[§4.6]**

§4.6 states the V2 path reads `context_build_success_rate`, `context_explicit_empty_count`
and the tier means "from the same fields."

That is true of four of the six. It is false of `context_explicit_empty_count`, which derives
from `r.effective_t2_strategy == "explicit_empty"` (`compiler/kpi/graph.py:181-183`) — a field
§4.5 explicitly drops from V2.

The successor exists (`query_kind == "state_c"` in the V2 search section) and the semantics
match, so this is a re-sourcing, not a lost metric. But it needs stating, because it carries a
population change v0.1 does not mention: `query_kind` lives in the `search` section, which is
`null` when no search ran. On V1 every complete record could answer "was this State C?"; on V2
a pre-Pass-1 source cannot. Define the V2 count as *over records where a search ran*, or the
figure silently changes meaning the first time a pre-Pass-1 source appears.

### R-4 — The T2 ordering rule is asserted but never written down. **[§4.3]**

§4.3 says selector order is "preserved," that "selector rank feeds the within-tier ordering
ahead of the PageRank tie-break," and that "SD-2's strict tier ordering and the page cap are
unchanged."

Today that ordering is a single sort key over a flat list: `scored.sort(key=lambda x: (-x[1],
-x[2], x[0]))` — tier desc, PageRank desc, slug asc (`context_loader.py:240`), and `selected_slugs
= scored[:page_cap]` (241). T1, T2 and T3 all pass through it.

Preserving selector rank *inside* T2 while T1 and T3 keep PageRank requires a heterogeneous
sort key, and v0.1 never writes it. This is the single line that decides which pages reach the
prompt under the cap, so it should be spelled out — e.g. `(-tier, rank_index, -pagerank, slug)`
where `rank_index` is the selector position for T2 members and a constant for T1/T3.

Two consequences worth ratifying rather than inheriting:

- Under a binding `page_cap`, **selector rank now decides which T2 pages survive**, where
  PageRank decided before. That is the intended improvement, but it is a behavior change to the
  prompt-facing product and belongs in §3 as a ruling, not as a clause in a parameter list.
- `Hit` order is fat's ranked order (concordance is defined as "fat top-10 ∩ thin top-20",
  `result.py:100-102`), so "selector order" is well-defined. Say which stage's rank it is — a
  reader can reasonably guess thin's, which is membership-only (`search.py:44-52`).

---

## Should-fix before ratification

### R-5 — `source_text` becomes a dead parameter. **[§4.3, §7]**

`build_context_snapshot(source_text=...)` is consumed **only** by the regex family —
`_t2_slug_in_text`, `_t2_title_in_text`, `_t2_legacy`, and the dispatchers that thread it
(`context_loader.py:318, 345, 468, 495, 522, 545`). Delete §7's list and nothing reads it; the
`re` import goes with it.

`compile_source` still passes `source_text=body` (`compiler.py:703`). §4.3's change list names
`mode` and `resolver` as the removed params and does not mention `source_text`. Add it — this
is the same "computed, read nowhere" class as `unresolved` and `small_space`, deleted last
session on exactly this test.

(`active_entities` stays — the projection still reads `title` / `page_type`,
`context_loader.py:247-255`.)

### R-6 — Expression accounting has two candidate authorities. **[§4.5]**

§4.5 derives `key_outcomes` from hit-level facts: *"the highest-ranked validated hit attributed
to that expression."*

But `GraphSearchResult.unresolved_expressions` (`result.py:136`) is already the controller's
authority for the unresolved set, and `Hit.matched_expressions` (`types.py:133`) is the
authority for matched-plus-attribution. The invariant is that the two together partition
`query.expressions`.

Deriving `unresolved` a second time from the absence of a hit is not equivalent: an expression
that appears in neither is **silently lost rather than counted**. Name `unresolved_expressions`
as the authority and `matched_expressions` as the attribution source, and assert the partition
in the P3a.1 tests. `SearchTelemetry`'s own docstring makes this argument for `status` /
`execution` (`result.py:70-73`) — *"a second copy can disagree with the first"* — and the same
reasoning applies here.

### R-7 — Telemetry that exists is never aggregated, so no later deletion can be evidence-based. **[§4.5, §4.6]**

The envelope retains full `StageRecord`s, so nothing is *lost*. The gap is that §4.5's V2
search-section list and §4.6's series list both omit these, so nothing ever aggregates them —
and an un-aggregated field cannot retire a mechanism.

- **`stage2_budget_bound`** (`result.py:80-86`) — its own docstring: *"Expected to be permanently
  false at current corpus density … this is the flag that says whether the fail-safe has ever
  engaged."* That is precisely the 0/N measurement that justified deleting three mechanisms this
  session. Persist it or the fail-safe can never be deleted on evidence, only on argument.
- **`all_entries_dropped_occurrences`** (`result.py:94`) — a validation-collapse counter with no
  successor in the V2 list.
- Completeness sweep: `query_truncated_occurrences`, `attempted_violations`, `stage2_hydrated` /
  `stage2_title_only` (the last two are partly covered by `body_coverage`, so a deliberate
  "covered, not persisted" note is a fine disposition).

### R-8 — Dropping `max_hops` from `ContextTelemetry` retires the V1 *writer*. **[§4.5, §7 row 4]** *(answers OQ-P3a-1)*

Full grep run. Within the context-tiering sense of the name — the `max_hops` in
`kdb_graph.queries.shortest_path`, `kdb_graph/cli.py`, `kdb_mcp/{server,adapters}.py` is
unrelated path-finding — the consumers are:

- `common/types.py:379` — `ContextTelemetry.max_hops`
- `compiler/context_record.py:65, 141-144, 160, 183, 292-331` — V1 schema, the complete-status
  non-null invariant, the factory, and the parser
- `compiler/context_loader.py:182, 211-214, 287`
- **No KPI series reads it** — `grep -c max_hops compiler/kpi/graph.py` → 0. Tests only otherwise.

So: **no consumer was missed, and dropping it from V2 is safe.** One coupling v0.1 does not
state, though. `build_context_record_v1` reads `telemetry.max_hops` (`context_record.py:160`);
if `ContextTelemetry` loses the field, the V1 factory stops compiling. Its only non-test callers
are `compiler.py:709, 732`, both of which switch to V2 — so the correct disposition is
**V1 goes read-only: parser retained for historical reads, factory retired.** §7 should carry
that as its own row; it currently implies V1 survives whole.

### R-9 — The pre-search `context_failed` path has no `keys_emitted` source. **[§4.5]**

Today `ContextFailureInput.keys_emitted` is derived pre-graph-read from frontmatter
(`compiler.py:717-719`) precisely so it survives a builder that never ran. §4.5 re-sources
`keys_emitted` to *"the original pre-truncation expressions from the adapter."*

§4.1 says `InvalidGraphSearchRequest` / `SearchConfigError` **propagate** into `context_failed`.
On that path there is no adapter output. State the fallback — `frontmatter.entity_search_keys`
when the adapter produced nothing — or V2 failure records lose a field V1 guaranteed.

### R-10 — The empty-graph early return is unspecified under V2. **[§4.3]**

`context_loader.py:160-185` returns before any tiering, hardcoding `max_hops=2`,
`cold_start=True`, and every emitted key `unresolved`. Under V2 that path needs: `max_hops`
gone, the new `matched | unresolved` vocabulary, and a decision on whether `search` is null
(no search ran) or populated (the adapter searched an empty space and the core abstained —
which is what actually happens, per §4.1 step 3). The latter is right and worth stating: an
abstention on an empty space is a *result*, and its record should show it.

### R-11 — No pre-run cost projection. **[§4.7, R-P3a-5]**

REPLACE means every source now carries two additional LLM calls. At 1,586 notes that is a new
recurring operational cost, and R-P3a-5 leaves the seat open between two candidates roughly 4×
apart on price. §4.7 delivers `cost_usd_pass1_5` *after* the run.

Every input already exists and none of it needs a paid call:

- thin input bytes ≈ eligible space size × identity-line length — bounded by
  `M × MAX_SLUG_LEN` (§3.1's 18,464 B at M=150)
- fat input bytes ≈ stage-2 pool × mean body size — measure the body-size distribution over
  the 163 active entities in the current vault (`common/wiki_io.get_body` over
  `queries.active_entities`), which is the same read the adapter's `body_reader` will do
- space sizes per domain — the projected column in the 08-02 handoff §3
- bytes→tokens — D5's four measured families (§3.1), and the run's own seat model is in there
- pricing — `common/models.json` for both candidates

**Disposition: this is P3a.0 work, not v0.2 prose.** One table (thin input, fat input, output
allowance, × per-M pricing, × 1,586) alongside the registry edit, before the seat is chosen —
it turns R-P3a-5's two candidates into a measured call rather than a default, and sizes the
vault ingest before it is scheduled. No numbers are estimated here on purpose; they should come
from the corpus, not from a reviewer.

### R-12 — Split the sandbox gate's two firsts. **[§8, §10]**

§8's gate row fuses **prompt 1.3.0's first-ever live fire** with **Pass-1.5's first-ever live
fire** into one criterion (*"run completes; KPI/board/envelope inspection"*). §10 handles the
risk as a watch-for — *"inspect the emitted keys before trusting the search results built on
them"* — which is the right instinct, but a watch-for is not a gate.

Make it an explicit sub-checkpoint in the gate row: **Pass-1 output inspected and accepted
before Pass-1.5 results are read.** If 1.3.0's `entity_search_keys` come back wrong, every
downstream selector judgment is being read through a broken query and the run tells you nothing
about the selector. Costs one pause, removes one confound.

---

## Verified correct — checked, no change needed

Recorded so the panel does not re-derive them:

- `SearchRunEnvelope` shape already declared and unused — `kdb_search/artifact.py:368-379`. ✔
- `GraphSearchResult.audit` delivered as the 8th field (D-123-H) — `result.py:155`. ✔
- Retiring series are **not** in `GRAPH_WEIGHTS` — `compiler/kpi/score.py:68-73`. ✔ (holds for
  all seven of R-2, not only the two named)
- `emit_kpis.py:296`'s `copytree(run_dir, …)` auto-packages `search/` with zero changes —
  confirmed, and the comment above it lists the dirs it did not anticipate. ✔
- `search.py:200-201`'s docstring is stale: `get_body` lives at `common/wiki_io.py:39`, not in
  `kdb_graph`. ✔ P3a.0's fix is correct.
- `page_type` vocabulary belongs at the materializer — `projection.py:125-128` assigns it there
  in prose. ✔ Assigning it to the adapter discharges #128 exactly as written.
- `Hit.matched_expressions` is controller-resolved, so D-123-F taking the model's advisory
  `unresolved` off the wire does **not** threaten expression accounting — `types.py:124-133`. ✔
- `models.json`: `deepseek-v4-flash` 384,000 and `qwen3.7-flash` 128,000 `max_output_tokens`,
  both `ctx_window` 1,000,000, both `tokens_lte_bytes: true`. ✔ §4.8 is accurate.
- `compile_source`'s step-1 try and the `context_failed` channel — `compiler.py:700-728`. ✔
- `SearchOpts.evidence_excerpt` (`types.py:99`) is still the orphan the 08-02 handoff flagged.
  Correctly left alone — not P3a's to clean.

**One inaccuracy, in P3a's favor:** §7 lists "orchestrator call site" as losing `mode` /
`resolver`. There is nothing to remove — `kdb_orchestrate.py:711` never passed them, and the
env vars that once selected them are documented dead at `context_loader.py:7-9`. The useful
reading is stronger than the correction: **LAYERED and LEGACY have never had a production
caller.** That de-risks §7 considerably and is independent support for R-P3a-2.

---

## The open questions

**OQ-P3a-1 — drop `max_hops`?** Yes. No consumer missed; no KPI reads it. See R-8 for the one
coupling that needs a §7 row (V1 goes read-only).

**OQ-P3a-2 — new `SearchPassMeasurement` type?** Confirmed, for the reason given plus one more.
`prompt_versions: {thin, fat}` genuinely does not fit `PassCallMeasurement`'s single field, and
one-measurement-per-search is the right grain — but the stronger argument is that a third type
leaves the pass1/pass2 projections untouched, so the D-117-5 completeness contract keeps its
existing meaning on the two columns that already work. Widening the shared type would put every
existing measurement at risk to serve the new one.

**OQ-P3a-3 — T3 stays same-domain-gated?** Yes, and it is already true rather than a change:
`_t3_neighbors` receives `pool - seeds` where `pool` is the domain pool (`context_loader.py:193,
214`). Nothing in P3a touches it. Worth keeping stated, since T2's provenance changes and a
reader may assume the gate moved with it.

**OQ-P3a-4 — tombstone the deleted series or clean cut?** Not answerable as posed. It asks about
two series; seven are affected (R-2). Settle the full retirement list first, then the call is
easy and mostly falls out of it: the three with successors (`resolved_at_load` →
`expression_matched`, and the two recency families) want a one-release tombstone *because the
denominator changes* and a silent swap makes the series look continuous when it is not; the four
with no successor want a clean cut plus the docs re-baseline note.

---

## Recommendation

Fold R-1 through R-4 into v0.2 before P3a.1 opens — R-1 costs body reads per source at vault
scale, and R-2/R-3/R-4 each produce an implementation that compiles, passes its own tests, and
is wrong. R-5 through R-12 are v0.2 edits that need no re-deliberation. Then send v0.2 to the
external panel per project default; the architecture is stable enough that panel effort is
better spent on it than on v0.1.
