# Task #115 Phase 4 — Gate-4 code review (Codex)

## Verdict: GO-WITH-CHANGES

The production change in `compiler/repair.py` is directionally correct: escaped wikilink syntax and wikilink-shaped text in fenced/inline code are consistently excluded from both coercion discovery and rewriting, and `compile_one` still re-runs schema validation after coercion before entering the semantic gate. I found no production-code regression or scope creep. Gate 4 is not yet strong enough to serve as the Phase-5 comparison-cohort anchor, however, because the new tests do not prove three contracts they claim to prove.

## (a) Corpus correctness & completeness

### F1 — [Severity: Medium] · `tests/fixtures/wikilink_parity/cases.json:37` · the corpus does not guard the coerce behavior that Phase 4 changed

The independently recomputed expected outputs are correct for all 12 cases, and the case roster covers the blueprint's named surface forms, including heading+display, uncoercible space, uppercase fold, and an unclosed token. The protected-token cases are nevertheless ineffective against the regression that motivated the production edit:

- `escaped`, `fenced-code`, and `inline-code` use the already-valid target `aapl` (`cases.json:37-58`).
- `coerce_slugs_and_propagate` therefore builds no rename for those tokens, so both the pre-fix implementation and the new implementation leave them unchanged.
- The coerce assertion at `compiler/tests/test_wikilink_parity.py:39-49` consequently cannot distinguish "token was correctly excluded" from "token was scanned/rewritten but happened to map to itself."

I reproduced this directly by running an exact local simulation of the pre-fix regex/scanner/rewriter against the corpus: the old implementation passed all 12 `expected_body_coerce` and `changed` expectations. Reverting the production fix would therefore leave the advertised parity suite green.

Suggested change: make the protected-token cases force a real rename. For example, place `[[AAPL]]` or `[[Foo--Bar]]` both inside the escaped/code region and in ordinary prose, then pin that only the ordinary token becomes `[[aapl]]` / `[[foo-bar]]`. Add direct cases showing that (1) an uncoercible token found only in code does not block a legitimate page-slug repair and (2) a code-only collision does not trigger collision refusal. A malformed heading+display case would also pin preservation during an actual coerce rewrite rather than during a no-op. The acceptance check should be that the pre-fix implementation fails these cases.

No other corpus expectation error found.

## (b) Coerce behavior-change audit

No production flaw found.

- Ignoring a malformed value that occurs only in code can change a prior retry/quarantine into a successful coercion of a real page/link slug. That is the intended result once code-span text is classified as non-link syntax.
- Ignoring a code-only collision is likewise consistent with the authority set: collisions among non-links must not veto a valid repair.
- The negative lookbehind now leaves `\[[...]]` byte-identical, matching both extractors and the canonicalizer.
- `compiler/compiler.py:407-428` still invokes coercion only after a schema failure, re-validates the mutated payload at `:418-421`, and proceeds only when that second schema result is clean. The semantic gate remains after it at `:441-475`.

The missing regression evidence for these behaviors is F1.

## (c) System-test soundness (live-vs-rebuild / replay)

### F2 — [Severity: Medium] · `kdb_graph/tests/test_rebuilder.py:946` · the three-way equality test bypasses two of the boundaries it claims to prove

The test proves equality among in-memory page bodies interpreted by the graph extractor, direct graph intake, and a direct rebuild. It does not prove **persisted final wiki body = production live graph = rebuilt graph**:

- The "live" path calls `GraphDB.apply_compile_result` directly with its default immediate wiring at `:975-978`. Production orchestration instead applies each source with `wire_links=False` and later calls the batch `wire_links` finalizer (`orchestrator/kdb_orchestrate.py:129-135, 187-204`).
- The "wiki-body" side at `:995-1001` iterates the original Python dictionaries and calls `kdb_graph.intake.body_wikilink_slugs`; it never invokes `page_writer.apply`, reads a persisted Markdown page, or crosses the frontmatter/body serialization boundary.
- Rebuild is fed two independently written journals at `:1003-1010`, while a production orchestrator batch persists its combined compile result after deferred finalization. This does not exercise `_combine_crs` or batch wiring.

The explicit edge set does correctly pin heading/display positives and escaped/inline-code negatives. In particular, the escaped negative has an existing target and would fail if intake counted it; the inline-code regression is also caught by the explicit/body-edge assertions. The defect is integration depth, not those expected edges.

