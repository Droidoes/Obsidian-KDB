# Task #116 — Source-Lifecycle Convergence + Durability — DESIGN SEED (candidate, NOT ratified)

> **Status:** CANDIDATE design seed for #116 — this is the Task #115 blueprint
> **v1.7** text, archived verbatim after Codex R12's carve moved the
> reservation/MOVED/durability subsystem out of #115. It is **not** a ratified
> #116 architecture: the recovery model (write-ahead vs immutable commit
> bundles vs simpler) must be chosen against real-vault evidence per the #116
> ledger row and the North Star's simplicity rule. Archived 2026-07-21 after
> Codex R13 F1 (the untracked blueprint file had been overwritten in place;
> reconstructed from session history).

---

# Task #115 — Pass-2 Contract Revision — Implementation Blueprint (v1.7)

> Architecture basis: decisions D-115-1..15, spec v1.5 at
> `docs/superpowers/specs/2026-07-21-task115-pass2-contract-audit-findings.md`.
> Execute with superpowers:subagent-driven-development or executing-plans.
> Test runner: `.venv/bin/python -m pytest` (bare `pytest` for counts).
> **Every commit gate requires Joseph's explicit approval — no gate is
> automatic authorization.**

**Goal:** shrink the Pass-2 LLM contract to model-authored wiki data only —
`pages[]` (`slug`, `page_type`, `title`, `body`) + optional
`compilation_notes` — with Python owning identity, status, summary
identification, and graph-edge derivation; the system prompt moves to the
repo; `confidence` is logically deprecated.

**Revision history:**
- **v1.0** — initial blueprint.
- **v1.1** — Codex R5 absorbed (10 findings): no `outgoing_links`
  resurrection; pre-call expected-summary-slug; per-source post-canon
  invariant; commit chain + North-Star-first; fixture split; cascades;
  confidence inventory + snapshot bump; header ordering; prompt copy+hash;
  parity corpus.
- **v1.2** — Codex R6 absorbed (7 amendments): graph derivation moved INTO
  Gate 2; dual-mode aggregate validation; collision authority map; v6-loader
  dropped; repair stage deleted whole; `summary_page` mapping boundary;
  pinned Gate-2 baseline.
- **v1.3** — Codex R7 absorbed (6 amendments): `status` out of new
  aggregates (consumer defaults are the stamp); `SummaryReservationIndex`
  data flow; zero-call telemetry; centralized `expected_summary_slug`;
  `ParsedSummary` non-throwing; North-Star scope completed.
- **v1.4** — Codex R8 absorbed (2 High + 3 Medium + cleanup): MOVED
  lifecycle reconciliation on every outcome; post-canonical exact summary
  re-validation; zero-call assertion split; named graph query; zero-call
  telemetry writer + KPI semantics.
- **v1.5** — Codex R9 absorbed (3 High + 1 Medium): MOVED outcome/state
  table; matched replay pairs; occupancy-aware `summary_slug_state`;
  exactly-once observability.
- **v1.6** — Codex R10 absorbed (2 High + 2 Medium): restart-safe β
  recovery; reverse-reservation transitional-self; replay-visible NOISE;
  `--limit` resolved; archive write protocol.
- **v1.7** — Codex R11 absorbed (2 High + 1 Medium; 4th consecutive round
  inside the MOVED machinery): pending intent upgraded to a full
  write-ahead transaction record (exact manifest patch, graph-effect
  fingerprint, sidecar/journal payloads) with a FIVE-STATE startup
  recovery table (intent≠commit; clear only AFTER the eligibility journal
  is durable); NOISE moved from an invalid fake compiled source to a typed
  Python-owned `source_dispositions[]` lifecycle channel (validated,
  canonical/page-writer-exempt, intake stamps `no_graph_db`); journal
  version PINNED 2.2 → 2.3 with new compile-event kinds + adapter
  historical/new fixture tests.

**Sequencing contract (D-115-13):** North-Star docs commit → Phase 0 commit
→ baseline cohort → Gate 2 (Phases 1–2, incl. graph derivation + MOVED
lifecycle) → Gate 3 (confidence deprecation) → Gate 4 (parity/system tests)
→ comparison cohort from the clean Gate-4 HEAD. A run with
`release_version == "unknown"` or a dirty tree is not attributable.

