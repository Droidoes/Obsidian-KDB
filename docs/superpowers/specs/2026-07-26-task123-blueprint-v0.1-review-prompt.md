# #123 — Blueprint v0.1: panel review prompt (codex, opus5)

Date: 2026-07-26 · From: Kimi (with Joseph) · Re: **#123 Semantic graph search — blueprint v0.1**

## What you are reviewing

`docs/superpowers/specs/2026-07-26-task123-semantic-graph-search-blueprint.md` — the Phase-2 blueprint implementing **spec v0.4 (RATIFIED)**: `docs/superpowers/specs/2026-07-25-task123-semantic-graph-search-spec.md` (R1 per-entry salvage, no deterministic machinery anywhere / R2 uniform pre-flight budget / R3 narrower gate / R4 always-two-stage; SD-1..SD-6 settled). The R3-ordered fixture already landed: `benchmark/truth/task123_search_snapshot_v1/` (163 identities + frozen excerpts + checksums + smoke test; commit `3d271e2`; full suite 1963 green).

The blueprint resolves every item spec §10 routed forward, as decision points **B1–B14** with recommendations (blueprint §13 is the compact table). Nothing is ratified yet — Joseph rules after your review.

## What we need from you

1. **Adversarial review of the blueprint against spec v0.4** — does any recommendation contradict a ratified ruling, quietly reopen a settled decision, or add machinery the spec doesn't sanction?
2. **Verify the checkable claims against the repo** before concurring. The load-bearing ones:
   - `graph_search`'s import surface is `common` only (caller materializes the space; text projection via `common/wiki_io.get_body`; selector via `common/call_model` + `common/call_model_retry`; route via `common/model_pool.resolve_models_json`) — hence B1's `kdb_search/` sibling package, imports `{common}`, one new row in `tools/tests/test_package_boundaries.py`.
   - Integration point: `compiler/compiler.py:700–735` (`compile_source` step 1, context build + warn-only `_write_context_record` precedent at `compiler.py:640`); `compiler/context_loader.py` T2Mode machinery (lines 59–68, 465–628) is the retirement surface; `compiler/context_record.py` V1 shape is what V2 evolves.
   - `.venv` has **no local tokenizer** (no tiktoken/sentencepiece/tokenizers) — hence B3's `ceil(utf8_bytes/4)` estimator (spec §7.2: "exact per-model tokenizer where available; otherwise bytes÷4").
   - Sizing table (blueprint §7) is measured from fixture v1: thin block 163 entities = 14,343 B (87 B/entity); fat M=150 = 101,102 B (674 B/entity); vault-scale thin whole-graph ~9,600 entities ≈ 835k B ≈ ~209k conservative tokens. Recompute if you doubt it — `benchmark/truth/task123_search_snapshot_v1/identities.json` + `excerpts/`.
3. **Rule on the open interpretations** (these are the places I stretched spec text into mechanics — if you disagree, say so specifically):
   - **B14, D7-gate reading:** blueprint phases P1–P4 (machinery, testable with canned/mocked selector outputs, zero live selector spend) proceed once the blueprint is ratified; every *live selector call* (truth-set experiments, cohort re-runs, vault ingestion) waits for Joseph's labels + numerical gates. Is this consistent with your adopted closing line ("no implementation, selector tuning, or vault ingestion crosses the D7 gate until steps 1–3 are complete") — codex, you wrote that line; does "implementation" there mean P1–P3 must also wait, or does it mean selector-exercising implementation?
   - **B14, State C:** pass-1 emits `entity_search_keys: []` explicitly ⇒ no selector call, empty T2 (preserves D-90-8's "honor the no-anchors judgment"). Alternative: run the search on summary+themes text anyway. Which?
   - **B14, thin-empty with N>M:** thin stage retains zero validated slugs over a space larger than M ⇒ honest empty result at `execution=thin_attempted`, fat skipped (zero evidence = spend-wasting no-op). R4 uniformity concern?
   - **B9, resolver retention boundary:** `kdb_graph.queries.resolve_to_canonical_slugs*` stay (used by `kdb_mcp/adapters.py:99` for tool-arg identity resolution; intake-time alias canonicalization is write-path identity). Joseph's ruling was "the deterministic resolver has no role anywhere in the *search* path." Is the identity-resolution/search boundary drawn correctly, or does the ruling reach further?
   - **B5, escaping:** 2-space-indent rule with column-0 delimiters vs switching the evidence block to a JSON array (rejected in the blueprint as a spec §2.1 amendment — do you agree it would be an amendment, and with the rejection?).
   - **B8, ContextRecordV2:** search summary inside the versioned per-source record + sibling byte-fidelity envelope; V1 parser retained for history; `configured_t2_mode`/`effective_t2_strategy`/resolution-provenance fields die with T2Mode; `key_outcomes` re-shaped to per-expression `matched|unresolved` + annotations, 1:1 with `keys_emitted`. KPI reads both versions; the #122 `never_resolved` series re-baselines on expression accounting. Any continuity break I'm missing?
4. **Anything the blueprint is silent on that it shouldn't be** — gaps, not just disagreements.

## Response format

- Verdict: **CONCUR / CONCUR-WITH-ITEMS / REVISE**, per decision point where relevant (e.g. "B1 concur; B8 concur-with-items: …").
- Numbered findings, each with: severity (load-bearing / minor), the repo evidence you checked, and the specific fix.
- If you verify a claim and it holds, say so explicitly — confirmation of the checkable claims is as valuable as catches.
- Keep it in a response doc; Joseph will carry it back (`…-blueprint-review-codex.md` / `…-blueprint-review-opus5.md`).
