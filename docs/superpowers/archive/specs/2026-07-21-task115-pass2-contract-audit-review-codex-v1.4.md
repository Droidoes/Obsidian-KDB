# Task #115 — Pass-2 contract audit v1.4: Codex review

**Date:** 2026-07-21  
**Reviewer:** Codex  
**Reviewed artifact:** `2026-07-21-task115-pass2-contract-audit-findings.md` v1.4  
**Repository anchor:** `main` at `7d8263b`  
**Verdict:** Product decisions ratified; resolve the integration contract before implementation

## Executive assessment

v1.4 is materially stronger as a decision record. The target LLM response is small,
wiki-native, and much easier to explain: the model authors pages and prose; Python
owns identity, persistence, and derived system state. The decisions on
`compilation_notes`, `page_type`, prompt ownership, and retired-model validation are
well supported.

The significant changes also expand Task #115 beyond a prompt/schema cleanup. It now
changes four architectural contracts:

1. the producer journal consumed by graph replay;
2. the meaning of canonical page merges;
3. the physical Kuzu schema and public MCP response shape; and
4. the packaging/provenance contract for the repository-owned prompt.

Those consequences are not fully specified yet. The product decisions do not need to
be reopened, but two implementation-level choices do: whether canonical merges may
discard links present only in losing bodies, and whether `Entity.confidence` is
logically deprecated or physically removed now.

## Findings

### F1 — High: body-owned links change canonical merge semantics

D-115-1 makes the persisted body the only link authority and removes
`outgoing_links` from both `PageIntent` and `compile_result.json` (lines 17–47,
148–152). That is internally consistent until canonical page collisions occur.

The current canonicalizer deliberately keeps one contender's body while unioning
`outgoing_links` from every contender (`compiler/canonicalize.py:394-430`). The test
at `compiler/tests/test_canonicalize_algorithm.py:320-336` states why: links
contributed by losing page intents must not be silently dropped.

After v1.4, deriving graph edges from the surviving body necessarily drops links that
occur only in losing bodies. Preserving the old union as a transient Python edge set
would keep graph behavior but violate the ratified rule that links are body-derived
wiki state rather than a parallel projection.

Two coherent implementations exist:

1. **Body is absolute authority.** Accept the canonicalization behavior change,
   remove the union invariant, and require `LINKS_TO(final page)` to equal the
   wikilinks in the final persisted body.
2. **Merge preserves all link contributions.** Define a deterministic body-merge or
   body-annotation rule that puts every retained link into the surviving wiki body.
   This preserves graph information but changes prose and is substantially more
   complex.

The first option best matches D-115-1's stated design principle, but the loss must be
explicitly ratified. The validation claim should then allow explained graph-KPI
deltas for canonical-collision cases rather than asserting that KPIs cannot move.

### F2 — High: the link-derivation owner and live/replay contract are unspecified

The graph currently consumes `page.outgoing_links` directly
(`kdb_graph/intake.py:309-344`, `729-750`). Live orchestration calls graph intake
directly, while rebuild/replay loads archived producer JSON and passes it to the same
core through `ObsidianRunsAdapter` (`kdb_graph/adapters/obsidian_runs.py:9-16`,
`181-200`). The `kdb_graph` package cannot import `compiler` or `common`, so it cannot
reuse `compiler.validate_source_response.body_wikilink_slugs`.

The blueprint must assign one owner for converting body text into graph edges. Two
viable boundaries are:

1. **Graph-owned derivation.** `kdb_graph.intake` parses body wikilinks for new
   payloads and uses legacy `outgoing_links` when that key is present. Both live and
   replay therefore use one graph-core function.
2. **Versioned producer adapter.** Live orchestration and historical replay each
   normalize their input into an internal graph mutation shape containing derived
   edges before core intake. This keeps Markdown parsing outside graph core but adds
   two paths that must be proven equivalent.

Graph-owned derivation is the simpler boundary and naturally preserves
live-equals-replay. Because package layering prevents sharing the parser code, the
compiler and graph parsers should share a fixture corpus covering plain links,
aliases, headings, escaped links, fenced code, inline code, duplicates, and malformed
tokens. A system test must assert:

> final wiki-body wikilinks = live graph `LINKS_TO` = rebuilt graph `LINKS_TO`

For historical payloads, preferring an existing legacy `outgoing_links` value
preserves the graph semantics of the original run; body derivation is the fallback
for the new shape.

