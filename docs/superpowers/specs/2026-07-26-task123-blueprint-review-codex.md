# #123 Semantic Graph Search — Blueprint v0.1 Codex Review

**Date:** 2026-07-26  
**Reviewer:** GPT-5.6 / Codex  
**Review packet:** [`2026-07-26-task123-blueprint-v0.1-review-prompt.md`](2026-07-26-task123-blueprint-v0.1-review-prompt.md)  
**Blueprint:** [`2026-07-26-task123-semantic-graph-search-blueprint.md`](2026-07-26-task123-semantic-graph-search-blueprint.md) v0.1  
**Ratified basis:** [`2026-07-25-task123-semantic-graph-search-spec.md`](2026-07-25-task123-semantic-graph-search-spec.md) v0.4 · [`2026-07-25-task123-semantic-graph-search-vision.md`](2026-07-25-task123-semantic-graph-search-vision.md) v1.5

## Verdict: REVISE

The central architecture is sound: `kdb_search/` is the correct consumer-neutral
sibling, caller-side graph materialization preserves `kdb_graph` as a leaf, and
the payload/envelope split is appropriate.

I do not concur with v0.1 unchanged. B14 conflicts with the literal ratified D7
and R4 language. B1, B5, B7, B8, B9, and B11 also miss repository seams that
would break packaging, evidence fidelity, audit completeness, or KPI loading.
These are blueprint corrections, not reasons to reopen the semantic-search
vision.

## Decision-point votes

| Decision | Vote | Disposition |
|---|---|---|
| **B1** package boundary | **REVISE** | Option A is correct; packaging and all planned dependency edges are incomplete. |
| **B3** estimator | **CONCUR-WITH-ITEMS** | The ratified bytes÷4 fallback may remain, but exact candidate counts and a real calibration gate are still missing. |
| **B4** prompt storage | **CONCUR-WITH-ITEMS** | Repo-owned, versioned prompts are correct; add them to package data and an installed-wheel smoke test. |
| **B5** escaping | **REVISE** | JSON would be a spec amendment and need not be adopted, but the proposed delimiter grammar conflicts with both the ratified layout and the measured bytes. |
| **B6** artifact sink | **CONCUR-WITH-ITEMS** | Core-returned payload/caller persistence is correct; empty-space outcomes and persistence failure need one shared audit path. |
| **B7** adapter placement | **REVISE** | Placement is correct; required root, route, and run-order inputs are not wired. |
| **B8** record evolution | **REVISE** | V2 plus a sibling envelope is correct; the actual V1-only loader and `context_failed` continuity are unresolved. |
| **B9** T2Mode retirement | **CONCUR-WITH-ITEMS** | The identity/search boundary is correct; the retirement surface omits a live resolver call in KPI code. |
| **B10** selector route | **CONCUR-WITH-ITEMS** | `models.json`/`ModelSpec` is correct; use selector-role evidence for candidate inclusion/exclusion. |
| **B11** retry composition | **REVISE** | Current retry layers cannot satisfy two logical attempts plus one archived record per attempt. |
| **B12** FTS track | **CONCUR** | Deferral to an independent P5 surface is consistent with v0.4. |
| **B13** refs and hashes | **CONCUR-WITH-ITEMS** | Canonical hashes are appropriate once the body root and exact serialized payload are unambiguous. |
| **B14** gate and edges | **REVISE** | State C ruling concurs; pre-label implementation and thin-empty fat-skip do not conform to v0.4. |

## Verified repository claims

1. **The proposed core can have a `{common}`-only import surface — verified
   architecturally, not yet in code.** `kdb_search` does not exist yet, so no
   implementation import surface can be inspected. The required APIs do exist:
   `common.wiki_io.get_body`, `common.call_model.ModelRequest/ModelResponse`,
   `common.call_model_retry.call_model_with_retry`, and
   `common.model_pool.resolve_models_json`. Putting this code in
   `kdb_graph` would violate its AST-enforced zero-internal-import contract.

