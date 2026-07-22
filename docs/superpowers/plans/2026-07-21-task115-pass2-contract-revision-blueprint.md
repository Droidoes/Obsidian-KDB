# Task #115 — Pass-2 Contract Revision — Implementation Blueprint (v1.10, DESCOPED)

> Architecture basis: decisions D-115-1..15, spec v1.5 at
> `docs/superpowers/specs/2026-07-21-task115-pass2-contract-audit-findings.md`.
> **Carve ratified by Joseph 2026-07-21 on Codex R12's staging recommendation:
> the reservation/MOVED/durability subsystem (v1.7 Tasks 1.4-preflight + 2.5)
> leaves #115 and becomes a follow-up task paired with #94.** v1.7 is
> preserved as that follow-up's design seed — four rounds of design work, not
> discarded effort.
> Execute with superpowers:subagent-driven-development or executing-plans.
> Test runner: `.venv/bin/python -m pytest` (bare `pytest` for counts).
> **Every commit gate requires Joseph's explicit approval.**

**Goal:** shrink the Pass-2 LLM contract to model-authored wiki data only —
`pages[]` (`slug`, `page_type`, `title`, `body`) + optional
`compilation_notes` — with Python owning identity, status stamping, summary
identification, and graph-edge derivation; the system prompt moves to the
repo; `confidence` is logically deprecated.

