# Task #122 — Event-Time Context Capture (blueprint v0.5)

**Date:** 2026-07-24 · **Status:** v0.5 — absorbs Codex blueprint R4 (1 Important + 2 Moderate + 1 Minor, all verified). Codex R4: "ready for APPROVE / Joseph's Proceed without another architecture-options round." **Awaiting Joseph's Proceed**
**Architecture:** options v1.3 (ratified) + D-122
**Reviews:** blueprint R1 → `…-blueprint-review-codex.md` · R2 → `…-blueprint-review-codex-v2.md` · R3 → `…-blueprint-review-codex-v3.md` · R4 → `…-blueprint-review-codex-v4.md`

## 0. Codex R3 dispositions

| R3 finding | Disposition |
|---|---|
| F1 — `finalize_ran=False` ≠ unchanged graph | **Absorbed (§7):** verified `kdb_orchestrate.py:141-149` — graph sync precedes the manifest boundary; `manifest_post_graph` leaves `graph_committed=True` with finalize skipped. Contract now says "unfinalized," never "unchanged" |
| F2 — stale `compile_result.json` packaging | **Absorbed (§7b):** verified `emit_kpis.py:159-174` copies it + wiki unconditionally; packaging branches on `finalize_ran`; sentinel regression test |
| F3 — type ellipses | **Absorbed (§1):** `ContextRecordV1` fully enumerated; factory/parser state invariants frozen; shared Literals in `common.types` |
| F4 — raw score-boundary validation | **Absorbed (§7c):** dict-level rule (missing→True, non-bool→reject, False→skip) at the CLI and on pointer re-reads |
| F5 — test placement | **Absorbed (§8):** pure record tests beside `compiler/context_record.py`; filesystem/reconciliation tests beside the orchestrator; all-complete-later-failed case restored |

## 1. Data types

**`common/types.py`** (leaf) — shared vocabulary + builder payloads:

```python
KeyDisposition = Literal["unresolved", "resolved_t2_seed", "resolved_already_t1",
                         "resolved_out_of_scope", "resolved_duplicate_seed"]
ConfiguredT2Mode = Literal["structured", "layered", "legacy"]
EffectiveT2Strategy = Literal["structured_keys", "explicit_empty", "legacy_regex", "layered_union"]

@dataclass(frozen=True)
class KeyOutcome:
    key: str
    disposition: KeyDisposition
    resolved: str | None
    target_first_run_id: str | None

@dataclass(frozen=True)
class TierRecord:
    candidates: int
    delivered: int
    slugs: list[str]              # ALL delivered slugs, prompt rank order

@dataclass(frozen=True)
class ContextTelemetry:           # builder-owned — NO run_id, NO schema metadata
    source_id: str
    configured_t2_mode: ConfiguredT2Mode
    effective_t2_strategy: EffectiveT2Strategy
    keys_emitted: list[str]
    key_outcomes: list[KeyOutcome]
    t1: TierRecord
    t2: TierRecord
    t3: TierRecord
    candidate_universe_size: int
    domain_scope: str | None
    cold_start: bool
    max_hops: int
    page_cap: int

@dataclass(frozen=True)
class ContextBuildResult:
    snapshot: ContextSnapshot     # prompt-facing — unchanged
    telemetry: ContextTelemetry   # persistence-facing — never serialized into the prompt
```

