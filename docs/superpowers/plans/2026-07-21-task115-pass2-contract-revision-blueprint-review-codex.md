# Task #115 — Pass-2 contract revision blueprint v1.0: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-revision-blueprint.md` v1.0  
**Architecture basis:** Task #115 decisions v1.5 (`D-115-1..15`)  
**Repository anchor reviewed:** `main` at `8af7139`  
**Verdict:** Revise before Proceed

## Executive assessment

The blueprint is directionally strong and absorbs nearly all of the v1.5 integration
decisions. Its phase split is understandable, prompt packaging is treated as a real
deployment concern, historical aggregate compatibility is preserved, and the graph
derivation/confidence choices match the ratified architecture.

It is not implementation-ready yet. Four contradictions would otherwise produce a
contract that either cannot pass its own gates or silently preserves the field the
task is intended to remove:

1. Phase 1 reconstructs `outgoing_links` inside serializable `PageIntent` objects.
2. The summary validator removes the runtime value it needs to validate the summary
   slug.
3. the post-canonicalization gate says one summary across the batch rather than one
   per compiled source; and
4. the hard two-commit sequencing statement conflicts with three later commit gates.

There are also important missing cascades in aggregate validation, fixture migration,
orchestrator combination, confidence deprecation, and snapshot versioning. These can
be resolved with a focused v1.1; the ratified D-115 decisions do not need reopening.

## What is already solid

- Phase 0 correctly separates provenance from behavioral prompt edits.
- The installed-wheel prompt test closes the editable-install blind spot.
- The target response schema exactly matches the ratified wiki-native shape.
- Body-authority canonicalization and legacy graph-edge fallback are both explicit.
- Logical—not physical—`Entity.confidence` removal is respected.
- Old and new aggregate journals are both included in the intended replay matrix.
- Clean-commit cohort attribution and explained canonical-collision deltas are
  correctly carried forward.

## Findings

### F1 — Critical: Phase 1 resurrects `outgoing_links` in the aggregate payload

Task 1.5 says `reconcile_body_links` remains and becomes the sole producer of
`outgoing_links` on `PageIntent` (lines 116–120). That contradicts:

- D-115-1: no reconstructed `outgoing_links` in `CompiledSource` /
  `compile_result.json`;
- D-115-10: graph owns body-to-`LINKS_TO` derivation; and
- Task 2.2: new aggregate writers never emit the deprecated key (lines 154–159).

This is not merely an “internal field” today. `PageIntent.to_dict()` uses
`dataclasses.asdict`, and `CompiledSource.to_dict()` serializes every page through
that method (`common/types.py:211-223`, `243-266`). If `PageIntent.outgoing_links`
remains populated, every new `compile_result.json` will still carry it. Worse, graph
intake is designed to prefer the legacy key when present, so an accidentally emitted
field would bypass the new body-derived path entirely.

**Required correction:**

- remove `outgoing_links` from `PageIntent` and new `CompiledSource` serialization;
- delete the mutating `reconcile_body_links` step from `compile_one`, or replace it
  with a pure body extractor used only by telemetry/validation;
- keep body wikilink rewriting in slug coercion and canonicalization, but do not
  materialize a parallel edge list; and
- add an explicit test that recursively asserts no new compiled page contains an
  `outgoing_links` key, followed by a graph test proving the body still creates the
  expected edges.

### F2 — Critical: summary validation removes the input required by its own rule

Task 1.4 requires exact validation against a slug derived from the source filename
stem (lines 98–108). Task 1.5 then removes the `source_name` argument from the
semantic-check call (line 121). The payload no longer contains `source_name`, so the
validator would have no source identity from which to compute the expected slug.

The executable contract should be:

1. derive `expected_summary_slug` from trusted `job.source_id` before the model call;
2. fail before API spend if derivation is impossible (for example, a
   non-ASCII-only/empty-normalizing stem);
3. do **not** inject the value into the prompt, preserving Joseph's model-authorship
   decision; and
4. call `semantic_check(payload, expected_summary_slug=...)` on every attempt.

This also ensures a source-path defect is not treated as a stochastic model failure
and retried twice.

