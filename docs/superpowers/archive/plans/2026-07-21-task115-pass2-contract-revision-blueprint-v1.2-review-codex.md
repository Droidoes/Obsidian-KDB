# Task #115 — Pass-2 contract revision blueprint v1.2: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-revision-blueprint.md` v1.2  
**Architecture basis:** Task #115 decisions v1.5 (`D-115-1..15`)  
**Repository anchor reviewed:** `main` at `8af7139`  
**Verdict:** Targeted v1.3 required before Proceed

## Executive assessment

v1.2 successfully fixes the central v1.1 sequencing defect. Graph-owned body-to-edge
derivation now lands inside Gate 2, so every approved commit remains runnable and a
body-only recompile cannot erase `LINKS_TO`. The historical aggregate validator is
properly dual-mode, the nonexistent snapshot loader is gone, the empty repair
dispatcher is deleted, the summary-page helper now sits at the serialized mapping
boundary, and Gate 3 has a real before artifact.

Six of the seven prior amendments are fully resolved. Collision policy is
architecturally resolved but not yet executable in the current call graph.

The fresh pass found two high-severity blockers:

1. `status` is still reconstructed into `PageIntent`/`compile_result.json`, directly
   contradicting ratified D-115-1 and v1.2's own “new writers never emit old keys”
   assertion.
2. the collision preflight has no manifest/reservation input, typed return path, or
   MOVED-source lineage rule; the existing `compile_one` tuple cannot route its
   promised `failure_stage="validate"`.

Four medium findings close telemetry, public-validator, malformed-response, and
North-Star details. This remains a narrow plan revision, not a design reopening.

## Prior-review resolution

| v1.1 amendment | v1.2 status | Assessment |
|---|---|---|
| Move body-to-`LINKS_TO` derivation before Gate 2 | Resolved | Task 2.4 and Gate-2 recompile coverage make the contract commit integration-safe. |
| Dual-mode historical/new aggregate validation | Resolved | Legacy referential/type semantics and new exact identity semantics are separated. |
| Define collision authority, precedence, plumbing, and preflight | Partial | Authority and fail-closed precedence are stated; function/data plumbing, typed routing, and move lineage remain open. |
| Remove the v6 snapshot-loader requirement | Resolved | v7 remains writer-only; journal rebuild is the executable compatibility path. |
| Delete or justify the empty repair stage | Resolved | The finding-driven dispatcher and failure route are explicitly deleted. |
| Type `summary_page` for serialized mappings | Resolved | The helper now matches page_writer/manifest_writer's actual boundary. |
| Capture a Gate-2 graph baseline for Gate 3 | Resolved | A pinned mixed-journal corpus and normalized artifact are specified. |

## Findings

### F1 — High: `status` is still reconstructed into new aggregate payloads

Ratified D-115-1 lists `status` among the six removed fields and explicitly says the
removed aggregate projections are **not reconstructed** in `CompiledSource` or
`compile_result.json` (`pass2-contract-audit-findings.md:13-20`). Python owns the
operational value at consumer boundaries.

v1.2 instead drops only `confidence` and `outgoing_links` from `PageIntent`, then says
the compiler stamps `status="active"` (blueprint lines 155–166). Because
`PageIntent.to_dict()` uses `asdict`, that stamp is serialized into every new
aggregate. This also contradicts Task 2.2's statement that removed fields are
read-only and “new writers never emit old keys” (lines 218–232).

The downstream cutover is already cheap:

- `page_writer._fm_for_page()` defaults an absent status to `active`
  (`compiler/page_writer.py:160-180`); and
- graph intake defaults an absent status to `_DEFAULT_ENTITY_STATUS`
  (`kdb_graph/intake.py:283-299`).

**Required correction:** drop `status` from `PageIntent` and new aggregate
serialization. Keep it optional/deprecated in the aggregate schema solely for
historical validation. Treat the page-writer/frontmatter and graph-upsert defaults as
the Python-owned operational stamp. Extend the recursive new-payload assertion to
cover all six removed keys, including `status`, while proving historical payloads
containing it still validate and rebuild.

