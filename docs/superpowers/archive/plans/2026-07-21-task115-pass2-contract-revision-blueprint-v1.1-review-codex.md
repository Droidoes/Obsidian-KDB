# Task #115 — Pass-2 contract revision blueprint v1.1: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-revision-blueprint.md` v1.1  
**Architecture basis:** Task #115 decisions v1.5 (`D-115-1..15`)  
**Repository anchor reviewed:** `main` at `8af7139`  
**Verdict:** Targeted revision required before Proceed

## Executive assessment

v1.1 is a substantial improvement. It correctly absorbs the central contract
corrections from the v1.0 review: new payloads no longer reconstruct
`outgoing_links`, summary identity comes from trusted source identity, the
post-canonicalization invariant is per source, raw response fixtures are separated
from historical aggregates, the confidence inventory is much more complete, and the
commit/North-Star gates now match repository policy.

Eight of the ten prior findings are fully resolved; the collision and snapshot
findings are only partially resolved. One new load-bearing problem is introduced by
the revised phase boundaries: Gate 2 would commit body-only payloads before graph
intake knows how to derive links from bodies. A run from that supposedly green commit
would delete each recompiled page's existing `LINKS_TO` edges and recreate none.

The remaining work is a focused v1.2, not another architecture cycle. Move graph-side
body parsing into the contract commit, preserve genuinely legacy aggregate-validation
semantics, and close five smaller execution details.

## Prior-review resolution

| v1.0 finding | v1.1 status | Assessment |
|---|---|---|
| R5 F1 — `outgoing_links` resurrection | Resolved | `PageIntent` drops the field and new serialization is recursively tested. |
| R5 F2 — expected summary identity/collision | Partial | Trusted pre-call derivation is correct; collision ownership, precedence, and call timing remain incomplete. |
| R5 F3 — batch-wide summary invariant | Resolved | The invariant is now per compiled source with typed canonicalization routing. |
| R5 F4 — commits and North Star | Resolved | Reviewable commit chain, explicit approval, and North-Star-first are all explicit. |
| R5 F5 — fixture-format conflation | Resolved | Raw current-response fixtures migrate; historical aggregate journals remain untouched. |
| R5 F6 — aggregate/orchestrator cascades | Resolved with one compatibility caveat | The affected surfaces are listed, but historical summary validation needs dual-mode behavior. |
| R5 F7 — confidence/snapshot inventory | Partial | Writers/readers and v7 bump are covered; the nonexistent loader and comparison baseline are not. |
| R5 F8 — dataclass ordering | Resolved | The new defaulted field is appended and historical dictionaries are normalized. |
| R5 F9 — prompt copy/hash | Resolved | Byte copy, pinned hash, logical retirement, and wheel smoke are explicit. |
| R5 F10 — parser parity | Resolved | Extraction and rewriting both have expected outputs across all four implementations. |

## Findings

### F1 — Critical: Gate 2 is not an integration-safe commit

Gate 2 commits Phases 1–2 (blueprint lines 249–251), where new pages no longer carry
`outgoing_links`. Graph-owned body derivation does not arrive until Task 3.2
(lines 272–277), after the Gate-2 commit.

Today the orchestrator defers link wiring until finalization
(`orchestrator/kdb_orchestrate.py:128-133`, `186-203`). `wire_links()` visits every
compiled page (`kdb_graph/intake.py:729-750`), and `_replace_outgoing_links()` first
deletes all existing outgoing edges, then recreates only those found in
`page.get("outgoing_links", [])` (`kdb_graph/intake.py:309-337`). Under the Gate-2
shape, that list is absent, so a recompile erases the page's `LINKS_TO` edges.

The graph test promised in Task 1.5 (blueprint lines 177–179) also cannot pass against
the real Gate-2 implementation; calling it a bridge to Phase 3 does not make Gate 2
green.

**Required correction:** move Task 3.2 and its minimum body-to-edge integration tests
into Phase 2, before Gate 2. Graph-edge derivation is part of the contract cutover,
not a later consumer cleanup. Confidence deprecation and snapshot v7 can remain in
Phase 3; the broader parser-parity corpus can remain in Phase 4.

### F2 — High: historical aggregate validation is made stricter than the preserved contract

D-115-14 preserves existing aggregate sidecars under the current validation and
rebuild paths. Task 2.2 instead says aggregate validation always derives the exact
expected summary slug from `source_id` (blueprint lines 224–237).

That exact filename-stem equality is a new D-115-11 rule. The current aggregate
validator does not enforce it on historical records: when `summary_slug` is present,
it only checks that the referenced page exists and has `page_type == "summary"`
(`compiler/validate_compile_result.py:159-178`). The old JSON Schema likewise checks
the `summary-*` form, not equality with the source filename. Therefore a historical
sidecar can be valid today yet fail the proposed validator even though the plan says
historical output still validates.

**Required correction:** define dual-mode aggregate validation:

- legacy source with top-level `summary_slug`: preserve the existing referential and
  page-type checks;
- new source without that field: derive the expected slug from `source_id`, require
  exactly one summary page, and enforce exact equality.

Alternatively, the blueprint could require an audited historical corpus proving
every retained journal already satisfies the new exact rule, but it currently has no
such audit and that would be a less robust compatibility strategy.

### F3 — High: collision detection has no authoritative ownership map or preflight contract