**North-Star gate (before ANY implementation):**
`docs/CODEBASE_OVERVIEW.md` updated to the chosen end-to-end architecture —
body-only Pass-2 response + graph-owned edge derivation; canonicalization
rewrites body wikilinks (no edge-list projection); logical Entity-confidence
deprecation; repository ownership of the Pass-2 prompt (D-A2 reversal);
Python-owned `status` boundary (absent from new aggregates; consumer
defaults stamp `active`); Repair-stage deletion with the end-to-end stage
flow renumbered; MOVED lifecycle as an exactly-once mutation independent of
compile outcome. Own docs commit before Phase 0.

---

## Phase 0 — Provenance foundation (commit boundary 1)

### Task 0.1: Prompt moves to the repo (copy + verify, NOT filesystem move)

1. Copy `~/Obsidian/KDB/KDB-Compiler-System-Prompt.md` →
   `compiler/prompts/KDB-Compiler-System-Prompt.md` (bytes verbatim, defects
   intact — D-115-7 fixes come in Phase 1).
2. Assert the copy's SHA-256 equals the ratified anchor
   `dcfa3d1cd9c1e7c543527b5d4357ce46fb9f1e31a766a8127b8565942c11e12a`
   (pinned in the Gate-0 test).
3. `compiler/prompt_builder.py:60-66`: loader reads the packaged file,
   vault-path memoization dropped; explicit error if missing. Prove the
   rendered system prompt is **byte-equivalent** to the pre-switch load.
4. The vault file is retired **logically** (no longer read). Physical
   deletion is a separate operator cleanup after the comparison cohort,
   requiring Joseph's explicit approval.
5. `pyproject.toml:45-48`: package-data gains `compiler = ["schemas/*.json",
   "prompts/*.md"]`.
6. Test harnesses stop writing `<tmp>/KDB/KDB-Compiler-System-Prompt.md` —
   packaged prompt by default; an override hook only where a test genuinely
   needs prompt variation.
7. Benchmark runner: run-dir prompt snapshot re-pointed at the packaged
   file (Task #30 re-runnability contract preserved).
8. **Wheel smoke test** (offline-capable, `--no-deps`): install the built
   wheel into a scratch venv; assert `load_system_prompt()` returns the
   anchored bytes.

### Task 0.2: Run stamps (field-ordering safe)

- `RunMeasurementHeader` ALREADY carries required `pass2_prompt_version`
  (`common/measurement.py:173`) — never populated. **Populate it** from a
  code-owned `PASS2_PROMPT_VERSION` constant (`compiler/prompt_builder.py`,
  start `"2.0.0"`).
- Append `pass2_system_prompt_sha256: str = ""` AFTER `release_version`
  (line 180). SHA-256 of the loaded prompt text.
- `load_run_measurements` constructs via `RunMeasurementHeader(**header_data)`
  (line 212) — add normalization filling missing historical fields before
  construction. **Test by loading an actual pre-#115 header dict** (no SHA
  key), not only by constructing the dataclass.
- `release_version` (`common/version.py`) already anchors the commit.