### F2 — High: collision preflight is not wired into the produce call graph and mishandles MOVED lineage

Task 1.4 now selects a coherent authority: manifest source metadata plus a
current-run overlay, with graph/page state as a fail-closed consistency check
(blueprint lines 131–153). The plan still does not say how that state reaches the
compiler.

Today the orchestrator owns the live `full_manifest` and updates it after every
successful source commit (`orchestrator/kdb_orchestrate.py:806-860`), but its
`compile_source()` call passes no manifest or reservation index (lines 704–715).
`compile_source()` likewise accepts no such input (`compiler/compiler.py:601-623`).
If preflight is placed inside `compile_one`, that function has neither the manifest
nor graph connection. If it returns through the planned
`(compiled_source, compilation_notes, error)` tuple, `compile_source` will classify
the error as `failure_stage="compile"`, not the promised `"validate"`
(`compiler/compiler.py:657-675`).

Move lineage is also load-bearing. The orchestrator explicitly supports a
MOVED+CHANGED source appearing in both queues and skips the later reconcile because
the compile path already handled it (`orchestrator/kdb_orchestrate.py:872-878`). In
that case, the old source ID can still own the same summary slug in both manifest and
graph. A literal “different source” check rejects the new source ID, quarantines the
move, and can leave the old ownership in place indefinitely.

**Required correction:** define an executable preflight boundary, for example:

1. the orchestrator builds a `SummaryReservationIndex` from the current
   `full_manifest` immediately before each `compile_source` call;
2. the index is keyed both ways (`slug -> owner` for collision checks and
   `source_id -> slug` for consistency) and includes the current-run state already
   reflected in `full_manifest`;
3. scan move lineage (`ScanEntry.previous_path` / MOVED `from -> to`) is passed as an
   allowed predecessor so a genuine move transfers identity rather than colliding
   with itself;
4. `compile_source` receives the index, performs the graph consistency query, and
   returns a typed `CompileSourceResult(failure_stage="validate", ...)` before the
   model call; and
5. tests cover same-source recompile, distinct-source collision, ambiguous graph
   ownership, manifest/graph disagreement, and MOVED+CHANGED with an unchanged
   basename.

An equivalent design is acceptable, but the plan must name the signature/state flow
and moved-source rule; the current three-line policy cannot be translated without
new architectural choices during implementation.

### F3 — Medium: “zero model calls” has no defined telemetry behavior

The collision and slug-derivation preflights promise zero model calls, but their
location determines whether a Pass-2 response-stat record exists. `compile_one`
currently owns the always-write `finally` block, while a natural `compile_source`
preflight would return before entering it.

Even if preflight is moved inside `compile_one`, the current telemetry fallback
forces a no-call failure to `call_count=1` and `final_attempt_index=1`
(`compiler/compiler.py:546-553`). That would make the “zero-call” assertion true only
of the mock, not of the persisted measurement contract.

**Required correction:** specify and test the persisted result. The most honest
contract is one quarantined Pass-2 telemetry record with `attempts=0`,
`call_count=0`, `final_attempt_index=0`, zero tokens/latency, and
`failure_stage="validate"`. If preflight failures are intentionally excluded from
Pass-2 measurement records instead, reconcile that choice with `p2_attempted`,
quarantine-rate inputs, and the existing one-record-per-attempt expectation.

### F4 — Medium: the exact summary algorithm and public validation surfaces remain distributed

The same summary identity rule is needed by Task 1.4's pre-call gate, Task 2.2's
aggregate validator, response replay, and the public `kdb-validate-response` CLI.
v1.2 describes derivation in multiple tasks but does not assign it to one executable
helper.

The current CLI still accepts `--source-name` and invokes
`semantic_check(..., source_name=...)` (`compiler/validate_source_response.py:127-155`).
`tools/replay.py` similarly stores `ReplayFixture.source_name` and case metadata under
`source_name` (`tools/replay.py:32-85`, `119-126`). Task 2.2 says replay will pass
trusted identity, but the fixture/CLI migration is not listed.