2. **The integration-point claim holds.** `compile_source` owns the context
   build in `compiler/compiler.py:700–735`; `_write_context_record` at
   `compiler/compiler.py:640–651` is warn-only. `compiler/context_loader.py`
   contains `T2Mode` at lines 59–68 and the resolver-era T2 machinery in the
   stated region. `compiler/context_record.py` is the strict V1 persistence
   shape that V2 must evolve.

3. **One retirement claim is incomplete.** In addition to the surfaces listed
   by the blueprint, `compiler/kpi/graph.py:120` currently calls
   `queries.resolve_to_canonical_slugs` to compute late-vs-never telemetry.

4. **No local tokenizer — verified.** The active venv contains no importable or
   installed `tiktoken`, `sentencepiece`, or `tokenizers` package.

5. **Fixture identity and restoration claims hold.** Commit `3d271e2` is the
   fixture commit; the tracked fixture contains 163 ordered identities, 163
   excerpts, a manifest, and 165 recorded checksums. The fixture restoration
   test and current package-boundary test pass locally: **16 passed**.

6. **Sizing claims are only partly verified.** Re-rendering the frozen fixture
   reproduces:

   - thin whole graph: **14,343 B**;
   - thin value-investing: **4,404 B**;
   - fat whole graph: **110,121 B**;
   - fat value-investing: **37,664 B**;
   - fat first 150 identities in slug order: **101,102 B**.

   The fat figures use the original spec-shaped rendering with raw,
   unindented excerpt bytes and a two-space-indented closing delimiter. They
   do **not** use B5's proposed indent-every-excerpt-line/column-0-delimiter
   serialization. Also, 101,102 B is the first 150 slugs, not the fixture's
   largest possible 150-entry payload; the largest 150 by rendered entry size
   are **105,489 B**. Finally, 14,343÷163 is about 88.0 B/entity, so the
   corresponding 9,600-entity projection is about **845 kB / 211k bytes÷4
   tokens**, not 835 kB / 209k.

7. **Baseline-suite qualification.** A local full run reached **1962 passed, 1
   skipped, 1 deselected**; one environment-enabled live Deepseek smoke test
   failed on restricted network access. This does not contradict the recorded
   1963-green baseline and is unrelated to the blueprint.

## Findings

### 1. B14 narrows an explicit D7 prohibition

**Severity: load-bearing**

**Repo/spec evidence checked:** Spec §8.1, steps 1–4, says “no
implementation, selector tuning, or vault ingestion crosses the D7 gate until
steps 1–3 are complete.” My v0.3 concurrence response also says the
prohibition on “experiments, tuning, implementation, and vault ingestion” is
clear. Blueprint §11 instead interprets `implementation` as live
selector-exercising work and permits P1–P4 before labels and gates.

**Required fix:** Under ratified v0.4, P1–P4 implementation must wait until the
probe artifact, Joseph's labels, and numerical gates land. The fixture/smoke
step is already complete, so steps 2–3 are the remaining gate.

If Joseph wants canned-only P1/P2/P4 work to proceed earlier, that is a valid
alternative policy, but it requires an explicit spec amendment and
re-ratification; it cannot be introduced as a blueprint interpretation. P3
production integration should remain gated even under that amendment.

### 2. Thin-empty fat-skip contradicts R4

**Severity: load-bearing**

**Repo/spec evidence checked:** Spec R4 says thin then fat “every source, every
run,” with “no small-space skip.” Its budget tests require every under-budget,
non-empty search to call thin then fat. Blueprint §2.2 and B14 skip fat when
`N > M` and the validated thin retention is empty.

**Required fix:** For conformance with current v0.4, execute the fat call over
the empty retained evidence set and require an honest-empty response.

The operationally simpler alternative is an explicit R4 amendment introducing
a distinct terminal state such as `abstain_stage1_empty`. If adopted, it should
not be reported as generic `completed`: it means Stage 1 prevented any body
from being judged, and the truth-set stage-1 recall gate is its compensating
control.

### 3. B1 omits installed-package and planned-consumer contracts

**Severity: load-bearing**