**Accepted temporary behavior (the carve's price):** cross-source
normalized derived-slug collisions (distinct sources whose
`expected_summary_slug` values coincide after normalization/truncation)
keep today's behavior — wiki pages
last-writer-wins, graph Entities co-owned. MOVED sources are unaffected
EXCEPT the narrow `MOVED ∩ to_compile` branch (reconcile-skip can leave
predecessor graph ownership behind; ordinary move-only transfer already
works). These are EXISTING behaviors, not new regressions; the exact-stem
semantic gate still catches model non-compliance per source. Global
summary-slug reservation and source-lifecycle convergence are explicit
non-goals until the follow-up (see §Follow-up).

**Revision history:**
- **v1.0–v1.7** — Codex R5–R11 absorbed; design grew to include the
  reservation/MOVED/durability subsystem (write-ahead records, occupancy
  preflight, `source_dispositions`, journal 2.3).
- **v1.8 (DESCOPED)** — Codex R12 + Joseph: subsystem carved out (paired
  with #94 for WS3, v1.7 as design seed). #115 returns to the ratified
  contract objective. R12's warnings preserved: #94 stays a pre-production
  blocker; the carve is NOT permission for a production vault rollout
  before the follow-up closes.
- **v1.9** — Codex R13 absorbed (3 blockers + 2 clarifications; verdict
  "carve correct, do not re-expand"): v1.7 design seed ARCHIVED at
  `docs/superpowers/specs/2026-07-21-task116-source-lifecycle-design-seed-v1.7.md`
  (candidate, not ratified); spec v1.6 carve addendum splits D-115-11
  (#115 per-source exactness / #116 cross-source reservation); cohort
  guard moved BEFORE the baseline and keyed on the fully normalized
  `expected_summary_slug` (not raw stems); zero-call stem-failure route
  pinned to `compile_one`'s telemetry seam; MOVED/WAL wording corrected
  (MOVED ∩ to_compile branch only; WAL is the v1.7 CANDIDATE, not a
  foregone deliverable).
- **v1.10** — Codex R14 absorbed (3 bounded residuals; verdict "ready for
  the North-Star/docs gate"): stem-error propagation pinned end-to-end
  (`FailureStage` Literal gains `"validate"`; inner-record and
  outer-result stages mapped + tested separately); spec metadata bumped
  to v1.6; remaining same-basename/duplicate-stem wording replaced with
  normalized derived-slug terminology.

**Sequencing contract (D-115-13):** North-Star docs commit → Phase 0 commit
→ baseline cohort → Gate 2 (Phases 1–2 contract commit) → Gate 3
(confidence deprecation) → Gate 4 (parity/system tests) → comparison
cohort from the clean Gate-4 HEAD. A run with `release_version ==
"unknown"` or a dirty tree is not attributable.

**North-Star gate (before ANY implementation):**
`docs/CODEBASE_OVERVIEW.md` updated for the CONTRACT changes only — body-only
Pass-2 response + graph-owned edge derivation; canonicalization rewrites
body wikilinks; logical Entity-confidence deprecation; repository-owned
prompt (D-A2 reversal); Python-owned `status` boundary; Repair-stage
deletion with stage-flow renumbering. NO MOVED/WAL architecture (carved).
Own docs commit before Phase 0.

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

### Task 0.3: Cohort collision guard (BEFORE the baseline — R13 F3)

- Group the pinned cohort corpus by the **fully normalized
  `expected_summary_slug`** value (slugify + 112-char stem budget — the
  same derivation Task 1.4 centralizes), scoped exactly as the future
  reservation policy will be scoped. Raw duplicate-STEM inventory is
  insufficient: distinct stems can collapse after normalization/truncation
  (`Foo Bar.md` vs `foo-bar.md`, long-stem truncation collisions).
- Report underivable stems as well. Persist with the baseline artifacts:
  source list / corpus fingerprint, derived-key groups, tool/algorithm
  version.
- If the production helper is not yet landed at Gate 0, use a spec-pinned
  read-only inventory script and add a Phase-1 equivalence test against
  the centralized `expected_summary_slug` helper.
- Recompute before Phase 5: same corpus, same zero-collision requirement.
- Zero collisions ⇒ the deferred reservation exposes the cohort to no
  known collision case. Any collision ⇒ stop and resolve before firing.

**Gate 0 (Joseph's approval):** suite green + Task 0.3 guard persisted
with zero collisions; commit. Joseph fires the **baseline cohort**
(gpt-5.4-mini + deepseek-v4-flash) from this clean commit.

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

### Task 1.4: Exact summary identity (model-facing, NO cross-store machinery)

- **One centralized helper:** `expected_summary_slug(source_id: str) -> str`
  (compiler-owned, pure) — pins `Path(source_id).stem` →
  `common/paths.slugify` → 112-char stem budget (trailing-hyphen handling)
  → typed error on empty/non-ASCII normalization. Reused by the semantic
  gate, aggregate validation, replay, and the CLI.
- **Pre-call derivation check — pinned route (R13 F4, R14):** the helper
  runs INSIDE `compile_one`, after telemetry state initialization and before
  prompt construction/model call. On an underivable stem: a typed
  validation failure is set on the response record (`failure_stage=
  "validate"`, `attempts=0`, zero tokens — via the existing
  `model_response=None` path in `build_resp_stats`, exactly one record via
  the `finally` block). The `FailureStage` Literal
  (`compiler/compiler.py:57-60`) gains `"validate"`. `compile_one` returns
  the typed error, which `compile_source` maps to
  `CompileSourceResult(failure_stage="validate")` — NOT the generic
  `"compile"` mapping (`compiler.py:666-675`); the inner-record and
  outer-result stages are pinned and tested SEPARATELY.
  Never retried, never spends API. (The graph context read happens first
  — acceptable; no outer telemetry seam needed.)
- Tests: exactly one response record, `attempts == 0`, zero token/cost
  totals, typed exception, inner `validate` + outer `validate` stages, no
  model call, no retry.
- **Semantic gate:** `semantic_check(payload, *, expected_summary_slug=...)`
  on every attempt: exactly one `page_type == "summary"` page AND its slug
  equals the expected value. Rule 1 (`source_name` echo) deleted.
- The expected value is NEVER injected into the prompt (Joseph's
  model-authorship decision stands).
- **OUT OF SCOPE (carved):** `SummaryReservationIndex`, occupancy queries,
  cross-store collision rejection, transitional/β states. Cross-source
  collision behavior is unchanged from today (§Goal's accepted temporary
  behavior).

### Task 1.5: `compile_one` rewiring — no removed field in any new payload

- `common/types.py`: `PageIntent` drops `confidence`, `outgoing_links`, AND
  `status` (`to_dict()` is `asdict`; consumer defaults —
  `page_writer._fm_for_page()` absent→`active`, intake
  `_DEFAULT_ENTITY_STATUS` — ARE the Python-owned stamp). `CompiledSource`
  drops `summary_slug`, `concept_slugs`, `article_slugs`. `CompileResult`:
  `warnings` → `compilation_notes`; `log_entries` dropped; `LogEntry`
  deleted. (Cleanup: delete orphaned `PageStatus`/`Confidence` aliases if
  the final scoped search confirms no consumer.)
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

## Phase 2 — Canonicalize, aggregate contract, graph derivation, compat

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

### Task 2.5: Fixtures

- New-shape per-source response fixtures + one old-shape and one new-shape
  aggregate journal pair (mixed rebuild coverage).

**Gate 2 (Joseph's approval):** full suite green — INCLUDING Task 2.4's
graph integration tests; commit Phases 1–2 as ONE contract commit. (This
HEAD is runnable: recompiles preserve links.)

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
- Live-vs-rebuild LINKS_TO equality on a new-shape batch — scoped to
  LIFECYCLE-NEUTRAL NEW/CHANGED cases (R13 F5); MOVED/fail-fast
  convergence belongs to #116/#94.
- Mixed historical+new journal rebuild (D-115-14).
- `tools/replay.py`: new-shape replay end-to-end; legacy-negative fixtures
  reject with expected classification.

**Gate 4 (Joseph's approval):** suite green; commit. This clean HEAD is the
comparison-cohort anchor.

---

## Phase 5 — Cohort validation (Joseph)

- Fire gpt-5.4-mini + deepseek-v4-flash from the Gate-4 HEAD (clean).
  Guard re-run first (Task 0.3): recompute the normalized
  `expected_summary_slug` groups on the SAME corpus — zero collisions
  required, result persisted with the comparison artifacts.
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
snapshot loader. **No global summary-slug reservation, collision preflight,
MOVED lifecycle machinery, write-ahead records, `source_dispositions`, or
journal 2.3 — all carved to the follow-up.**

## Follow-up task (#116, filed in the ledger)

**Source-lifecycle convergence + durability** (paired with #94, a
WS3-pre-production gate): global summary reservation + occupancy policy;
NEW/CHANGED/MOVED/DELETED + signal/noise/reactivation transitions; per-run
replay material + journal evolution; live==rebuild invariants; recovery
architecture chosen against real-vault evidence. **Design seed
(CANDIDATE, not ratified):** the v1.7 blueprint archived at
`docs/superpowers/specs/2026-07-21-task116-source-lifecycle-design-seed-v1.7.md`
— its write-ahead record + five-state recovery table are ONE candidate;
immutable commit bundles or a simpler model remain live alternatives to be
evaluated against R12's evidence list (normalized derived-slug collision
inventory, tombstone/move frequency, signal↔noise cases, interrupted-run
artifact shapes, live-vs-rebuild divergences), collected read-only during the
WS2/WS3 preflight. #94 stays a pre-production blocker; the carve is NOT
permission for production rollout before this closes.

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
- **Summary alias bypass** — post-canon exact re-validation (R8 F2).
- **Cross-source summary collision (accepted, temporary)** — today's
  behavior preserved; cohort guarded by the normalized derived-slug
  collision inventory (Task 0.3);
  closed by the follow-up task.