### F3 — High: lookup-by-type needs a post-canonicalization summary invariant

Lines 28–42 replace aggregate `summary_slug` with lookup of the page whose
`page_type == "summary"`. The per-response semantic gate can guarantee exactly one
summary before canonicalization, but canonicalization happens after aggregate
validation (`compiler/compiler.py:683-705`) and can merge pages across types while
retaining the winner's `page_type` (`compiler/canonicalize.py:336-460`). There is no
post-canonicalization validation pass today.

That creates a new failure mode: an alias-ledger collision between a summary page and
a concept/article page can leave zero summary-typed pages. The current pipeline still
has the remapped top-level `summary_slug` to identify the primary page; the v1.4
lookup-by-type consumers would not.

The blueprint should require all of the following:

- exactly one summary page before **and after** canonicalization;
- a hard rejection of summary/non-summary cross-type canonical merges, or an
  equivalent invariant that preserves the summary type;
- page writer and manifest writer to fail closed if lookup returns zero or multiple
  pages, never silently choose the first; and
- tests for alias-singleton summary renames and cross-type collision rejection.

The summary-slug convention also needs an executable definition. The existing schema
regex only proves `summary-*`; it does not prove equality to the source stem. Define
the exact source-id-to-slug algorithm, including the 120-character total limit,
non-ASCII-only stems, empty normalization, and collisions. This does not reintroduce
prompt injection: the model can remain the slug author while Python validates exact
equality against the deterministic expected value.

### F4 — High: confidence deprecation is a graph migration and API change

D-115-4 correctly rejects model-authored page confidence, but “end-to-end” currently
spans more than the listed Python fields:

- `Entity.confidence` is a physical Kuzu column in schema 2.4
  (`kdb_graph/schema.py:57-73`);
- schema migrations are non-destructive, while destructive changes require
  `graphdb-kdb rebuild` (`kdb_graph/schema.py:210-223`);
- snapshot format 6 serializes the field (`kdb_graph/snapshot.py:269-299`);
- `EntityCard.confidence` is a required public MCP field
  (`kdb_mcp/models.py:7-14`); and
- the North Star still explicitly retains the Entity confidence enum
  (`docs/CODEBASE_OVERVIEW.md`, D-A2).

Two implementation paths satisfy the semantic decision:

1. **Logical deprecation now.** Stop accepting, writing, querying, verifying,
   snapshotting, and returning the value, but leave the unused Kuzu column until the
   next destructive schema change. This avoids a rebuild solely to remove one dead
   column.
2. **Physical removal now.** Bump the graph schema, require a rebuild, bump the
   snapshot format, update the MCP response contract, and document the operational
   cutover.

The first is lower-cost and reversible; the second makes the physical schema match
the conceptual model immediately. v1.4 must select one before blueprint ratification.
Whichever path is selected, scope the removal as **page/Entity confidence**. The
parked Claim/Evidence tier has separate computed confidence fields and evaluation
fixtures; a broad mechanical removal of every `confidence` reference would damage
that distinct 2.0 design.

### F5 — High: repository prompt packaging and git provenance need hard gates

Moving the prompt into `compiler/prompts/` is sound, but the proposed file will not
currently ship in a built package. `pyproject.toml:45-48` includes only
`compiler/schemas/*.json` for the compiler package. Editable installs may hide this
defect; a wheel install will not.

The blueprint must add `prompts/*.md` to package data and include a build/install
smoke test that loads the prompt from an installed wheel.

The provenance sequence also needs tightening. `git describe --dirty` proves only
that some uncommitted change existed; it does not identify the dirty schema,
`RESPONSE_CONTRACT`, or exemplar content. Since the broader fingerprint proposal was
ratifiably rejected, attribution must come from clean commit boundaries:

1. implement and commit the provenance fields;
2. record a clean baseline run;
3. implement and commit the contract revision; and
4. run the comparison cohort from that second clean commit.

The spec should name the canonical persistence surfaces. At minimum,
`measurement_header.json` should carry `pass2_prompt_version`,
`pass2_system_prompt_sha256`, and the exact release commit; state whether the primary
run journal duplicates them or joins through `run_id`. A validation run with
`release_version == "unknown"` or a dirty tree should not be considered attributable
under the chosen git-based design.

### F6 — Medium: the historical read-compat path is described incorrectly