Task 1.4 names three lookup scopes—current committed pages, manifest, and graph—and
says a slug reserved by a “different source” fails at `validate` (blueprint lines
147–153). It does not define:

- how each store maps a slug to its owning source;
- which store is authoritative when they disagree;
- how an existing graph Entity with missing/ambiguous primary ownership is treated;
- what state is passed into `compile_source`/`compile_one`; or
- whether the deterministic collision check happens before the model call.

Without those rules, three independently queried stores can produce inconsistent
answers, and implementations can spend an API call before rejecting a collision that
was already knowable.

**Required correction:** specify one source→summary reservation map and its data
flow. The most direct design is a current-run overlay on the manifest's existing
`source_id -> summary_slug` metadata, with graph/page state used as a fail-closed
consistency check rather than a competing authority. Define disagreement and
unowned-Entity behavior explicitly. Perform this collision preflight alongside slug
derivation before the API call, assert zero model calls in collision tests, and route
the returned source-local failure as `failure_stage="validate"` if that label is to
be retained.

### F4 — Medium: Task 3.3 requires a snapshot loader that does not exist

Task 3.3 says the “loader handles v6 historical snapshots” (blueprint lines
279–283). The snapshot module explicitly states that it is write-only and that a
future `load-snapshot` command is out of scope (`kdb_graph/snapshot.py:1-10`,
`46-52`). The North Star says the same (`docs/CODEBASE_OVERVIEW.md:639`).

This sentence either creates an unplanned recovery subsystem or sets an impossible
acceptance criterion. Bump and test the writer format at v7, document v6 for a future
reader, and remove loader implementation from Task #115. Historical journal rebuild
compatibility—not snapshot loading—is the relevant executable D-115-14 path.

### F5 — Medium: deleting all repair rules leaves an empty repair stage behind

Task 2.3 deletes the three list-fixer families but retains coercion and the pure body
extractor (blueprint lines 241–247). Those list fixers are the only registered repair
rules today (`compiler/repair.py:80-153`). Once removed, `_RULES`, `repair()`,
`ReconcileAction`, `RepairError`, and the compiler's `failure_stage="repair"` branch
become dead dispatch machinery (`compiler/compiler.py:692-700`).

**Required correction:** explicitly remove the empty finding-driven repair stage and
its tests/types while retaining the pre-validation slug coercer and pure extractor.
If the stage is intentionally retained as an extension point, say so and justify why
an empty runtime phase is preferable; that would conflict with this task's stated
dead-machinery goal.

### F6 — Medium: `summary_page` is typed for a shape its consumers do not hold

Task 1.5 defines `summary_page(compiled_source) -> PageIntent` and sends
`page_writer.py` and `manifest_writer.py` through it (blueprint lines 170–176). Both
consumers currently operate on serialized dictionary entries from `compile_result`,
not `CompiledSource`/`PageIntent` dataclasses (`compiler/page_writer.py:208-234`,
`orchestrator/manifest_writer.py:282-297`).

Define the helper's integration boundary precisely. The smallest coherent form is a
pure mapping helper such as `summary_page(source: Mapping[str, object]) -> dict` (or a
read-only mapping), used by aggregate consumers. Otherwise the implementation must
rehydrate dataclasses or introduce separate helpers, recreating the drift this helper
is meant to prevent.

### F7 — Medium: Gate 3's pre/post graph diff has no “before” artifact

Gate 3 asks for an executable normalized pre/post comparison after rebuilding
historical journals (blueprint lines 285–288), but it never captures the pre-Phase-3
graph/table state or identifies a pinned expected fixture. Running the post-change
rebuild twice proves determinism, not equivalence to the pre-change behavior.

**Required correction:** after moving body-derived wiring into Gate 2, capture a
normalized Gate-2 rebuild artifact from a pinned mixed-journal corpus. Gate 3 then
rebuilds the same corpus and compares against that artifact with only Entity
confidence excluded. Specify the command/fixture and retained tables/properties so
the gate is reproducible in CI rather than an operator-only assertion.

## Required v1.2 amendments

- [ ] Move graph-owned body-to-`LINKS_TO` derivation and minimum integration coverage
      before Gate 2.
- [ ] Split legacy and new aggregate summary validation semantics.
- [ ] Define one collision ownership map, precedence rules, state plumbing, and a
      zero-model-call preflight.
- [ ] Remove the nonexistent v6 snapshot-loader requirement; keep the v7 writer bump.
- [ ] Delete or explicitly justify the now-empty finding-driven repair stage.
- [ ] Define `summary_page` for the serialized mapping boundary its callers use.
- [ ] Capture a pinned Gate-2 graph baseline for the Gate-3 normalized comparison.

## What does not need reopening

The ratified architecture decisions remain coherent. In particular, do not reopen:

- the body-only LLM response;
- graph ownership of edge derivation;
- exact summary identity for **new** outputs;
- fail-closed collisions rather than silent suffixes or shared summaries;
- logical-only Entity-confidence deprecation;
- prompt repository ownership and byte-provenance baseline; or
- the reviewable commit chain with explicit approval at every commit gate.

## Final verdict

Revise before Proceed, but narrowly. v1.1 resolves the original contract-shape
problems well. v1.2 should chiefly repair the phase ordering, make read compatibility
truly legacy-aware, and turn the remaining operational statements into executable
contracts. With the seven amendments above, the blueprint should be ready for
ratification.
