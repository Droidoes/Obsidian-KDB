# Benchmark KPI Enumeration Review - Codex

## Verdict

GO-WITH-CHANGES

The KPI direction is sound enough to continue, but I would not proceed to the anchors/weights spec until the findings below are folded. The two load-bearing issues are: (1) the proposed graph-level dangling-link KPI is not computable from `LINKS_TO` edges alone because unresolved targets are silently skipped by graph ingestion; and (2) `BELONGS_TO coverage` is mostly a deterministic derived projection in schema v2.4, not a clean model-quality KPI.

## Findings

### (a) scored-vs-diagnostic & directionality

[Severity: High] brief §2C row `BELONGS_TO coverage` (`docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:73-81`); `kdb_graph/ingestor.py:488-544`; `ingestion/enrich/pass1_schema.py:73-78`

`BELONGS_TO coverage` is directional in the abstract, but not as implemented today. In schema v2.4, `BELONGS_TO` is mechanically derived from `Source.domain + SUPPORTS`, not emitted per entity by the model. `rederive_domains()` deletes and rebuilds all `Domain` nodes and `BELONGS_TO` edges from source-domain provenance, and Pass-1 requires `domain` for every envelope. That means most active, support-bearing canonical entities will acquire `BELONGS_TO` by construction once the source has a domain.

Why it matters: scoring this can reward a projection invariant rather than model graph quality. If it is near-constant across models, Borda will either add noise or overstate a non-discriminating axis.

Suggested change: demote `BELONGS_TO coverage` to invariant/diagnostic, or redefine it as a Pass-1/domain completeness KPI over sources rather than entities. Do not keep it as one of only two scored graph KPIs unless live multi-model data proves real spread.

### (b) double-counting/redundancy

[Severity: High] brief §2A processing robustness rows (`docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:51-58`); `compiler/compiler.py:289-303`; `compiler/compiler.py:480-491`; `tools/benchmark/scorer.py:384-393`

The scored robustness set counts closely related stages of the same failure ladder: repair-rung usage, retry load, token-overrun rate, quarantine rate, and semantic-pass rate. In Pass-2, token overrun is terminal and therefore also contributes to quarantine. Any final error becomes `final_status="quarantined"`. Semantic failures likewise retry and then quarantine if unresolved.

Why it matters: scoring all of these independently overweights "the pipeline had to fight the model" relative to graph quality. A single bad source can produce multiple correlated penalties.

Suggested change: score one composite `intervention_burden` KPI, or at most score `quarantine_rate` plus one graded `intervention_burden`. Keep retry, token-overrun, repair-rung, and failure-stage split as diagnostic breakdowns.

### (c) kills & the M1 migration

[Severity: Critical] brief §2C row `link-resolution / dangling-link rate` and §3 M1 migration (`docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:73`; `docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:96`); `kdb_graph/ingestor.py:316-337`; `kdb_graph/queries.py:310-319`; `tools/benchmark/scorer.py:221-255`

The proposed M1 migration is not computable from final `LINKS_TO` edges alone. `_replace_outgoing_links()` uses a two-node `MATCH` before `CREATE`, so unresolved targets are silently skipped. `links_to_edges()` then returns only successfully created edges. The denominator, including dangling outgoing targets, has already been lost from the graph.

Why it matters: a graph-only dangling-link rate would report only surviving edges and cannot count failures. It would make a model that emits many unresolved links look cleaner than it is.

Suggested change: keep the signal, but compute it from emitted link intents plus graph/entity resolution: denominator from `compile_result.json`, Pass-2 sidecars, or rendered wiki body wikilinks; numerator by resolving targets against the final active canonical entity set. Describe it as a cross-artifact graph-resolution KPI, not a pure `LINKS_TO` edge KPI.

[Severity: Medium] brief §3 M5 kill rationale (`docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:94`); `compiler/repair.py:242-265`; `kdb_graph/ingestor.py:330-337`; `compiler/validate_source_response.py:115-124`