**`compiler/context_record.py`** (new — persistence + evidence; `compiler`'s allowed imports are `{common, kdb_graph}`, importable by orchestrator + kpi without inversion):

```python
CONTEXT_RECORD_SCHEMA_VERSION = 1
ContextStatus = Literal["complete", "context_failed"]     # persistence-local

@dataclass(frozen=True)
class ContextRecordV1:
    schema_version: Literal[1]
    run_id: str
    source_id: str
    status: ContextStatus
    configured_t2_mode: ConfiguredT2Mode
    effective_t2_strategy: EffectiveT2Strategy
    keys_emitted: list[str]
    key_outcomes: list[KeyOutcome]
    t1: TierRecord
    t2: TierRecord
    t3: TierRecord
    candidate_universe_size: int | None
    domain_scope: str | None
    cold_start: bool | None
    max_hops: int | None
    page_cap: int
    # .to_dict() is the ONLY serialization path

@dataclass(frozen=True)
class ContextFailureInput:
    source_id: str
    configured_t2_mode: ConfiguredT2Mode
    effective_t2_strategy: EffectiveT2Strategy   # derived from mode + frontmatter, pre-graph-read
    keys_emitted: list[str]                      # Pass-1 frontmatter keys (known pre-build)
    domain_scope: str | None
    page_cap: int

@dataclass(frozen=True)
class ContextIntegrityIssue:
    path: str
    reason: Literal["malformed", "wrong_run"]
    detail: str

@dataclass(frozen=True)
class ContextLoadResult:
    records: list[ContextRecordV1]
    issues: list[ContextIntegrityIssue]

@dataclass(frozen=True)
class ContextIntegrity:
    missing: int
    malformed: int
    duplicate: int
    unexpected: int
    wrong_run: int
    expected_count_mismatch: bool

@dataclass(frozen=True)
class ContextEvidence:
    records: list[ContextRecordV1]
    expected_ids: set[str]
    matched_ids: set[str]
    coverage: float | None           # None when expected empty
    complete: bool                   # requires bool(expected_ids) — never vacuous
    integrity: ContextIntegrity

def build_context_record_v1(*, run_id: str, status: ContextStatus,
                            telemetry: ContextTelemetry | None = None,
                            failure_input: ContextFailureInput | None = None) -> ContextRecordV1
def parse_context_record_v1(raw: dict) -> ContextRecordV1   # strict — rejects, never coerces
```

**Factory state invariants (invalid combos raise, never guess):**

```
complete:        telemetry required; failure_input forbidden;
                 candidate_universe_size / cold_start / max_hops non-null
context_failed:  telemetry forbidden; failure_input required;
                 candidate_universe_size / cold_start / max_hops null;
                 zero tiers; empty key_outcomes
```

The strict parser enforces **both** sides (a `complete` record with null observables rejects; a `context_failed` record with non-null observables rejects).

## 2. `kdb_graph/queries.py` — ONE row classifier, two query shapes (P1)

- Both query shapes return **neutral resolution rows** — the batch Cypher drops its `CASE`, same row shape as the simple query.
- Shared **`classify_resolution_rows(rows) -> dict[str, tuple[str, str | None]]`** — precedence (`canonical_id` active > `ALIAS_OF` active > direct leaf active; dead targets fail-closed) + per-path stamp selection, exactly once. **Empty `first_run_id` → `None` here** (parser rejects an empty persisted stamp — normalization at construction, never at load).
- Public: `resolve_to_canonical_slugs_with_provenance(_batch)` → `{raw: (canonical, first_run_id)}`; legacy pair → slug-only projections. Parity structural + pinned; simple ≡ batch by construction + pinned.

## 3. `compiler/context_loader.py` — two-product builder (P1)

- `build_context_snapshot` → `ContextBuildResult` (one production caller, `compiler.py:669`; tests updated). Prompt-facing behavior unchanged.
- **Disposition derivation** (per emitted key, in emission order; T1 set + pool in scope at `:89-104`):
  ```
  absent from resolution map              → unresolved
  canonical ∈ t1_slugs                    → resolved_already_t1
  canonical ∉ (pool − t1_slugs)           → resolved_out_of_scope
  canonical already seeded by earlier key → resolved_duplicate_seed
  else                                    → resolved_t2_seed (and seed it)
  ```
- **TierRecords:** `candidates` = pre-cap tier set size (`|t1|`,`|t2|`,`|t3|` at `:92-110`); `delivered`/`slugs` = post-cap, post-projection prompt pages per tier (`:112-142`), in rank order. Invariant pinned: `sum(delivered) == len(snapshot.pages) ≤ page_cap`. `candidate_universe_size` = `|pool|` — the domain-scoped pool (`_domain_pool(conn, domain) & active`) when the source has a domain, else all active entities (`:88-89`; before T1 exclusion).
- **Effective strategy mapping:** structured mode + non-empty keys (State B) → `structured_keys`; structured + explicit `[]` (State C) → `explicit_empty`; structured + no frontmatter (State A), or LEGACY mode → `legacy_regex`; LAYERED mode → `layered_union` (key dispositions recorded for the key-derived part; regex-derived slugs join T2 candidates without outcomes).
- **Empty-graph early return** (`:78-80`): full telemetry — every emitted key `unresolved` (outcomes present), zero tiers (`candidates: 0, delivered: 0, slugs: []`), `cold_start=True`, `max_hops` per the cold-start widening policy (2 when T1 empty and |T2| < `_MIN_SEED_THRESHOLD`, `:106-109`).

## 4. `compiler/compiler.py::compile_source` — record writer (P1)

- Success: `build_context_record_v1(run_id=ctx.run_id, status="complete", telemetry=…)` → `.to_dict()` → `atomic_write_json` to `state_root/runs/<run_id>/context/<safe_source_id>.json`.
- Builder-exception: `build_context_record_v1(run_id=ctx.run_id, status="context_failed", failure_input=ContextFailureInput(…))` → same writer → existing `failure_stage="context"` result unchanged.
- Caller-supplied snapshot path: no record. Write failure: warn-only. Once per source per run.

## 5. `orchestrator/emit_kpis.py` — strict loader + typed reconciliation (P2)

```
load_context_records(context_dir, expected_run_id) -> ContextLoadResult   # records + issues
reconcile_context_records(load_result, expected_ids, p2_attempted) -> ContextEvidence
```

**Strict v1 parser — rejects, never coerces:** missing/unsupported `schema_version`; missing/wrong-typed ids/enums; negative or bool-as-int counts; `complete` record whose `key_outcomes` don't align 1:1 with `keys_emitted`; `unresolved` with non-null target / resolved without one; `target_first_run_id` neither null nor non-empty str (**empty rejected**); `delivered != len(slugs)`; `delivered > candidates`; `sum(delivered) > page_cap`; either side of the §1 status invariants violated. Rejections become `ContextIntegrityIssue`s and **travel into reconciliation**.

**Reconciliation order (pinned):** authoritative expected signal IDs from Pass-1 sidecars → load+validate → duplicate/unexpected detection → matched set + coverage (`None` when expected empty) → count cross-check vs `header.p2_attempted` → `ContextEvidence`.

```
evidence_complete := bool(expected_ids) AND matched_ids == expected_ids AND zero integrity errors
```

**Frozen integrity diagnostics** (emitted even when aggregates are `None`): `context_integrity_ok` (`bool | None` — `None` when expected empty), `context_missing_record_count`, `context_malformed_record_count`, `context_duplicate_record_count`, `context_unexpected_record_count`, `context_wrong_run_record_count`, `context_expected_count_mismatch`.

## 6. `compiler/kpi/graph.py` — watched fields, unambiguous equations (P2)

**Execution branch (R4 F1 — skip, don't null-overwrite):** today's `compute_graph` eagerly executes every finalized graph-quality read (`:104-205`). The no-finalize path must **never execute those reads** — wasted work on ineligible metrics, querying a residual graph for discarded values, and a read failure could cost the audit artifact itself:

```python
compute_graph(conn, finalize_artifacts, *,
              finalize_ran: bool = True,
              pass1_search_keys: list[str] | None = None,
              run_id: str | None = None,
              context_evidence: ContextEvidence | None = None) -> dict
```

```
finalize_ran=True:   existing graph-quality reads + legacy metric unchanged;
                     compute/merge Task-122 context fields
finalize_ran=False:  do NOT execute finalized graph-quality or legacy-resolution
                     reads — emit their established keys as None;
                     compute Task-122 fields from context_evidence;
                     execute ONLY the unresolved-at-load resolver read for L/V
                     (and NO query when that population is empty)
```

Pin: monkeypatch an ordinary finalized graph-quality query to raise; run the no-finalize branch; prove the query was never called, Task-122 context/integrity values still emit, finalized graph fields are present as `None`, and the unresolved resolver is called only when unresolved evidence exists.

Over **complete** records only. `N` = all emitted keys; `R` = resolver hits at load; `L` = unresolved-at-load resolving on the post-run read; `V` = unresolved-at-load still unresolved:

```
R + L + V == N   (exact)
search_key_resolved_at_load_rate = R / N
search_key_late_resolution_rate  = L / N     # query population = unresolved keys;
search_key_never_resolved_rate   = V / N     # denominators = ALL emissions
pre_run + cohort + age_unknown == R (exact); their rates divide by N, sum to R/N
```

`N == 0` ⇒ key rates `None`; `N > 0` with zero numerator ⇒ `0.0`. Also: `context_t{1,2,3}_{delivered,candidates}_mean`, `search_key_t2_seed_rate` (pre-cap), `context_build_success_rate`, `context_explicit_empty_count`, `context_record_coverage`, §5 integrity fields. `evidence_complete == False` ⇒ substantive aggregates `None` (coverage + integrity still emitted). Legacy `entity_search_key_resolution` byte-identical.

## 7. No-finalize emission contract — the truthful lifecycle version (R3 F1/F2)

**`finalize_ran=False` means "the run did not complete the finalize boundary" — nothing more.** Graph state may be unchanged (all context builds failed), **residual** (`manifest_post_graph` on a source — graph sync precedes the manifest boundary, `kdb_orchestrate.py:141-149`), **partially committed** (earlier sources committed, a later one hit `manifest_post_graph`), or **partially finalized** (a `_finalize` exception after a mutation). Therefore **finalized-run graph quality is ineligible → `None`** — in every case. The score skip (§7c) is right under this stronger truth.

1. `--emit-kpis` writes an auditable `measurements.json` whenever Pass-1 produced expected signal IDs, **even without finalize**; the artifact records `finalize_ran: false`.
2. **Field-level policy:** `graph.scored` finalized-run quality fields → `None`; Task-122 event-time watched fields + integrity **retained**; finalized-run-dependent watched fields (`orphan_rate`, legacy `entity_search_key_resolution`) → explicitly `None`.
3. **Deterministic post-run read, accurately described:** the unresolved-key batch read **always runs**, reading the **actual post-run graph state** — complete, partial, or residual — solely to classify whether an event-time miss became resolvable later in the run. It never makes the artifact rankable and never redefines a load-time outcome. `R + L + V == N` holds.
4. `RunMeasurementHeader` gains `finalize_ran: bool = True` (stamped at `kdb_orchestrate.py:991`; historical headers missing it load as `True`).

### 7b. Packaging branches on `finalize_ran` (R3 F2)

`compile_result.json` is written only by `_finalize` and is stable top-level state (`emit_kpis.py:159-162` copies it unconditionally today — a no-finalize run would package a **previous** run's payload):

```
finalize_ran=True:   copy compile_result.json + wiki/ snapshot (as today)
finalize_ran=False:  copy run_state/ (incl. context/), measurement_header, report,
                     prompt snapshot, console log;
                     NO compile_result.json; NO wiki/ (the live tree is not this
                     run's finalized output)
```

`emit_run_kpis`'s docstring/comments updated (they currently assert finalize ran). Sentinel regression test: pre-seed `compile_result.json` + wiki with a prior-run marker, run no-finalize, prove neither is packaged.

### 7c. Score-boundary validation (R3 F4)

The combined score command reads `measurements.json` as a raw dict (`tools/benchmark/cli.py:386-430`), so the rule lives at that boundary:

```
missing finalize_ran   -> True (historical)
value is bool True     -> eligible
value is bool False    -> skip with printed notice (before any pointer update)
value is any other type -> reject the artifact as malformed
```

Applied both when incorporating new inputs **and** when re-reading persisted leaderboard pointers. If every supplied artifact is skipped and no eligible leaderboard entry exists → clear "no rankable finalized runs" outcome.

### 7d. Pass-1 board surfacing — explicit interface (restored per R4 F3)

- `tools/benchmark/cli.py`: extract the Task-122 watched fields per model from measurements — all `search_key_*`, `context_*` means/rates, coverage, and the §5 integrity diagnostics — → `build_pass_board(..., pass1_watched_by_model=…)`.
- `pass_boards.py::_build_row`: **explicit merge** (not the `_pass1` suffix filter) into Pass-1 `raw_values` for **ranked, partial, and measurements-fallback** rows.
- JSON and Markdown render from the same `raw_values`.
- Eligible artifacts only: `finalize_ran=false` inputs are skipped at the §7c gate before any pointer update — they appear in no board.

## 8. Test plan (TDD)

- **Record unit tests (`compiler/tests/test_context_record.py`):** factory state combinations (both valid, each invalid combo raises); exact serialization/round-trip; strict field/type/cross-field validation incl. both status-invariant sides; empty-stamp normalization at the classifier (never at parse).
- **Loader/reconciliation (`orchestrator/tests/test_context_records.py`):** filesystem loading; wrong-run/malformed issue capture (issues survive, no record); duplicate/unexpected/missing reconciliation; expected-ID matching; zero-expected.
- **Resolver:** `kdb_graph/tests/test_queries_context.py` + `compiler/tests/test_t2_resolver_parity.py` — neutral-row classifier per path; stamp correctness; projection ≡ legacy; simple ≡ batch.
- **Builder/capture (`compiler/tests/test_context_loader.py` + new `test_context_telemetry.py`):** every disposition incl. cap-pressure; modes; empty-graph telemetry; cold-start `max_hops=2`; tier invariant; **prompt identity — golden fixture frozen from CURRENT code BEFORE the builder change**, across structured/explicit-empty/legacy/layered/empty-graph (byte + hash).
- **Writer (`compiler/tests/test_compile_source.py`):** success record; synthesized `context_failed` (frozen shape, `None` observables); warn-only write failure; caller-supplied snapshot → no record.
- **Coexistence (`common/tests/test_measurement.py`):** context records present ⇒ strict load OK, original `pass2_records`, `pass2_malformed == 0`; header without `finalize_ran` loads as `True`.
- **Aggregation (`orchestrator/tests/test_emit_kpis.py`):** reconciliation cases; rate equations; `context_failed` in coverage not in means; late vs never; legacy unchanged.
- **No-finalize lifecycle (R3 F1/F2):** all-`context_failed` (unchanged graph) ⇒ `context_build_success_rate == 0.0`, graph scored `None`, score-skipped; `manifest_post_graph` on the first source (residual graph, no finalize) ⇒ audit evidence emitted, Task-122 fields retained, finalized graph KPIs `None`, score-skipped; one committed source + later `manifest_post_graph` (partial graph) ⇒ same; all-complete-but-later-failed (valid context evidence, no finalized output) ⇒ context metrics emitted, graph fields `None`, score-skipped; `_finalize` exception after a mutation if deterministically injectable ⇒ same; **packaging sentinel test** (prior-run `compile_result.json` + wiki never packaged).
- **Score boundary (`tools/benchmark/tests/test_score.py`):** missing/`false`-string/`0`/True variants per §7c; all-skipped ⇒ "no rankable finalized runs".
- **Boards (`tools/benchmark/tests/test_pass_boards.py`):** ranked + fallback rows carry the new fields (JSON + Markdown); skipped artifacts appear nowhere.
- **Event-time truth table:** pre-run → hit+pre_run; earlier-same-run → hit+cohort; empty-graph miss later created → late; absent post-run → never; missing stamp → `age_unknown`.

## 9. Phases (each suite-green; commit gate = Joseph per phase)

- **P1 — capture:** §1 types + factory/parser → §2 resolver (neutral rows + shared classifier) → §3 builder → §4 writer; **golden prompt fixture frozen FIRST**; record-level + prompt-identity tests. Baseline 1768.
- **P2 — aggregation + surfacing:** §5 loader/reconcile → §6 watched fields → §7/7b/7c emit-gate + packaging + score skip → boards; KPI reference docs + North Star milestone + `TASKS.md` closure.

## 10. Out of scope / risks

- No scored-KPI changes, no Borda, no production write-path changes beyond the `context/` sidecar.
- The batch resolver's Cypher `CASE` removal changes internals, not results — structural parity pins it.
- §7 creates a new audit-only artifact class (`finalize_ran: false`) — excluded at the score input gate; packaging can never inherit stale finalized output.
- Record schema v1 with `schema_version` enforced by the strict parser from day one.