**Repo evidence checked:** `pyproject.toml` package discovery does not include
`kdb_search*`; package data has no `kdb_search` prompt rule; default pytest
testpaths omit `kdb_search/tests`. In
`tools/tests/test_package_boundaries.py`, the new package must be added to
`INTERNAL` as well as `ALLOWED`, or imports of it are silently ignored.
Blueprint B1 names `compiler → kdb_search`, but P4's
`tools/benchmark` harness also needs `tools → kdb_search`; a direct P5 MCP
adapter would need `kdb_mcp → kdb_search`.

**Required fix:** Add these explicit P1 changes:

- package discovery: `kdb_search*`;
- package data: the selector prompt files;
- pytest testpaths: `kdb_search/tests`;
- offline built-wheel prompt-loading smoke test;
- `kdb_search` in boundary-test `INTERNAL`;
- `ALLOWED` edges for each designated consumer, including the P4 harness.

P5 must name which sibling owns graph materialization for CLI/MCP before its
edge is added; it must not place that adapter in `kdb_graph`.

### 4. B5's grammar and its sizing evidence describe different prompts

**Severity: load-bearing**

**Repo evidence checked:** The exact fat sizes in blueprint §7 are reproduced
only by this shape:

```text
- slug: ...
  excerpt: """
<raw excerpt, not line-indented>
  """
```

B5 instead says every excerpt line is prefixed by two spaces and delimiters are
recognized only at column 0. The ratified example places the excerpt field and
closing delimiter inside an entry; the sizing table uses a two-space closing
delimiter. Therefore the closing grammar, “verbatim bytes” claim, golden
rendering, and measured bytes are not yet one design.

**Required fix:** Freeze one formal line grammar before retaining any sizing
numbers. A spec-shaped non-JSON option is:

```text
- slug: ...
  excerpt: """
    <every evidence line>
  """
```

Only the exact two-space closing-marker line terminates the field; evidence
lines are always indented one level deeper. Then golden-test collision cases
and recompute all table rows from that serializer, including the largest
possible M=150 fixture subset.

A JSON evidence array would change the ratified §2.1 wire layout and is
therefore an amendment. I concur with not making that amendment for v1; I do
not concur with the current ambiguous indentation rule.

### 5. B7 has no authoritative body root, selector source, or run ordinal

**Severity: load-bearing**

**Repo evidence checked:** `common.wiki_io.get_body(..., root=None)` defaults
to `OBSIDIAN_VAULT_PATH`/`~/Obsidian`. Production `compile_source` receives an
explicit `vault_root`, and graph storage can also be explicitly selected.
B7 calls `graph_search` without binding the reader to that root, so graph
identities can be paired with bodies from another vault. `compile_source` and
`RunContext` also have no `intra_run_order`, although the envelope requires
it. The pseudocode's `selector_route=…` has no defined source distinct from
the Pass-2 model route.

**Required fix:** Make the adapter inputs explicit:

```text
vault_root
intra_run_order
selector: common.model_pool.ModelSpec
```

Bind `wiki_io.get_body` to `vault_root` when invoking the core, thread the
source ordinal from the orchestrator's deterministic source loop, and define
where the default selector `ModelSpec` is resolved. Tests must use two
different vault roots and prove the selected root supplies the archived
evidence.

### 6. Empty-space short-circuit bypasses the promised audit path

**Severity: load-bearing**

**Repo/spec evidence checked:** The core signature says
`SearchAuditPayload` is always constructed and `graph_search` itself owns the
empty-space result. B7 instead short-circuits `domain_missing` without calling
`graph_search`, but the next steps expect `result.audit` and an envelope.
Spec §3.3 requires the typed abstention to be recorded, while only selector API
spend—not the pure Python core invocation—must be zero.

**Required fix:** Prefer calling `graph_search` with an empty,
reason-stamped `SearchSpaceRef`; it must return without invoking `call`.
Alternatively expose one core-owned empty-result factory used by both paths.
Do not duplicate abstention/audit construction in the compiler adapter.