Killing M5 is reasonable, but the stated rationale is too strong. Body wikilinks are not purely display-only in the current pipeline: `reconcile_body_links()` derives `outgoing_links` from body `[[wikilinks]]`, and graph `LINKS_TO` is then built from `outgoing_links`.

Why it matters: the written rationale contradicts the production data path and may cause later reviewers to miss why body wikilinks still matter for graph construction.

Suggested change: keep M5 killed, but say it is obsolete because declared emit-set coverage is no longer the right quality target and is redundant with graph-resolution/reuse signals. Do not say body wikilinks have no programmatic role.

[Severity: Low] old M2/M3 kill (`docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:92-93`); `compiler/repair.py:268-306`; `compiler/validate_compile_result.py:180-230`

The M2/M3 kill is correct. `concept_slugs` and `article_slugs` are rebuilt from `pages[].page_type`, and the pairing findings are measure-severity/reconcilable. There is no useful graded signal left in the old declared-list Jaccard itself.

Suggested change: keep the kill as written, optionally cite the repair-stage reason.

### (d) graph-set completeness

[Severity: High] brief §4 fork 5 (`docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:111`); `kdb_graph/ingestor.py:347-393`; `kdb_graph/queries.py:155-173`

If `BELONGS_TO coverage` is demoted, the scored graph set is too lean. I do not recommend inventing a third scored KPI immediately, but the current candidate list lacks a watched metric for entity reuse/fragmentation, which is the central graph-quality failure mode after parsing/schema robustness is solved.

Why it matters: two models can produce valid graphs with similar link resolution while one reuses canonical entities and the other emits one-off variants. That is a graph compiler quality difference the current scored set can miss.

Suggested change: add a watched diagnostic for entity reuse / fragmentation, for example the share of canonical non-summary entities supported by multiple sources, or the distribution of `SUPPORTS` per canonical entity. Promote only after multi-model data shows direction and spread. Direction is plausible but not yet safe enough to score without data.

[Severity: Medium] candidate alias/canonicalization quality; `compiler/canonicalize.py:259-296`; `kdb_graph/ingestor.py:549-640`

Alias/canonicalization quality is tempting but should not be scored from current graph state. The canonicalization stage is deterministic and ledger-driven; alias rows are emitted from `canonical_meta.aliases_emitted`, not free model judgment. A model can influence which alias-like slugs appear, but correctness depends heavily on the human alias ledger.

Why it matters: scoring alias counts or `ALIAS_OF` rates risks rewarding ledger coverage or source mix rather than model quality.

Suggested change: keep alias/canonicalization metrics diagnostic only unless a future model-owned alias proposal mechanism exists.

### (e) classification & normalization

[Severity: Medium] brief §2C row `orphan rate` (`docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:75`); `kdb_graph/ingestor.py:649-702`; `orchestrator/kdb_orchestrate.py:195-209`; `tools/cleanup.py:117-161`

The brief defines orphan rate as entities with no incoming/outgoing links, but the code defines orphan candidates as canonical entities with zero `SUPPORTS`. Also, the orchestrator finalize pass detects orphans and then immediately runs cleanup/retraction for reaped orphans. The final graph may not retain the orphan candidates you want to measure.

Why it matters: measuring final graph state could produce a false zero. The current definition also mixes two different concepts: graph isolation vs unsupported/stale derived pages.

Suggested change: define this KPI from finalize artifacts (`orphans_marked`, `reaped`, `retracted_slugs`) and call it unsupported-entity/orphan-cleanup rate. Keep it diagnostic until spread is observed.

[Severity: Medium] brief §4 fork 4 normalization (`docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:109`)

Dangling-link rate should be a ratio, not per-token, if computed as unresolved emitted links over total emitted links. Robustness failures should be token-normalized because source size changes failure impact. Coverage/pass rates should remain ratio pass-through.

Why it matters: per-token dangling links would reward verbose sources/models strangely and obscure the direct quality question: of the links emitted, how many resolve?

Suggested change: use ratio pass-through for dangling-link rate and `BELONGS_TO`-style coverage metrics; token-normalize source/run failures and intervention counts.

### (f) Pass-1 / #108 coupling