**Gate 0 (Joseph's approval):** suite green; commit. Joseph fires the
**baseline cohort** (gpt-5.4-mini + deepseek-v4-flash) from this clean
commit.

---

## Phase 1 — LLM contract revision (schema + prompt + exemplar + gates)

### Task 1.1: `compiled_source_response.schema.json` rewrite

- `pageIntent` required: `slug`, `page_type`, `title`, `body` only (drop
  `status`, `outgoing_links`, `confidence` + their `$defs`).
- Top level: required = `pages`; optional = `compilation_notes`. Drop
  `source_name`, `summary_slug`, `concept_slugs`, `article_slugs`,
  `log_entries`, `warnings` (+ `sourceName`, `summarySlug`, `logEntry`
  `$defs`).
- Descriptions de-jargoned (D-115-8); summary-slug convention as prose on
  the slug field.
- Tests: new shape accepted; removed fields rejected; `compilation_notes`
  optional.

### Task 1.2: Prompt rewrite (repo-owned)

- Delete: §1 jargon paragraph, self-check source-id-space bullet, `status`
  rule + example occurrences, `source_name` echo rule, `outgoing_links`
  array + bidirectional rule, `log_entries` section, `warnings` bullet.
- Keep/add: wiki-native link instruction ("reference any page with
  `[[slug]]` inline"); `compilation_notes` bullet (thin-source escape valve
  preserved, renamed); summary-slug convention stated once.
- Fix D-115-7: line-1 `do youd#`; "manifest snapshot" → graph snapshot;
  "aborts the run" → quarantine-and-continue.
- Bump `PASS2_PROMPT_VERSION` in the SAME commit (content and version never
  drift).

### Task 1.3: `exemplar_response()` rewrite

- New shape (4-field pages, `compilation_notes`); pairing prose dies.
- Test: exemplar passes the new schema.

### Task 1.4: Pre-call slug derivation, collision preflight, semantic gate

- **One centralized helper:** `expected_summary_slug(source_id: str) -> str`
  (compiler-owned, pure) — pins `Path(source_id).stem` →
  `common/paths.slugify` → 112-char stem budget (trailing-hyphen handling)
  → typed error on empty/non-ASCII normalization. Reused by preflight, the
  semantic gate, aggregate validation, replay, and the CLI.
- **Collision preflight (pre-call):** the orchestrator builds a
  `SummaryReservationIndex` from the live `full_manifest` immediately before
  each `compile_source` call (bidirectional: `slug -> owner`,
  `source_id -> slug`), with MOVED lineage (`ScanEntry.previous_path` /
  MOVED `from -> to`) passed as an allowed predecessor. `compile_source`
  receives the index and performs the graph fail-closed consistency check
  via a NEW named helper in `kdb_graph.queries` (the North Star's single
  graph query API — NO raw Cypher in the compiler) returning an
  **occupancy-aware** value, NOT a bare owner list —
  `summary_slug_state(conn, slug) -> SummarySlugState(exists, page_type,
  supporting_source_ids)` — because `list[str]` collapses three materially
  different states to the same empty list (R9 F3). Truth table:

  | graph state at expected slug | manifest index | verdict |
  |---|---|---|
  | no Entity, slug unreserved | — | PASS (first compile) |
  | summary Entity, owner == this source | consistent | PASS (recompile) |
  | summary Entity, owner == allowed MOVED predecessor | consistent | PASS (move; Task 2.5 completes the transfer) |
  | distinct or multiple owners | any | REJECT (`failure_stage="validate"`) |
  | Entity exists, ZERO supporting sources (unowned) | any | REJECT — reclaiming an unowned summary is a separate explicit policy, never an empty-list accident |
  | NON-summary Entity occupies the slug (`Entity.slug` is the PK; `_upsert_entity` would retype it while page_writer leaves the old file) | any | REJECT |
  | manifest/graph disagreement (unexplained) | — | REJECT |

  `compile_source` returns `CompileSourceResult(failure_stage="validate", ...)`
  BEFORE the model call on any REJECT. Never retried.
- **Cross-store transitional rows (R10 F1):** two known non-ordinary states
  are RECOGNIZED, never rejected as "unexplained disagreement":
  - **failed move (transitional self):** the reservation index's REVERSE
    `source_id -> old_slug` mapping shows this source already reverse-reserved
    to its predecessor's old summary slug (destination owns the old slug and
    its SUPPORTS from the failed run; `last_compiled_hash` stale) and the
    expected new slug is absent → PASS; the compile then replaces the old
    SUPPORTS with the new pages.
  - **β residual (restart-unsafe by definition):** scan lineage names the
    predecessor, the manifest is still PRE-move, and the graph destination
    already owns the expected slug from the failed commit → do NOT run
    ordinary preflight; enter the Task-2.5 β-recovery path (below).