Also record artifact persistence outcome: on a warn-only envelope-write
failure, the V2 summary must not claim that a nonexistent `artifact_path` was
persisted.

### 7. ContextRecordV2 is not wired through the actual loader

**Severity: load-bearing**

**Repo evidence checked:** `orchestrator/emit_kpis.py:33–39` imports
`ContextRecordV1` and `parse_context_record_v1`; its loader calls that parser
directly. A V2 record currently becomes a `malformed` issue. Updating only
`compiler/kpi/graph.py`, as the blueprint/test disposition emphasizes, would
make all new records disappear before the KPI layer sees them.

Blueprint B8 also mandates `search: null` for every `context_failed` record.
If search completed and the subsequent context builder raised, that discards
the search summary from the per-source audit unit even though the sibling
envelope exists.

**Required fix:** Add a version-dispatching
`parse_context_record` returning `ContextRecordV1 | ContextRecordV2`; update
`ContextLoadResult`, `ContextEvidence`, `orchestrator/emit_kpis.py`, and
`orchestrator/tests/test_context_records.py` for V1, V2, and mixed histories.

Allow `context_failed.search` to be non-null when search completed before the
builder failed. It is null only when search was not requested or no typed
search outcome was produced. Add an integration test for “search succeeds,
context build fails.”

### 8. B9 misses the existing KPI resolver use

**Severity: load-bearing**

**Repo/spec evidence checked:** `compiler/kpi/graph.py:120` performs a
post-run `resolve_to_canonical_slugs` read to split unresolved-at-load keys
into late vs never resolved. B9's removal list does not include this use, yet
spec v0.4 says the deterministic resolver's role drops to zero everywhere and
forbids would-have-recovered telemetry.

**Required fix:** Remove that KPI-time resolver call and explicitly retire or
null the late-vs-never fields for new/recomputed #123 records. Historical
persisted measurements remain historical facts; the V1 parser may remain
without preserving prohibited recomputation behavior. Update the #122
evaluation document, KPI schema/tests, and B9 retirement sweep accordingly.

The proposed retained boundary is otherwise correct:
`kdb_mcp/adapters.py:99` uses the resolver to identify which canonical entity
a tool argument denotes, not to return relevant entities. Intake alias
canonicalization is likewise identity/write-path work. Those
`kdb_graph.queries.resolve_to_canonical_slugs*` APIs may remain.

### 9. B11's retry layers cannot produce the required attempt trace

**Severity: load-bearing**

**Repo evidence checked:** `call_model_with_retry` defaults to **three**
top-level attempts (`MAX_RETRIES + 1`). OpenAI/Anthropic clients inside
`call_model` additionally set SDK `max_retries=2`, so one wrapper attempt may
issue up to three HTTP requests. The wrapper has no attempt observer and
returns only the successful response; failed wrapper attempts cannot become
the spec-required separate `StageRecord`s. Spec §3.4 requires two logical
attempts total and §5.1 requires one archived entry per executed call attempt.

**Required fix:** Define the retry layers precisely:

- exactly two selector-level logical attempts for each ratified retry class;
- one `StageRecord` per selector-level attempt, including failures;
- SDK transport sub-retries identified separately and not misreported as
  selector attempts.

Either extend the common wrapper with `max_attempts=2` plus an attempt sink, or
let `kdb_search` own the two-attempt loop around a single common model call.
Do not stack a second selector-level transport loop over the wrapper's
three-attempt default. Tests must assert both call count and archived records
for transport failure, response failure, and retry success.

### 10. B3 has not discharged spec §7.1's candidate-tokenizer duty

**Severity: load-bearing**

**Repo/spec evidence checked:** The absence of a local tokenizer is true, but
blueprint §7 reports only bytes÷4 and words×1.3 estimates. Spec §7.1 explicitly
routes exact serialized Stage-1/Stage-2 counts with the candidate selector
tokenizer to the blueprint. The proposed test proves bytes÷4 exceeds the older
word heuristic on one fixture; it does not prove bytes÷4 is an upper bound for
either candidate tokenizer. Slugs, hashes, punctuation, and multilingual UTF-8
can exceed one token per four bytes.