**Required correction:** define one compiler-owned pure helper, for example
`expected_summary_slug(source_id: str) -> str`, that pins `Path(source_id).stem`,
`slugify`, the 112-character stem budget, trailing-hyphen handling, and typed empty
normalization. Reuse it in preflight, aggregate validation, replay, and CLI. Migrate
replay cases to `source_id`, and replace or supplement the CLI flag with
`--source-id`; define whether omitting it means schema-only validation or is an
operator error. This avoids four subtly different implementations of D-115-11.

### F5 — Medium: `ParsedSummary` derivation must remain non-throwing on rejected responses

Task 1.6 says `ParsedSummary.summary_slug` is derived from the summary page
(blueprint lines 179–184), while Task 1.5 introduces a fail-closed `summary_page`
helper. Those two semantics must not be conflated.

`build_parsed_summary()` runs from `compile_one`'s `finally` block for every parsed
dictionary, including schema- or semantic-rejected responses
(`compiler/compiler.py:520-524`). Its current explicit contract is “Never raises”
(`compiler/resp_summary.py:15-20`). Reusing the operational fail-closed helper would
turn an ordinary zero/multiple-summary quarantine into an exception from telemetry,
masking the real failure.

**Required correction:** pin telemetry behavior separately: return the summary slug
only when exactly one well-formed summary page is observable; otherwise store
`None`. Body-link counting must likewise tolerate malformed pages/bodies. Add
zero-summary, multiple-summary, and malformed-page tests that exercise the real
`compile_one` finally path.

### F6 — Medium: the North-Star gate omits two architecture changes made by the plan

The North-Star gate lists body-only response, graph-owned edges, confidence
deprecation, and prompt ownership (blueprint lines 39–44). It does not mention:

- the exact boundary for Python-owned `status` after it disappears from new
  aggregates; or
- deletion of the finding-driven Repair stage, with slug coercion retained inside
  the compile attempt loop.

The current North Star explicitly documents Stage 5 as unconditional
`reconcile_slug_lists` + `reconcile_body_links` and describes Pass-2 as emitting edge
projections (`docs/CODEBASE_OVERVIEW.md:184-197`). Leaving the Repair-stage deletion
out of the pre-implementation docs commit violates the plan's own North-Star-first
gate and would leave stage numbering/ownership stale.

**Required correction:** add both items to the North-Star commit scope and update the
end-to-end stage flow, not only D-A2 and prompt-location prose.

## Required v1.3 amendments

- [ ] Remove `status` from `PageIntent` and all new aggregate payloads; stamp it only
      at operational consumer boundaries.
- [ ] Define the reservation-index type, orchestrator-to-compiler signature, graph
      check, typed failure route, and MOVED predecessor semantics.
- [ ] Pin zero-call preflight telemetry (`call_count`/attempt index and KPI inclusion).
- [ ] Centralize `expected_summary_slug(source_id)` and migrate replay/CLI identity
      inputs from `source_name`.
- [ ] Keep `ParsedSummary` best-effort and non-throwing on invalid parsed responses.
- [ ] Add status ownership and Repair-stage deletion to the North-Star-first commit.

## What is now solid

- Gate 2 is a runnable body-only contract commit with graph derivation included.
- Legacy `outgoing_links` remains preferred only when the key is present.
- Historical and new aggregate summary validation are correctly separated.
- Canonicalization enforces one summary per source before persistence.
- The finding-driven repair dispatcher is removed without deleting slug coercion.
- Confidence deprecation and snapshot v7 remain properly isolated in Phase 3.
- Gate 3 compares the same pinned mixed-journal corpus against a Gate-2 artifact.
- Parser extraction and rewriting parity remain an appropriate Phase-4 system gate.

## Final verdict

Revise before Proceed, narrowly. v1.2 resolves the previous review's substantive
issues and is close to implementation-ready. v1.3 should remove the last aggregate
contract violation and make collision preflight a real typed data flow—including
move lineage and honest zero-call telemetry. The four medium amendments are small
but worth pinning before implementation because each otherwise lands in a failure or
operator path that the happy-path suite can miss.