The collision policy remains underspecified. “Collision after truncation” is listed
as a test, but the expected outcome is not. With a filename-only rule, two directories
can contain the same basename, and long distinct basenames can collapse to the same
112-character suffix. Coherent options are:

1. fail closed when an expected summary slug is already reserved by another source;
2. add a deterministic path-derived suffix, which changes D-115-11 and requires new
   ratification; or
3. permit shared summaries, which conflicts with the per-source summary concept.

Under the ratified filename-stem rule, fail-closed collision detection is the
consistent choice. The blueprint must define its lookup scope—current run, manifest,
existing graph, or all three—and its failure stage.

### F3 — Critical: the post-canonicalization invariant is scoped incorrectly

Task 2.1 says “exactly one summary page across the batch” (line 148). A normal
multi-source batch has one summary **per compiled source**, so a literal batch-wide
gate would reject every run containing more than one successfully compiled source.

The invariant must be:

> For every `compiled_sources[i]`, exactly one page has
> `page_type == "summary"`, before and after canonicalization.

The blueprint should also specify error routing. A summary/non-summary merge rejection
needs a typed canonicalization exception caught by `compile_source` and returned as a
`CompileSourceResult(failure_stage="canonicalize", ...)`; otherwise the new hard
rejection can escape the source-local quarantine contract as an unexpected run error.

Finally, place the post-canonicalization gate immediately after
`canonicalize.run()` and before `page_writer`, manifest mutation, or graph intake.
Page/manifest lookup should retain its own fail-closed defense, but it should not be
the first detector.

### F4 — High: phase commit topology contradicts the hard sequencing contract

Lines 14–17 say Phases 1–4 land as one contract commit. Gate 2 commits Phases 1–2,
Gate 3 commits Phase 3, and Gate 4 commits Phase 4 (lines 178–179, 197–198,
213–214). Both approaches can produce an attributable final cohort, but the plan must
choose one.

Two coherent sequences are:

1. **Strict two-commit sequence:** Phase 0 commit → baseline; implement and verify
   Phases 1–4 without intermediate commits → one contract commit → comparison.
2. **Reviewable commit chain:** Phase 0 commit → baseline; separate Phase 1–2,
   Phase 3, and Phase 4 commits → comparison from the clean Gate-4 HEAD. The exact
   final SHA still identifies the complete before/after delta.

Whichever is selected, every commit remains behind Joseph's explicit commit approval
per repository policy; the plan must not treat “Gate N: commit” as automatic
authorization.

The North Star update is also too late. `docs/CODEBASE_OVERVIEW.md` currently says
Pass-2 emits link edges, canonicalization rewrites `pages[].outgoing_links`, and D-A2
retains confidence. The plan updates only D-A2 during Phase 3. The chosen architecture
must be reflected in the North Star before implementation begins, including:

- body-only Pass-2 response and graph-owned edge derivation;
- canonicalization remapping body wikilinks, not an edge-list projection;
- logical Entity-confidence deprecation; and
- repository ownership of the Pass-2 prompt.

The Task #115 ledger entry already exists and is adequate.

### F5 — High: “keep old fixtures untouched” conflates two incompatible formats

D-115-14 preserves historical **aggregate** `compile_result.json` sidecars. It does
not make old raw LLM responses valid under the new per-source response schema.

The existing `compiler/tests/fixtures/pass2_recovery/*.txt` files contain the old LLM
shape and are explicitly asserted schema-clean and semantic-clean, then fed through
`compile_one` (`compiler/tests/test_compiler_recovery.py:95-106`, `120-155`). The
new `compiled_source_response.schema.json` has `additionalProperties: false`, so
those responses will be rejected. Likewise, `tools/replay.py` is a model-response
validator replay tool, not graph-journal replay; an old response cannot remain a
successful case “unchanged” without a legacy response validator, which the
architecture does not call for.

Split the fixture policy:

- **historical aggregate sidecars/journals:** keep old shape untouched and require
  current `kdb-validate` + graph rebuild compatibility;
- **raw response/recovery fixtures used as current successful responses:** migrate
  their decoded payloads to the new LLM shape while preserving carrier noise and
  recovery boundaries; and
- **deliberate legacy-response negative cases:** optionally retain a small subset
  whose new expected outcome is schema rejection.