- **Zero-call telemetry (pinned):** preflight rejections persist exactly one
  quarantined Pass-2 record (`attempts=0`, `call_count=0`,
  `final_attempt_index=0`, zero tokens/latency,
  `failure_stage="validate"`), written via a SHARED compiler helper used by
  both the preflight return and `compile_one`'s `finally` block (so
  "exactly one record" is mechanical). KPI: the scored per-token quarantine
  formula is PRESERVED for cohort comparability (zero-token records don't
  enter the denominator; an all-zero-call run yields
  `quarantine_rate_pass2=None` as today); a new diagnostic
  `preflight_quarantine_count` makes the class visible. Tests: mixed
  normal/zero-call run and all-zero-call Pass-2 run.
- **Test assertion split (R8 F3):** REJECTING preflights (distinct owner,
  ambiguous graph, manifest/graph mismatch, invalid stem) assert zero model
  calls + the zero-call record; ALLOWED cases (same-source recompile,
  MOVED+CHANGED predecessor) assert preflight success + exactly one normal
  model call in integration tests. Reservation-index unit tests run
  model-free but don't replace call-through tests.
- **Semantic gate:** `semantic_check(payload, *, expected_summary_slug=...)`
  on every attempt: exactly one `page_type == "summary"` page AND its slug
  equals the expected value. Rule 1 (`source_name` echo) deleted.
- The expected value is NEVER injected into the prompt (Joseph's
  model-authorship decision stands).

### Task 1.5: `compile_one` rewiring — no removed field in any new payload

- `common/types.py`: `PageIntent` drops `confidence`, `outgoing_links`, AND
  `status` (`to_dict()` is `asdict`; consumer defaults —
  `page_writer._fm_for_page()` absent→`active`, intake
  `_DEFAULT_ENTITY_STATUS` — ARE the Python-owned stamp). `CompiledSource`
  drops `summary_slug`, `concept_slugs`, `article_slugs`. `CompileResult`:
  `warnings` → `compilation_notes`; `log_entries` dropped; `LogEntry`
  deleted. (Cleanup, non-blocking: delete the orphaned `PageStatus` /
  `Confidence` aliases if the final scoped search confirms no consumer.)
- `compiler/compiler.py`: assembly stops reading removed fields; the
  mutating `reconcile_body_links` step DELETED (pure extraction only where
  validation/telemetry needs it); `reconcile_slug_lists` deleted; empty
  `related_source_ids` stamping deleted; `log_entries` plumbing deleted.
- Return signature: drop the log slot — `(compiled_source | None,
  compilation_notes, error)`; orchestrator call sites updated;
  `_combine_crs` aggregates `compilation_notes` (`kdb_orchestrate.py:156-183`).
- `summary_page(source: Mapping) -> Mapping` helper — serialized-dict
  boundary (`page_writer.py:208-234`, `manifest_writer.py:282-297`), FAIL
  CLOSED on zero/multiple summaries.
- Tests: recursive assertion that NO new page/aggregate payload contains
  ANY of the six removed keys (incl. `status`); historical payloads with
  them still validate + rebuild (bridges Task 2.2).

### Task 1.6: `ParsedSummary` migration (D-115-15) — best-effort, non-throwing

- `warning_count` → `compilation_note_count`; drop `log_entry_count`,
  `source_id_echoed`; `outgoing_link_count` from bodies via the pure
  extractor. `summary_slug`: emitted ONLY when exactly one well-formed
  summary page is observable, else `None` — `build_parsed_summary()` runs
  from `compile_one`'s `finally` on EVERY parsed dict incl. rejected
  responses; its "never raises" contract (`resp_summary.py:15-20`) is
  preserved. Zero-summary, multiple-summary, and malformed-page tests
  through the real finally path.
- Loaders tolerant of historical records.

### Task 1.7: Raw-response fixture migration

- `compiler/tests/fixtures/pass2_recovery/*.txt`: migrate decoded payloads
  to the new shape **preserving carrier noise and recovery boundaries**;
  update `manifest.json` expectations.
- Retain a SMALL legacy-response subset whose expected outcome is schema
  rejection (explicitly labeled negatives).
- Historical AGGREGATE sidecars/journals stay old-shape untouched
  (D-115-14).

**Gate 1:** Phase-1 scope green; reviewed with Phase 2, no separate commit.

---

