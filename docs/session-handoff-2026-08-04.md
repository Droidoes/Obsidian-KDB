# Session handoff — 2026-08-04

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ⏩ END OF SESSION — #123 P3a SHIPPED: semantic graph search is wired end-to-end; the first full-chain live run is Joseph's to fire

Six commits, all pushed to `origin/feat/123-semantic-graph-search` (P3a.5 docs land uncommitted
on top). Suite **3,102 passed** (exit 0 at the tip, P3a.4 gate). **No PR opened.**

Pass-1 → Pass-1.5 → Pass-2 is now one pipeline: per source, `compile_source` step 1 runs ONE
semantic graph search (`compiler/search_adapter.run_pass15` → the I/O-free `kdb_search` core),
and its products feed the context build directly. The deterministic PK/regex T2 seeding — the
mechanism #123 existed to replace — is **deleted whole** (owner ruling 2026-08-03: REPLACE, not
supplement).

```
63dd795  feat   P3a.0 — foundations (64K envelope, entity_first_run_ids, cost projection)
cd63019  feat   P3a.1 — pass-1.5 search adapter (unwired)
ca3d9bd  feat   P3a.2a — ContextRecordV2 types + factory + parser + writer (unwired)
59d930e  feat   P3a.2b — wire pass-1.5, delete PK/regex T2 seeding (REPLACE)
e6056a8  feat   P3a.3 — dispatching loader + KPI consumers on V2
128631b  feat   P3a.4 — pass-1.5 SearchPassMeasurement + board columns
```

Blueprint: `docs/superpowers/specs/2026-08-03-task123-p3a-blueprint-v0.3.md` (ratified). Every
phase TDD-gated: tests written RED first, production to green, full suite at each phase boundary.

---

## 1. WHAT P3A SHIPPED, phase by phase

- **P3a.0 — foundations.** The 64K output-token envelope on the pool entries (down from 128K
  max_output — the P3a seat ruling), `entity_first_run_ids` on the graph (the key-outcome
  recency read), and the pre-run cost projection
  (`docs/superpowers/specs/2026-08-03-task123-p3a-cost-projection.md`) that sized the arc at
  $2–$40 vault-scale and settled the selector seat on **qwen3.7-flash**.
- **P3a.1 — the adapter.** `compiler/search_adapter.py`: gates pre-Pass-1 sources, builds the
  `GraphSearchRequest` from Pass-1 frontmatter, runs `graph_search` with the run-level selector
  seat, persists **one search envelope per source** under `runs/<run_id>/search/` (warn-only
  write — a failed write never changes the source outcome), projects the §4.5 positional key
  outcomes. `kdb_search` stays I/O-free; the envelope serializer lives in the core, the write
  in the adapter.
- **P3a.2a/2b — ContextRecordV2 + the wiring.** `compile_source` step 1 is now exactly one
  `run_pass15`; its products (`t2_selection` / `t1_slugs` / `search_summary` / `key_outcomes`)
  flow straight into `build_context_snapshot` — **no `source_text`**. T2 = the selector's
  validated hits in selector order; T3 = always 1-hop; cold-start is telemetry only. Deleted:
  `T2Mode` (STRUCTURED/LEGACY/LAYERED), the regex slug/title-in-text matchers, the resolver
  wrappers, the cold-start 2-hop widening, and every test that pinned them. One V2 context
  record per source per run on BOTH step-1 outcomes (complete / context_failed); the search
  summary survives post-search failures via the exception channel (B8/B9).
- **P3a.3 — the reading side.** `parse_context_record`: one strict version-dispatching loader
  (V1 history + V2 current, unknown rejects); `emit_kpis` and every KPI consumer read through
  it; the KPI-time resolver read is removed. **All seven #122 `search_key_*` series are cut**
  (one rename, one per-key→per-hit re-baseline, three clean cuts per blueprint §4.6);
  `context_explicit_empty_count` re-sourced to `query_kind == state_c`; new series
  `search_stage2_budget_bound_rate`. The V2 rates are the search KPI now.
- **P3a.4 — the measurement channel (§4.7).** One `SearchPassMeasurement` per search, persisted
  as an additive `measurement` sibling key inside the existing search envelope (union +
  serializer untouched; the parser tolerates the key): calls/attempts (incl. no-response),
  lower-bound tokens + cost (unknowns counted, never zero-coerced), latency, per-stage splits.
  `RunMeasurementHeader` gains `searches_attempted` / `searches_written`, accumulated from each
  `CompileSourceResult` — `attempted − written` == envelope write failures exactly. Emit-time
  reconciliation: envelope-file count vs `searches_written` — mismatch warns (never silent), a
  malformed measurement fails the KPI emission safely. Both pass boards carry the `_pass1_5`
  diagnostic columns on `raw_values`; **no third ranked board**, and `effective_top_weights`
  gained an explicit `pass1_5` case (unknown scopes raise).