Fixture migration therefore belongs in Phase 1 with the response-schema change, not
after Gate 1. As written, “Gate 1: suite green; fixtures may still be old-shape” is
not achievable.

### F6 — High: aggregate validation and orchestration cascades are incomplete

Task 2.2 mentions deleting list-pairing checks but misses the load-bearing aggregate
summary rewrite. `validate_compile_result._check_source` currently derives all summary
findings from top-level `summary_slug` (`compiler/validate_compile_result.py:132-180`).
Once that field is absent, aggregate validation will no longer enforce any summary
invariant unless it is rewritten to inspect `pages[].page_type` and validate the
derived expected slug from `source_id`.

The same cascade includes:

- `HARD_ZERO_FINDING_TYPES`, `check_compiled_source`, their tests and stale shape
  documentation;
- response replay, which must pass trusted source identity or an expected slug into
  the new semantic gate;
- `orchestrator.kdb_orchestrate._combine_crs`, which currently aggregates
  `log_entries` and `warnings` and would otherwise drop `compilation_notes`
  (`orchestrator/kdb_orchestrate.py:156-183`);
- the `compile_one` return signature/state, which should not preserve an unused log
  slot; and
- `canonical_meta.outgoing_link_remaps` descriptions/stats, which become body-link
  remaps only even if the historical field name is retained.

Add these files and tests explicitly to Phases 1–2. New and historical aggregate
validation need separate assertions: new output omits deprecated keys; historical
output accepts them without causing new writers to copy them forward.

### F7 — High: logical confidence deprecation misses writers and snapshot versioning

Phase 3 covers the primary Entity upsert but not every Entity-confidence write.
Current code also writes the field when creating alias Entities
(`kdb_graph/intake.py:595-603`) and when the parked promotion path materializes an
Entity (`kdb_graph/ops/op_1_promote.py:307`). Those are Entity/page confidence writes,
not the protected Claim/Evidence confidence design, so they must stop under D-115-12.

The cascade should explicitly include:

- `kdb_graph/types.py` `Entity`;
- `kdb_graph/queries.py` and `graphdb.py` row-index mapping;
- alias and promotion Entity writes;
- `kdb_mcp/adapters.py` as well as the Pydantic model;
- test helpers that build the current producer shape; and
- viewer/CLI consumers found by the final scoped search.

Removing `confidence` from `entities.jsonl` changes the snapshot wire format even
though the dead Kuzu column remains. `SNAPSHOT_FORMAT_VERSION` must bump from 6 to 7,
with the removal documented and pinned in snapshot tests. Logical schema deprecation
does not make the snapshot change non-breaking.

Gate 3's “rebuild equals pre-change graph modulo confidence” also needs an executable
comparison. The post-change verifier no longer observes confidence and does not by
itself compare two graph directories. Define a normalized snapshot/table comparison
that removes only Entity confidence and proves every node, edge, and other property
is identical.

### F8 — Medium: the proposed measurement defaults can violate dataclass ordering

`RunMeasurementHeader` already has a required `pass2_prompt_version` before required
count fields, followed by defaulted `release_version`
(`common/measurement.py:166-180`). Task 0.2 describes both prompt fields as
default-empty at that location. Adding a defaulted field before later non-default
fields causes Python dataclass construction to fail with “non-default argument
follows default argument.”

It also is not enough to say historical readers default empty while
`load_run_measurements` directly calls `RunMeasurementHeader(**header_data)`
(`common/measurement.py:210-213`).

Specify one safe shape:

- keep all required fields first and append `pass2_system_prompt_sha256: str = ""`
  after `release_version`; retain the already-existing required
  `pass2_prompt_version`; or
- add an explicit `from_dict`/loader normalization that fills missing historical
  fields before construction.

Test by loading an actual pre-#115 header dictionary with no SHA field, not only by
constructing the new dataclass directly.

### F9 — Medium: prompt migration should copy, hash-verify, and retire logically

Task 0.1 says to move the live vault prompt into the repository. The vault file is an
external, user-owned artifact, so a filesystem move both deletes it and cannot appear
as a pure Git rename. The safe attributable sequence is:

1. copy the bytes into `compiler/prompts/`;
2. assert the copied file's SHA-256 equals the ratified pre-move anchor
   `dcfa3d1cd9c1e7c543527b5d4357ce46fb9f1e31a766a8127b8565942c11e12a`;