Lines 33–37 name pairing validation, canonical list remapping, and repair fixers as a
historical replay path. Replay does not call those producer stages; the adapter loads
the archived `compile_result.json` and applies it directly to graph intake.

Compatibility also covers more than the slug lists. Old artifacts can contain:

- aggregate `summary_slug`, `concept_slugs`, and `article_slugs`;
- page `outgoing_links` and `confidence`; and
- top-level `warnings` and `log_entries`.

Because `compile_result.schema.json` uses `additionalProperties: false`, simply
deleting those properties from the active aggregate schema will make historical
artifacts fail current validation even if replay intake ignores them.

Choose and document one policy:

1. keep the removed fields as optional, deprecated **read-only** properties in the
   aggregate schema while new writers never emit them; or
2. bump the producer/journal shape and dispatch old and new payloads through separate
   validators/adapters.

The first is the smaller change; the second provides a stricter version boundary.
Either way, retain old-shape replay fixtures alongside new-shape fixtures rather than
replacing them. State explicitly whether “read-compatible” means graph rebuild only
or also `kdb-validate` against historical sidecars.

### F7 — Medium: response telemetry still encodes every removed field

`ParsedSummary` currently persists `summary_slug`, `outgoing_link_count`,
`log_entry_count`, `warning_count`, and `source_id_echoed`
(`common/types.py:359-373`). `compiler/resp_summary.py:15-53` reads those values from
the soon-to-be-removed response fields. Without an explicit change, new runs will
silently report `None` and zero values, making the cohort's telemetry shape change at
the same time as the contract.

Define the replacement deliberately:

- derive summary slug from the one summary page if it remains useful telemetry;
- derive outgoing-link count from bodies if the metric remains useful;
- replace warning count with `compilation_note_count`;
- remove log-entry count and source-name echo; and
- keep loaders tolerant of historical response-stat records.

This is important to the claim that recovery and quality KPIs are comparable across
the before/after cohort.

### F8 — Low: narrow the “none are Python-reconstructed” wording

The D-115-1 title says none of the six fields are Python-reconstructed, while §3 says
Python stamps `status: active` and derives link edges. The intended distinction is
clear but the wording is not.

Suggested formulation:

> Six fields leave the LLM contract. Removed aggregate projections are not
> reconstructed in `CompiledSource` or `compile_result.json`; Python independently
> owns operational status, summary lookup, and graph-edge derivation.

This preserves the ratified decision while preventing implementation debates over
whether a derived edge or persisted status is a forbidden reconstruction.

## Required validation additions

The v1.4 validation plan is necessary but not sufficient for the expanded scope. Add:

- a packaged-wheel prompt-load smoke test;
- exact summary-slug boundary tests and a post-canonicalization summary gate;
- canonical-collision tests defining losing-body link behavior;
- compiler/graph wikilink parser parity fixtures;
- live-versus-rebuild equality for the new body-only payload;
- mixed historical/new journal rebuild tests;
- graph-schema upgrade or logical-deprecation tests, depending on D-115-4's chosen
  physical policy;
- snapshot and MCP contract tests for `Entity.confidence` removal; and
- before/after cohort runs from clean, distinct git commits.

## Exit criteria for v1.5 / blueprint entry

- [ ] Ratify canonical-collision link semantics under body authority.
- [ ] Assign the body-to-`LINKS_TO` derivation owner and legacy fallback.
- [ ] Add a post-canonicalization exactly-one-summary invariant.
- [ ] Specify the exact summary-slug derivation/validation algorithm.
- [ ] Select logical or physical removal of `Entity.confidence` and update the North
      Star accordingly.
- [ ] Add prompt package-data and installed-wheel verification.
- [ ] Define clean-commit provenance sequencing and exact stamp surfaces.
- [ ] Define aggregate historical-validation/replay compatibility.
- [ ] Migrate `ParsedSummary` intentionally rather than allowing silent zeros.
- [ ] Expand the validation matrix to cover graph rebuild, snapshot, and MCP.

## Final verdict

Keep Joseph's v1.4 product decisions. The reduced LLM contract is the right direction,
and no further retired-model experimentation is warranted. Do not translate the
document directly into implementation yet: the body-only link contract, summary
identity after canonicalization, confidence storage migration, and prompt packaging
are architectural boundaries, not cleanup details. A focused v1.5 that closes the
exit criteria above should be sufficient for blueprint ratification; no new broad
audit is needed.