**Required fix:** After B5's serializer is frozen and D7 steps 2–3 close, add a
pre-P1 sizing/calibration gate using each candidate's authoritative token
counter over the exact rendered fixture and adversarial high-token-density
cases. Persist the measurements and safety margin.

The ratified bytes÷4 runtime fallback may remain if calibration supports it.
If it does not, changing the fallback is a spec correction that must precede
implementation. Also set `ModelRequest.max_tokens` equal to the 2,000-token
thin output allowance; otherwise the allowance is an expectation, not a
reserved bound.

### 11. B10 excludes a selector candidate using unrelated Pass-2 evidence

**Severity: minor**

**Repo evidence checked:** `deepseek-v4-flash` is active in
`common/models.json`, has a 1M context window, and is substantially cheaper.
Its #120 issue concerns Pass-2 wiki-link emission, while the selector emits a
small closed-world identity JSON shape. That does not establish selector
failure.

**Required fix:** Either include Deepseek in selector-role truth-set screening
or predeclare a selector-specific exclusion probe/gate. Do not treat failure
on another prompt contract as semantic-search evidence. The production
default still waits for D7 results.

Use the existing `common.model_pool.ModelSpec` type in the public signature
rather than introducing an overlapping `SelectorRoute` unless the new type
has a distinct invariant.

### 12. Concordance needs a non-ten-hit denominator

**Severity: minor**

**Repo/spec evidence checked:** Blueprint §2.2 defines
`|fat.top10 ∩ thin.ranked_top20| / 10`. If fat returns two hits and both were
inside thin's top 20, that reports 0.2 rather than full concordance. The spec
describes a fraction of fat's top-ten set, not a fixed ten-result quota.

**Required fix:** Use:

```text
len(fat_top10 ∩ thin_top20) / len(fat_top10)
```

Return null when fat has no validated hits or no fat stage executed.

## Explicit rulings on Kimi's open interpretations

1. **D7:** Under current v0.4, `implementation` means P1–P4 implementation,
   not merely live-selector work. Finish the truth artifact and Joseph's
   labels/gates first, or amend and re-ratify the spec.

2. **State C:** **Concur with no selector call and empty T2.** Explicit
   `entity_search_keys: []` is D-90-8's no-anchors judgment. Searching
   summary/themes anyway would silently replace that policy. A future
   evaluation may propose the alternative explicitly.

3. **Thin-empty with `N > M`:** **Do not concur under R4.** Current v0.4
   requires the fat call. A skip can be adopted only as an explicit,
   distinctly telemetered R4 amendment.

4. **Resolver boundary:** **Concur with retaining identity-resolution and
   intake uses.** They are outside relevance search. Remove the omitted
   compiler KPI relevance/miss-telemetry use.

5. **Escaping:** **JSON would be a §2.1 amendment; rejecting it for v1 is
   reasonable.** Revise the indentation/delimiter grammar and regenerate
   sizing from the actual serializer.

6. **ContextRecordV2:** **Concur with V2 summary plus sibling byte-fidelity
   envelope.** Revise the loader dispatch, mixed-history tests,
   `context_failed` search preservation, and resolver-era KPI retirement
   before ratification.

## Ratification disposition

Revise blueprint v0.1 and return it for a focused concurrence pass. The next
version does not need to revisit the semantic-search architecture. It needs
to:

1. conform B14 to D7/R4 or carry explicit ratified amendments;
2. complete package discovery/data/testpaths and all consumer-boundary edges;
3. freeze one P10-safe serializer and recompute actual/worst-M sizing;
4. wire vault root, selector `ModelSpec`, and source ordinal into B7;
5. make empty-space outcomes use the same core audit path;
6. dispatch V1/V2 in `orchestrator/emit_kpis` and preserve completed search on
   later context failure;
7. remove the omitted KPI resolver use;
8. define two observable selector attempts without hidden wrapper-level
   attempt loss; and
9. add the exact candidate-token sizing/calibration gate.