3. switch the loader and prove the rendered system prompt is byte-equivalent; and
4. retire the vault file logically by no longer reading it.

Physical deletion of the legacy vault file can be a separate, explicitly approved
operator cleanup after the comparison cohort. Gate 0 should pin the exact anchor hash,
not merely “non-empty prompt.” The wheel smoke command should also be defined so it
runs without network access (for example, build/install the local wheel with
dependencies omitted).

### F10 — Medium: parser parity must cover rewriting as well as extraction

Phase 4 names compiler/graph extractor parity, but the compiler currently has
multiple Markdown interpretations:

- strict body extraction in `validate_source_response.py`;
- permissive slug-coercion rewriting in `repair.py`; and
- canonical alias rewriting in `canonicalize.py`.

They already differ on headings, escaped tokens, and code spans; notably the current
canonicalizer says heading links are out of scope while the proposed parity corpus
explicitly includes them. If only the graph and strict extractor share expected
sets, canonicalization can still rewrite—or fail to rewrite—a different set of
tokens before graph derivation.

Define one fixture corpus with two expected outputs per case:

1. extracted target slugs; and
2. body text after coercion/canonical alias rewriting.

Run it against the compiler extractor, coercion rewriter, canonicalizer, and mirrored
graph extractor as applicable. Production packages remain independent; sharing
test-only data does not violate the import boundary.

## Required blueprint amendments

- [ ] Remove `outgoing_links` from `PageIntent` and prove new serialization omits it.
- [ ] Derive `expected_summary_slug` from trusted source identity before the call and
      pass it explicitly to semantic validation without prompt injection.
- [ ] Define fail-closed summary collision detection, scope, and failure routing.
- [ ] Change the post-canonicalization invariant to exactly one summary **per
      compiled source** and catch its typed failure.
- [ ] Reconcile the commit topology and add explicit Joseph approval at every commit
      gate.
- [ ] Update all affected North Star sections before implementation begins.
- [ ] Separate aggregate historical fixtures from current raw-response fixtures and
      move response-fixture migration into Phase 1.
- [ ] Rewrite aggregate summary validation and include replay/orchestrator combine
      cascades.
- [ ] Complete the Entity-confidence write/read inventory and bump snapshot format.
- [ ] Make historical measurement-header loading executable without invalid dataclass
      field ordering.
- [ ] Copy and exact-hash-verify the prompt; defer external deletion.
- [ ] Extend parser parity to canonicalization and coercion behavior.

## Recommended gate structure

### Architecture gate

- v1.1 blueprint resolves every item above.
- `docs/CODEBASE_OVERVIEW.md` records the chosen end-to-end architecture.
- Joseph explicitly says **Proceed**.

### Provenance gate

- packaged prompt byte hash equals the ratified vault-prompt anchor;
- installed-wheel prompt smoke passes;
- historical measurement header loads;
- full non-live suite passes;
- Joseph approves the Phase 0 commit; and
- baseline cohort runs from that clean commit.

### Contract/system gate

- new response and aggregate payloads contain no reconstructed `outgoing_links`;
- old aggregate sidecars validate and rebuild;
- new raw response fixtures pass; intentionally retained legacy responses fail with
  the expected classification;
- post-canonical summary, collision, graph derivation, live/rebuild, mixed-journal,
  parser, confidence, snapshot, and MCP tests pass;
- normalized pre/post graph comparison differs only by Entity confidence;
- full suite and wheel build pass; and
- Joseph approves the final implementation commit or reviewed commit chain.

### Cohort/closure gate

- comparison runs from the clean final HEAD;
- stamps and release SHA differ as expected;
- quarantine/retry/recovery metrics remain within the ratified bounds;
- canonical-collision graph deltas are enumerated rather than hidden; and
- ledger, North Star milestone changelog, and handoff are updated before closure.

## Final verdict

Revise before Proceed. The plan has the right architecture and does not need another
broad design cycle, but its current serialization and validator wiring would violate
the central contract, and its fixture/commit gates cannot all be satisfied as
written. A v1.1 addressing the required amendments above should be ready for
ratification and implementation.