Suggested change: place the D-115-10 system test at an orchestration-capable boundary and exercise the real sequence: persist pages through `page_writer`, apply per-source graph state with deferred link wiring, run the accumulated batch finalizer, write/replay the same combined journal, then read the persisted wiki bodies and compare their extracted edges with both graph states. Include a forward cross-source link whose target is introduced later so deferred batch wiring is load-bearing. Keep the current parser-level tests as fast unit coverage.

### F3 — [Severity: Low] · `tools/tests/test_response_replay.py:100` · the legacy-negative test does not pin the stated `additionalProperties` cause

The fixture currently rejects at the intended gate: my probe returned `schema: [$] Additional properties are not allowed (...)`, and semantic evaluation short-circuits. The test at `:105-112` asserts only the generic `schema:` prefix, however. It would remain green if the fixture later became invalid for an unrelated schema reason, weakening the intended historical-response classification.

Suggested change: additionally assert `Additional properties are not allowed` and a representative removed top-level key present in the first schema detail (for example `summary_slug` or `source_name`). If page-field classification also matters, inspect the full validator error list and separately pin `outgoing_links`. The fixture-list and CLI `4/4` updates are otherwise correct.

## (d) Coverage claims & scope

### F4 — [Severity: Medium] · `kdb_graph/tests/test_rebuilder.py:909` · no identical old/new journal pair is proven through both rebuild and `kdb-validate`

The existing mixed-pair test does rebuild one legacy-style and one body-derived payload, but its validation precondition is performed on altered copies:

- `_fixture_backed` removes `compile_meta` at `:916-921` before validation.
- The unmodified originals, containing the synthetic `{run_state, hash}` metadata, are written to the journal at `:926-929` and rebuilt.
- Those journal payloads are not valid aggregate sidecars under the current schema; their `compile_meta` objects contain disallowed fields and omit required provider/model/token/latency/attempt fields.
- The nominal new payload is produced by `kdb_graph.testing.make_compile_result`, which also adds deprecated top-level `warnings`, so it is not a clean new-writer aggregate shape.

The other cited evidence does not close this exact gap. The Gate-3 mixed corpus rebuilds both shapes, but both stored compile results have the same schema-invalid synthetic `compile_meta`. `tests/fixtures/compile_result.minimal.valid.json` is a valid historical sidecar and is exercised through the `kdb-validate` CLI, but it is not one of the artifacts rebuilt by the mixed-journal test. Thus rebuild compatibility and validator compatibility are each covered, but not for the same old/new artifacts as D-115-14's cross-boundary claim requires.

Suggested change: construct one genuinely historical and one genuinely new compile result that are schema-valid exactly as written (either omit fixture-only `compile_meta` or supply the full production shape; omit all deprecated fields from the new result and use `compilation_notes` if needed). Write those exact objects as journal sidecars, load/validate the bytes from disk through `kdb-validate` or its shared API, then rebuild those same files and assert both legacy stored-link and new body-derived edges.

No scope-creep finding: production changes are confined to `compiler/repair.py`; there is no Phase-5 cohort machinery, #116 lifecycle work, or modification to canonicalization/intake/snapshot behavior. Package-boundary tests remain green.

## Verification performed

- Independently recomputed all 12 corpus cases: current expected slug sets and both rewrite bodies are correct.
- Pre-fix coerce simulation against the new corpus: all 12 cases passed, confirming F1.
- Focused Gate-4 and adjacent regression bundle: **162 passed**.
- Deterministic full suite (`-m 'not bench and not live'`): **1435 passed, 1 skipped, 2 deselected**.
- Package-boundary guard: **9 passed**.
- `git diff --check HEAD`: clean.

## Bottom line

The coerce implementation itself appears safe, and replay classification and graph edge expectations behave correctly. I would not commit this as the clean Gate-4/Phase-5 anchor yet: first make the parity corpus fail under the old coerce behavior, replace the in-memory/direct-intake equality check with a persisted-wiki plus production-finalizer system path, and validate the exact mixed sidecars that are rebuilt. F3 is a small assertion-hardening item and can be folded into the same correction. After those changes and a green deterministic suite, the phase should be suitable for `GO`.