---

## 2. VERIFICATION STATE

- Suite **3,102 passed, exit 0** at the tip (`128631b`); 3,134 collected, 1 bench-deselected.
  Every phase verified green individually before the next opened.
- Branch `feat/123-semantic-graph-search` pushed through `128631b`; P3a.5 docs (this file, the
  North Star milestone, the AGENTS.md sweep, the TASKS.md row + amendment) are **uncommitted**.
- **No PR.** The merge gate is the live run below, not review.

---

## 3. DEVIATIONS ACCEPTED (on the record)

1. **`Pass15Outcome` extension (P3a.2b, post-ratification).** It carries
   `keys_emitted: list[str]` and `key_outcomes: list[KeyOutcomeV2] | None` beyond blueprint
   §4.1's outcome shape — §4.5 specified the projection but named no carrier. `None` = no
   search ran (pre-Pass-1 / replay), distinct from a searched-but-keyless State C's `[]`.
   Recorded in `docs/TASKS.md` under the #123 row.
2. **Adapter stage-name translation fix (P3a.3, found by the restored e2e test).**
   `SearchBudgetRecord.stage` now translates `kdb_search`'s short stage vocabulary
   (`thin`/`fat`) to `StageName` (`thin_selection`/`fat_selection`) at the adapter boundary —
   a P3a.2b defect the window-pinned lifecycle tests had masked.

---

## 4. OUTSTANDING — in order

1. **(a) THE SANDBOX FULL-CHAIN RUN — Joseph fires it.** `scripts/sandbox-run.sh` against
   `~/Obsidian/Vault-in-place-test-run`: the first ever live Pass-1 + Pass-1.5 + Pass-2 chain,
   doubling as the Pass-1 prompt-1.3.0 first live fire and the pre-vault smoke. **The gate is
   SPLIT:** **(A)** Pass-1 prompt-1.3.0 output inspected and accepted **BEFORE** **(B)** any
   pass-1.5 results are read. Do not collapse the two — #126 changed what `entity_search_keys`
   contains, and those keys are now the search's query expressions (load-bearing, not
   fire-and-forget).
2. **(b) Orphaned fixture — Joseph's deletion decision.** `tests/fixtures/context_golden_prompts/
   task122_golden_prompts.json` (27.5 kB) is orphaned: the tests that consumed it were deleted
   in P3a.2b's REPLACE sweep, and nothing references it (verified by grep). Left on disk
   deliberately — the delete call is the owner's.
3. **(c) The production graph is EMPTY.** `~/Obsidian/KDB/graph` was emptied for the P3a.0 cost
   projection — **the first real run populates it from zero**, which means every early search
   is a cold-start/abstain until the ontology accumulates. Expected, not a defect; the
   honest-empty-T2 path (selector_failure / abstain → compile continues cold) is the designed
   behavior and is test-pinned.

---

## 5. WATCH-FORS FOR THE FIRST LIVE RUN

- **Cold-start everywhere** (item (c) above): expect `abstain_empty_space` / thin expression
  sets early; T2 honestly empty and Pass-2 compiling cold is VALID, not a failure.
- **`thin fails ⇒ no fat` (D-123-G)** — no fallback exists; two bad thin responses end the
  search. Now unmasked at real scale.
- **Zero-key sources** (#126): a source may emit empty `entity_search_keys`; valid end-to-end,
  but unresolved-expression metrics go degenerate on them.
- **DashScope content-filter false positives** (`data_inspection_failed`) — the standing
  provider-level risk for vault-scale ingest.
- **The reconciliation surfaces**: `searches_attempted − searches_written` (header) vs envelope
  files on disk (emit) vs measurements identified (boards) — any drift warns rather than
  silently scoring.

---

## 6. WHERE THINGS LIVE

- Pipeline wiring: `compiler/search_adapter.py` (pass-1.5 boundary), `compiler/compiler.py`
  (`compile_source` step 1), `compiler/context_loader.py` (`build_context_snapshot` on the
  adapter's products).
- Persistence: `runs/<run_id>/search/*.json` (envelope + `measurement` key),
  `runs/<run_id>/context/*.json` (ContextRecordV2), `measurement_header.json`
  (`searches_attempted/written`).
- KPI/measurement: `common/measurement.py` (`SearchPassMeasurement` + loaders),
  `compiler/kpi/processing.py` (`compute_search_diagnostics`), `orchestrator/emit_kpis.py`
  (`payload["search"]` + reconciliation), `tools/benchmark/pass_boards.py` (board columns +
  completeness).
- North Star milestone entry: `docs/CODEBASE_OVERVIEW.md` 2026-08-04. TASKS.md #123 row updated
  with the re-baseline warning + the amendment record.