## Phase 2 — Canonicalize, aggregate contract, graph derivation, MOVED lifecycle

### Task 2.1: Canonicalize under body-authority + post-canon EXACT summary gate

- `compiler/canonicalize.py`: delete the `outgoing_links` UNION (410-418)
  and the slug-list remap (490-500); keep `supports_page_existence` union;
  canonical alias rewriting rewrites BODY wikilinks only.
- Hard-reject summary/non-summary cross-type merges via TYPED
  `CanonicalizationError`; `compile_source` catches it and returns
  `CompileSourceResult(failure_stage="canonicalize", ...)`.
- **Per-source invariant, BOTH parts, BOTH sides of canonicalization
  (R8 F2):** for EVERY `compiled_sources[i]`, exactly one
  `page_type == "summary"` page **and its slug equals
  `expected_summary_slug(source_id)`** — checked pre-canon (Task 1.4
  semantic gate) AND re-checked immediately after `canonicalize.run()`,
  BEFORE page_writer / manifest / graph intake. A summary→summary alias
  singleton that would rename the summary page past the gate raises the
  typed `CanonicalizationError` (quarantine, no writes). Tests:
  summary→summary alias rejection, summary→concept alias rejection,
  losing-body link loss pinned, per-source invariant post-canon.

### Task 2.2: Aggregate validation — DUAL MODE (legacy-aware)

- `compile_result.schema.json`: removed fields become OPTIONAL,
  deprecated-annotated, read-only; `compilation_notes` added.
- `compiler/validate_compile_result.py`: dual-mode summary validation —
  LEGACY (top-level `summary_slug` present): existing referential +
  page-type checks (159-178); NEW (absent): derived expected slug via the
  Task-1.4 helper, exactly one summary page, exact equality. List-pairing
  checks (180, 248) deleted; `HARD_ZERO_FINDING_TYPES` + tests + stale docs
  updated. Separate assertions: NEW output omits ALL six deprecated keys
  (incl. `status`); HISTORICAL output with them validates (never copied
  forward).
- `tools/replay.py`: fixtures/cases migrate `source_name` → `source_id`;
  replay passes the derived expected slug into the semantic gate.
- `kdb-validate-response` CLI: `--source-name` replaced/supplemented by
  `--source-id`; omitted → schema-only validation (documented).
- `canonical_meta.outgoing_link_remaps` descriptions/stats → body-link
  remaps (historical field name retained for read-compat).

### Task 2.3: Repair stage — deleted whole, not just emptied

- Delete the #65 list fixers (`repair.py:80-153`) AND the finding-driven
  dispatch: `_RULES`, `repair()`, `ReconcileAction`, `RepairError`, the
  compiler's `failure_stage="repair"` branch (`compiler.py:692-700`), and
  their tests/types.
- Keep: `coerce_slugs_and_propagate` (page `slug`/body wikilinks only; drop
  the top-level `summary_slug` target, line 219) and the pure body-wikilink
  extractor.

### Task 2.4: Graph-owned edge derivation (Gate-2 blocker)

- Mirrored `body_wikilink_slugs` helper in `kdb_graph`.
  `_replace_outgoing_links` (`intake.py:309-344`): legacy `outgoing_links`
  key preferred when present; new-shape pages derive from body. The
  delete-then-recreate contract is unchanged — only the target-set source
  changes.
- Minimum integration tests (IN Gate 2): new-shape body links become
  LINKS_TO edges; legacy payload uses the stored list; recompile of a
  body-only page does NOT erase its edges; `wire_links` finalization
  (`kdb_orchestrate.py:128-133,186-203`) covered.

### Task 2.5: MOVED lifecycle — exactly-once reconciliation on EVERY outcome (R8 F1, R9 F1/F2/F4)

The reservation preflight (Task 1.4) makes this load-bearing: today
`_commit_source` builds `to_reconcile: []` (`kdb_orchestrate.py:90-133`),
`_commit_source_failure` does the same (361-389), and the reconcile queue
skips MOVED ops whose destination was in `to_compile` regardless of outcome
(872-878) — so the graph MOVED reconciliation (`intake.py:63-75,174-229`)
never runs on the live path. Success → double ownership (next preflight
fails); failure → manifest moved, graph not (guaranteed disagreement);
rebuild diverges (archived scan DOES contain the MOVED op).