[Severity: High] brief §4 fork 1 (`docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md:103`); `ingestion/enrich/enrich.py:132-150`; `ingestion/enrich/enrich.py:193-217`; `ingestion/enrich/replay_archive.py:22-43`; `orchestrator/kdb_orchestrate.py:610-674`

Do not fold all of #108 into the benchmark redesign, but do spec the Pass-1 telemetry contract now. Pass-1 already persists sidecars with raw-response tokens, latency, attempts, parsed envelope, and outcome for success and failure. The orchestrator event log only keeps coarse lifecycle and quarantine events.

Why it matters: if the benchmark consumes ad hoc Pass-1 sidecars directly now, it will bake in a parallel shape to Pass-2 `RespStatsRecord`. If it waits for #108 entirely, the first benchmark version is Pass-2-heavy despite the redesign goal.

Suggested change: define a unified `PassCallMeasurement` schema or adapter contract for Pass-1 and Pass-2. Implement a minimal Pass-1 sidecar reader for the benchmark now, and let #108 add repair-rung fields later without redesigning the KPI layer.

[Severity: Medium] Pass-1 quality signal omission; `ingestion/enrich/pass1_schema.py:73-93`; `compiler/context_loader.py` usage via frontmatter

GT-free Pass-1 quality remains genuinely hard. Signal/noise ratio is correctly diagnostic because "more signal" is not always better. However, Pass-1 has one consumer-facing structural signal: `entity_search_keys` resolution into active graph entities during context loading. It is not a pure quality label, but it measures whether Pass-1 produced usable anchors.

Why it matters: the redesign says the old benchmark was blind to Pass-1, but the scored set still has no Pass-1-specific quality signal beyond robustness.

Suggested change: add a diagnostic `entity_search_key_resolution_rate` for signal sources: emitted keys resolving to active canonical entities over emitted keys. Do not score initially because novel sources may legitimately introduce unresolved concepts.

### (g) blind spots/omissions

[Severity: High] retry/cost telemetry undercounts compile-loop work; `compiler/compiler.py:247-281`; `compiler/compiler.py:405`; `common/llm_telemetry.py:119-138`; `common/llm_telemetry.py:150-184`

Pass-2 `compile_one()` overwrites `state["model_response"]` on each compile-loop attempt and persists only the final response's tokens/latency. `compile_attempts` records the winning attempt, but there is no total tokens/latency across discarded attempts. The SDK-level `attempts` field is separate from the Pass-2 repair/retry loop.

Why it matters: retry load, cost, and latency will undercount models that need a second full Pass-2 call. This is especially important if retry/intervention remains scored.

Suggested change: before scoring retry/cost/latency, add aggregate Pass-2 attempt telemetry: total_compile_calls, total_input_tokens, total_output_tokens, total_latency_ms, and final_attempt_index. Mirror this in Pass-1 measurement shape.

[Severity: Medium] source denominator mismatch across passes; `orchestrator/kdb_orchestrate.py:657-684`

Pass-1 sees all `to_compile` sources; Pass-2 sees only sources gated as signal. Combining robustness across passes is defensible only if the measurement record preserves pass and denominator metadata.

Why it matters: a model that gates many sources as noise can avoid Pass-2 failure exposure. If per-run processing KPIs aggregate blindly, signal/noise decisions can mask compile quality.

Suggested change: keep combined per-run robustness, but require diagnostic breakdowns by pass and denominator: scanned/to_compile, Pass-1 attempted, signal, noise, Pass-2 attempted.

## Bottom Line

The KPI list is close, but not ready for anchors/weights. Fold the data-source fix for dangling-link rate, demote or redefine `BELONGS_TO coverage`, collapse the scored robustness ladder into fewer scored measures, and add watched diagnostics for entity reuse/fragmentation plus Pass-1 key resolution. On the "is the scored graph set too lean at two" fork: yes, it is too lean if one of the two is `BELONGS_TO coverage`; after demoting that, the right move is not to force a weak third scored KPI, but to add graph diagnostics and promote only after the first multi-model run shows real spread.
