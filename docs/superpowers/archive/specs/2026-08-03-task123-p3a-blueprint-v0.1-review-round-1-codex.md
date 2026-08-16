# #123 P3a Blueprint v0.1 — Codex Review, Round 1

Date: 2026-08-03  
Reviewer: Codex  
Artifact reviewed: `2026-08-03-task123-p3a-blueprint-v0.1.md`

## Disposition

**REVISE.** The architecture is directionally sound, but several contracts cannot yet be implemented as written.

## Findings

### 1. High — Measurement requires output-token data that `StageRecord` does not retain

The blueprint says `total_output_tokens` and per-stage token splits are summed from `StageRecord`s. The current record stores only `provider_input_tokens`; provider output tokens are discarded after cost calculation.

Add `provider_output_tokens` before persistence begins and bump the artifact schema version. Define how missing provider usage is represented rather than silently projecting it as zero.

### 2. High — The implementation phase order cannot maintain a green suite

P3a.2 deletes the V1 telemetry vocabulary and rewires `compile_source`, while P3a.3 introduces V2 serialization. At the P3a.2 gate, the rewired builder would have no valid context-record serialization path.

Introduce the V2 record types, factory, parser, and writer before or within the wiring phase. P3a.3 can then be limited to dispatching loaders and KPI consumers. Avoid a temporary V1 compatibility shim that would be added only to be deleted in the next phase.

### 3. High — Envelope persistence contradicts the binding logging policy

Section 3.1 says full bytes are retained only on failure, but §5.1 writes `SearchRunEnvelope{audit: SearchAuditPayload, ...}` for every search. `SearchAuditPayload` contains every rendered request, raw response, parsed output, and evidence body. That is the full ~80 kB receipt whose success retention the policy rejects.

Define a compact success receipt carrying the hashes, sent-byte counts, token usage, costs, prompt references, and validation totals needed by measurement. Preserve rendered messages, raw output, parsed output, and evidence only for failures. Alternatively, explicitly amend the logging policy and accept the documented storage cost.

### 4. High — `SearchPassMeasurement` needs a separate consumer channel

The existing measurement loader returns one homogeneous `list[PassCallMeasurement]`. `compute_processing` includes every list item in scored denominators and expects Pass-1/Pass-2-specific fields such as `final_status`, `syntax_repaired`, `schema_ok`, and `semantic_ok`.

Appending the proposed distinct dataclass would either raise at runtime or move the scored axes, violating the non-movement contract. Return a structured bundle or a separate search-measurement list. Feed only Pass-1 and Pass-2 measurements to `compute_processing`; feed search measurements to their dedicated diagnostic aggregation.

This supports the new-dataclass choice in OQ-P3a-2, but not a heterogeneous replacement for the current loader result.

### 5. High — Post-search failures cannot preserve `context_failed.search`

The adapter performs envelope persistence and the provenance read after `graph_search`, then returns `Pass15Outcome`. If `entity_first_run_ids` or summary projection raises, the adapter never returns an outcome. `compile_source` receives only the exception and cannot recover the completed search summary required by `context_failed.search`.

Define a typed post-search exception carrying partial search evidence, or introduce an explicit result carrier that separates the completed core search from subsequent adapter enrichment. Build the partial summary immediately after `graph_search`, before failure-sensitive post-processing.

### 6. Medium — Warn-only envelope-write failure accounting is not observable as described

A failed envelope write leaves no envelope from which a null `artifact_path` can later be read. Therefore, a read-time failure count cannot be derived from null paths in the missing artifacts.

Retain independent `searches_attempted` and `searches_written` counters in the run header. Derive write failures from their difference, and reconcile the envelope glob against `searches_written`. The context V2 summary may still carry `artifact_path: null` for source-level evidence.

### 7. Medium — Model plumbing and the 64K output policy are incomplete

The CLI resolves a `ModelSpec`, but the current `run()` boundary receives only raw provider/model/routing fields. Re-resolving from the raw SDK model name is not a stable model-pool identity and conflicts with the ad-hoc provider escape hatch.

Add an explicit run-level selector `ModelSpec` parameter and thread that object to every source. Fail before entering the source loop when no valid selector seat exists.

Also, lowering `common/models.json.max_output_tokens` does not itself constrain Pass-2: Pass-2 uses the existing `--max-tokens` value directly. If 65,536 is a behavioral run cap rather than capability metadata, validate `--max-tokens <= selector.max_output_tokens` before execution. Pass-1 is already fixed at 4,096, and selector calls are internally bounded below 65,536.

### 8. Medium — Deleting shared `KeyOutcome` leaves V1 records without a representation type

The deletion plan removes `common.types.KeyOutcome` while promising that V1 historical records remain readable. Keeping only V1 literal sets in the parser is insufficient: `ContextRecordV1.key_outcomes` and `_parse_outcome` still need a concrete return type.

Introduce a persistence-local `KeyOutcomeV1` in `compiler/context_record.py`. Keep the V2 outcome type distinct so the historical and current vocabularies cannot be mixed accidentally.

## Open-question recommendations

1. **OQ-P3a-1 — Drop V2 `max_hops`.** No production context-record consumer currently reads it. V1 retains the historical field through its own parser.
2. **OQ-P3a-2 — Use the new dataclass, returned separately.** A distinct type correctly models the two-prompt search, provided it is not appended blindly to the existing pass-call list.
3. **OQ-P3a-3 — Keep the same-domain T3 gate, but settle absent-domain behavior explicitly.** The current loader uses the whole active graph when no domain is available, so “same-domain-gated exactly as today” hides an important exception. If D3 remains hard, an absent domain should produce an empty T3 pool; otherwise the whole-graph fallback needs explicit ratification.
4. **OQ-P3a-4 — Prefer a clean cut with a documented re-baseline.** A payload tombstone adds a field with no runtime consumer and risks becoming permanent schema debris.

## Recommended disposition

Revise the blueprint before ratification. The minimum closure set is:

- retain provider output-token usage in the artifact producer;
- move V2 record serialization ahead of the wiring/deletion gate;
- reconcile success-envelope persistence with the logging policy;
- separate search measurements from the scored Pass-1/Pass-2 list;
- define a post-search failure carrier;
- make envelope-write failures independently countable;
- thread the resolved selector spec through the run boundary; and
- preserve V1 outcomes with a persistence-local historical type.