**Outcome/state table (R9 F1) — every conductor branch for a MOVED source
that is also in `to_compile`:**

| branch | graph mutation | manifest mutation | prior SUPPORTS | move handled when | retry behavior |
|---|---|---|---|---|---|
| Pass-2 compile SUCCESS | MOVED op rides the `_commit_source` txn: create destination Source, transfer/mark predecessor, then replace destination SUPPORTS with new pages | moved entry + tombstone | transferred, then replaced by new compile | graph txn commits | n/a (committed) |
| preflight REJECT (validate) | move-only txn: transfer predecessor state to destination | moved entry + failure record, `last_compiled_hash` preserved | transferred (predecessor's usable state preserved under destination) | move-only txn commits | next run sees consistent manifest+graph; source compiles normally |
| Pass-1 failure / Pass-2 model/schema/canonicalize failure | same move-only txn | same as above | transferred | move-only txn commits | same convergence |
| Pass-1 classifies destination as NOISE | move-only txn; noise disposition rides the TYPED lifecycle channel (below) so live and adapter both zero the destination's SUPPORTS and stamp `ingest_state=no_graph_db` | noise record | transferred then retracted to zero | noise commit | n/a |
| page-apply failure (post-compile) | move-only txn (separate from the rolled-back page/graph txn) | moved entry + failure record | transferred | move-only txn commits | recompile retries cleanly |
| graph-sync failure (rollback) | NO move mutation (rolled back atomically) | unchanged | unchanged | — | full retry re-attempts compile + move |
| manifest-post-graph failure (β residual, run-fatal) | move already committed with the source txn — recovery is RESTART-SAFE (below), never an in-memory flag | retry completes manifest only | already transferred | durable pending-commit record cleared | idempotent — no second count/event/move |
| `--limit` leaves the move unprocessed | processed in the CURRENT reconcile queue as a move-only transition (R10 F3 — chosen over deferral: the queue predicate keys on the handled-set, so "not visited because of limit" would otherwise reconcile immediately anyway; making it explicit keeps table/predicate/tests in agreement) + matched replay pair persisted | moved entry + tombstone | transferred | queue move-only txn commits | next run compiles from the transitional-self state |

**β recovery — write-ahead transaction record (R10 F1, R11 F1):** an
in-memory handled key dies with the abort, and a bare "pending intent" is
not proof the graph committed. The mechanism is a **write-ahead
transaction record** journaled BEFORE the graph transaction, containing:
prior-manifest fingerprint/precondition; the EXACT target manifest patch
(byte-reproducible — all inputs `build_source_state_update()` used:
post-embed hash/mtime, compiled source, prior manifest); graph-effect
fingerprint (destination Source, expected summary/SUPPORTS set, run_id,
MOVED lineage); replay sidecar paths/hashes + exact eligibility-journal
payload; and transaction kind (`compiled_move` / `move_only_failure` /
`noise`). The record is cleared ONLY AFTER the eligibility journal is
durable (clearing after the manifest leaves a crash window where live
state is committed but replay can never discover it).

**Startup recovery classifies observed durable state — it never assumes β:**

| observed state | recovery |
|---|---|
| graph old, manifest old (intent only / rollback) | discard intent, retry normal work — manifest NEVER advanced |
| graph target, manifest old (true β) | apply the RECORDED manifest target byte-for-byte |
| graph target, manifest target, journal absent | publish the RECORDED eligibility journal |
| graph target, manifest target, journal present | clear pending record only |
| any partial/unrecognized combination | fail closed with a typed recovery error |

Fault-injection tests at ALL FIVE boundaries (after intent write, graph
commit, manifest write, journal write, pending cleanup), each in a fresh
process; the graph-rollback case must prove the manifest is not advanced.

**Second-run transitional state (R9 F1, R10 F1):** after a
rename-with-new-stem fails, the destination Source owns the predecessor's
SUPPORTS under the OLD summary slug and the manifest reverse-maps
`source_id -> old_slug`; `previous_path` is gone from the next scan. The
Task-1.4 cross-store row recognizes this via the reservation index's
reverse mapping; a two-run test proves convergence without collision or a
duplicate move.

**Typed lifecycle channel (R11 F2):** graph lifecycle dispositions are a
Python-owned aggregate channel, NOT fake compiled sources — the rejected
`{pages: [], retired: true}` shape violated the exactly-one-summary
invariant, `pages.minItems`, and intake's `retired` blindness. New top-level
`compile_result.source_dispositions[]` with a CLOSED shape
`{source_id, disposition: "no_graph_db"}`: consumed by intake AFTER MOVED
reconciliation (zero the destination's SUPPORTS, stamp
`ingest_state=no_graph_db`); EXCLUDED from summary/canonical/page-writer
rules and from the new-payload recursive-six-key assertion's summary
requirements; aggregate schema validates it; adapter rebuild consumes it
identically. Tests: the payload validates, writes no wiki page, leaves the
destination active+`no_graph_db`, and both predecessor and destination end
with zero SUPPORTS — through live intake AND adapter rebuild.

**Version pinning (R11 F3 — decided HERE, not at implementation):**
- `compile_result.schema.json`: additive optional `source_dispositions` +
  `compilation_notes` + optional-deprecated legacy fields → aggregate
  compatibility contract documented; historical artifacts validate
  unchanged (dual-mode, Task 2.2).
- Run journal (`state/runs/<run_id>.json`): version bumps **2.2 → 2.3** —
  new compile-event kinds (`compiled_move`, `move_only_failure`,
  `all_failure`, `noise`) with exact `success`/`replayable_payload`
  semantics per kind; the adapter reads 2.0/2.1/2.2 historically and 2.3
  going forward, with old+new journal fixture tests. The pending-commit
  record format is internal (not a replay contract) but versioned for
  forward compatibility.

**Replay durability + write protocol (R9 F2, R10 F4):** every run that
commits a graph lifecycle mutation — including move-only and all-failure
runs — emits a MATCHED replay pair (`last_scan.json` + a fresh
`compile_result.json`). The archive writer is a NAMED orchestrator helper
with crash-consistent ordering: per-run sidecars atomically → manifest
boundary → eligibility journal (`state/runs/<run_id>.json` compile event)
LAST, so rebuild never discovers a partial pair — and the pending-commit
record is cleared only after the journal is durable (R11 F1). Interruption
tests after EACH write boundary, plus failure tests through the ACTUAL
`ObsidianRunsAdapter` rebuild path (in-memory double-apply is not an
independence proof).

**Exactly-once observability (R9 F4):** one `sources_moved` event + one
count increment at the point the move becomes durable on every successful
handling path (compile path AND reconcile queue); none on rollback, retry,
or β recovery. The handled marker is an in-memory `(from_path, to_path)`
key for intra-run dedup only — durable state lives in the pending-commit
record and the stores themselves; the serialized `ReconcileOp` stays a
pure replay instruction.

**System tests:** MOVED+CHANGED success; preflight failure; model/schema
failure; noise classification (assert Source status/ingest state AND zero
destination SUPPORTS through the real adapter rebuild); graph-sync
rollback; β fault-injection across a process restart; renamed-stem
TWO-RUN convergence; limit-deferred move handled in the current queue.
Each asserts: predecessor marked moved, predecessor SUPPORTS removed,
destination owns the correct SUPPORTS, manifest ownership agrees,
`live graph == rebuild` through the real adapter.

- Note: this completes the MOVED lifecycle for the compile path; the
  broader #94 resume-correctness blocker (abort strands) is a SEPARATE
  scope and stays parked for WS3.

### Task 2.6: Fixtures

- New-shape per-source response fixtures + one old-shape and one new-shape
  aggregate journal pair (mixed rebuild coverage).

**Gate 2 (Joseph's approval):** full suite green — INCLUDING Task 2.4's
graph integration tests and Task 2.5's MOVED convergence tests; commit
Phases 1–2 as ONE contract commit. (This HEAD is runnable: recompiles
preserve links; moves converge.)

---

## Phase 3 — Confidence deprecation (logical) + snapshot v7

### Task 3.1: Complete write/read inventory (D-115-12)

Entity/page-confidence writes stop at EVERY site:
- `kdb_graph/intake.py` Entity upsert (283-299) AND alias-Entity creation
  (595-603);
- `kdb_graph/ops/op_1_promote.py:307` (parked promotion path — ENTITY
  confidence, not the protected Claim-tier design);
- `kdb_graph/types.py` `Entity`, `queries.py` / `graphdb.py` row mapping,
  `verifier.py` comparison (77-82), `snapshot.py`;
- `kdb_mcp/models.py` `EntityCard` AND `kdb_mcp/adapters.py`;
- test helpers (`kdb_graph/testing.py`); final scoped sweep for viewer/CLI
  consumers.
Claim/Evidence computed-confidence fields (`schema.py:116-117`,
`core/belief_classifier.py`) are NEVER touched.

### Task 3.2: Snapshot format bump

- `SNAPSHOT_FORMAT_VERSION` 6 → 7: writer drops `confidence` from
  `entities.jsonl`; pinned in snapshot tests. Snapshot is WRITE-ONLY by
  design — NO v6 loader; v6 documented for a future reader. The executable
  D-115-14 path is journal REBUILD.

**Gate 3 (Joseph's approval):** suite green + executable pre/post
comparison: normalized rebuild artifact from a PINNED mixed-journal corpus
at the Gate-2 HEAD (fixture dir + exact rebuild command pinned in the
test); Gate-3 rebuilds the SAME corpus and diffs with ONLY Entity
confidence excluded — every node, edge, and other property identical.
Commit.

---

## Phase 4 — Cross-boundary parity + system tests

- **Parity corpus with TWO expected outputs per case** (extracted slugs AND
  post-rewrite body): plain / `|alias` / `#heading` / escaped / fenced-code
  / inline-code / duplicates / malformed — compiler extractor, coercion
  rewriter, canonicalizer, mirrored graph extractor. Test-only shared data
  does not violate the import boundary.
- Live-vs-rebuild LINKS_TO equality on a new-shape batch.
- Mixed historical+new journal rebuild (D-115-14).
- `tools/replay.py`: new-shape replay end-to-end; legacy-negative fixtures
  reject with expected classification.

**Gate 4 (Joseph's approval):** suite green; commit. This clean HEAD is the
comparison-cohort anchor.

---

## Phase 5 — Cohort validation (Joseph)

- Fire gpt-5.4-mini + deepseek-v4-flash from the Gate-4 HEAD (clean).
- Compare vs the Phase-0 baseline: quarantine/retry/recovery KPIs stable;
  graph-KPI deltas enumerated (not hidden) on canonical-collision cases;
  telemetry shows the `pass2_prompt_version` bump + distinct SHAs.
- Sign-off → closure: ledger row, Milestone Changelog, handoff; THEN the
  optional vault-prompt physical deletion (separate approval).

## Explicit non-goals

No GLM A/B (D-115-6). No physical Kuzu column removal (D-115-12). No
Claim-tier confidence changes. No `expected_summary_slug` prompt injection
(Joseph's (a)). No body-merge preservation of losing-body links (D-115-9).
No removed field (`status` included) materialized in new payloads. No v6
snapshot loader. No #94 abort-resume scope (MOVED lifecycle here is
compile-path-only, pulled in by the reservation preflight).

## Risk register

- **Behavior drift on live runs** — baseline/comparison cohort + stamps.
- **Read-compat holes** — dual-mode aggregate validation + old-shape
  sidecars + Gate-3 normalized rebuild diff.
- **Parser divergence** — two-output parity corpus across all four
  extraction/rewrite sites.
- **Prompt packaging miss** — anchor-hash test + offline wheel smoke.
- **Measurement loader breakage** — normalization + real old-dict load test.
- **Gate-2 link regression** — graph derivation INSIDE the contract commit
  + recompile-preservation tests.
- **MOVED non-convergence** — Task 2.5 outcome/state table + write-ahead
  record + five-state recovery + matched replay pairs (R8–R11).
- **Summary alias bypass** — post-canon exact re-validation (R8 F2).
