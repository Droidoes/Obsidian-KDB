# Task #90 Context-loader T2-rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to drive task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Task #90 v0.2 — rewrite `graph_context_loader._t2_slug_in_text` to consume Pass-1's `entity_search_keys` as the primary T2-seeding signal, with three-mode dispatch (STRUCTURED / LAYERED / LEGACY), alias-aware resolver (simple 2-query default + Codex-tested batch escape hatch), and full backward-compat for pre-Pass-1 sources.

**Architecture:** Closes the Pass-1↔context-loader tunnel-meeting-in-the-middle. Pass-1 (shipped 2026-05-26) emits `entity_search_keys`; this task wires the consumer side. Pass-2's view of `ContextSnapshot` stays invariant.

**Tech Stack:** Python 3.10+, Kuzu GraphDB (no schema change), existing `parse_existing_frontmatter` (`kdb_compiler/ingestion/frontmatter_embedder.py:34`), pytest TDD throughout. Live API smoke gated via `pytest -m live` per `[[feedback_user_fires_api_cost_runs]]`.

---

## §0 — Plan setup, locks, sequencing rationale

### Locked decisions inherited (do not re-litigate)

From Task #89 v0.2.2 blueprint:
- **D-89-20** Input contract: `entity_search_keys` is the sole structured Pass-1→T2 signal; alias-aware lookup via direct PK + `canonical_id` + `ALIAS_OF`; Pass-2 view unchanged.

From Task #90 v0.2 blueprint (`docs/task90-context-loader-t2-rewrite-blueprint.md`):
- **D-90-1..D-90-4** Option A clean replacement + T2Mode mechanism + prompt-inlined + benchmark separate
- **D-90-5** Title-phrase widening (Task #71) survives on legacy branch only
- **D-90-6** No zero-hit fallback in v1 per `[[feedback_no_imaginary_risk]]`
- **D-90-7** Frontmatter plumbing via shared helper, `CompileJob` schema unchanged
- **D-90-8** `entity_search_keys=[]` honored as State C (empty T2; no fallback)
- **D-90-9** Simple 2-query resolver as v1 default; Codex-tested batch as escape hatch (`KDB_T2_RESOLVER=batch`)
- **D-90-10** Shared `kdb_compiler/source_io.py` module (fixes B-1 circular import + Gemini F-4 double-disk-read)
- **D-90-11** `T2Mode` enum stays in `graph_context_loader.py`
- **D-90-12** 3-part sunset gate (corpus 100% enriched + NW-9 cold-start ≥ + NW-9 precision ≥)

### Phase sequencing rationale

**Phase A (source_io.py) → Phase B (planner) → Phase C (loader rewrite) → Phase D (tests) → Phase E (live smoke).**

**Why A first:** B-1 fix (shared module) is foundational. Both planner (B) and compiler (existing) re-import from it. Doing A first lets B and the compiler-side `source_text_for` rewrite land as thin wrappers with zero behavioral change for the compiler.

**Why C after B:** Loader's new `build_context_snapshot` signature (adds `frontmatter`, `mode`) is invoked by planner. Wiring planner first means C's signature change has a known call site.

**Why D before E:** Live smoke (E) costs API credits. Unit + parity tests (D) catch nearly all regressions for free; E is the final ship-gate.

---

## §1 — File structure map

### New files (create)

```
kdb_compiler/
├── source_io.py                                    (NEW — D-90-10 shared module)

kdb_compiler/tests/                                 (EXISTING — add test files)
├── test_source_io.py                               (NEW — parse_source_file unit coverage)
├── test_t2_resolver_parity.py                      (NEW — simple vs batch parity, D-90-9 + Grok F-4)
├── test_t2_mode_dispatch.py                        (NEW — 3-state branch selector + T2Mode dispatch)
└── test_t2_end_to_end_pass1_path.py                (NEW — live smoke, Phase E)
```

### Existing files (modify)

```
kdb_compiler/
├── compiler.py                                     (line 107-137: SourceFrontmatter MOVES to source_io.py;
│                                                    line 156-171: source_text_for becomes thin wrapper)
├── planner.py                                      (line 83-92: retire _read_source_text in favor of
│                                                    source_io.parse_source_file; lines 95-130: thread
│                                                    frontmatter + mode + resolver through build_jobs)
├── graph_context_loader.py                         (add T2Mode enum + _build_t2 dispatcher +
│                                                    _t2_structured/_t2_layered/_t2_legacy +
│                                                    _resolve_to_canonical_slugs + signature change to
│                                                    build_context_snapshot)
└── tests/test_graph_context_loader.py              (parametrize existing tests with T2Mode.LEGACY)
```

### No changes to

- `compile_one` / `compiler.py` Pass-2 path (signature stable)
- `prompt_builder.py` (no compile-prompt amendment)
- `types.py` (`CompileJob` / `ContextSnapshot` schemas unchanged — D-90-7)
- `graphdb_kdb/` schema or ingestor (no GraphDB changes)
- `kdb_compiler/ingestion/` (Pass-1 producer unchanged; prompt amendment is Task #90 step prior to live smoke — see §6.A)

---

## §2 — Phase A: source_io.py shared module (D-90-10)

### A.1 — Create `kdb_compiler/source_io.py`

- [ ] Module docstring stating purpose: "Shared source-file I/O for kdb_compiler — owns `SourceFrontmatter` dataclass and `parse_source_file()`. Used by both `planner.py` (plan-time frontmatter read) and `compiler.py` (compile-time `source_text_for` wrapper). Fixes Bug B-1 (planner→compiler circular import) per D-90-10."
- [ ] Define `SourceFrontmatter` dataclass (relocated verbatim from `compiler.py:106-137`). Preserve all fields + `from_dict` classmethod + docstring + the D-89-20 reference comment.
- [ ] Define `parse_source_file(path: Path) -> tuple[SourceFrontmatter | None, str]`:
  - Reads file as UTF-8 (propagates `OSError` / `UnicodeDecodeError` — caller decides degrade vs raise per use case).
  - Calls `parse_existing_frontmatter(raw)` from `kdb_compiler.ingestion.frontmatter_embedder`.
  - Returns `(SourceFrontmatter.from_dict(fm_dict), body)` — `from_dict` returns `None` if required keys absent.
  - On YAML parse error inside `parse_existing_frontmatter`: returns `(None, raw_content)` — frontmatter malformed but body still exists (Pass-1's bug to fix, not ours).
- [ ] Module-level imports keep zero coupling to `compiler.py`, `planner.py`, `graph_context_loader.py`.

### A.2 — Migrate `compiler.py` references

- [ ] Remove `@dataclass class SourceFrontmatter` definition (lines 106-137).
- [ ] Add `from kdb_compiler.source_io import SourceFrontmatter, parse_source_file` at top of `compiler.py`.
- [ ] Rewrite `source_text_for(job: CompileJob) -> tuple[SourceFrontmatter | None, str]` as 1-line wrapper:
  ```python
  def source_text_for(job: CompileJob) -> tuple[SourceFrontmatter | None, str]:
      """Thin wrapper around source_io.parse_source_file for backward-compat."""
      return parse_source_file(Path(job.abs_path))
  ```
- [ ] Keep `_build_source_summary` in `compiler.py` (compile-side concern, not I/O).

### A.3 — Verify zero behavioral change at compiler boundary

- [ ] Run `pytest -m "not live"` (full suite). Expected: 1071 pass, 1 skip, 2 deselect — same as `main` post-#89-closure.
- [ ] Spot-check: `grep -rn 'from kdb_compiler.compiler import SourceFrontmatter' kdb_compiler/ graphdb_kdb/` — should return zero hits (all imports now via `source_io`).

### A.4 — Unit tests `test_source_io.py`

- [ ] Test `parse_source_file` on:
  - Pass-1 enriched file (all required keys present + `entity_search_keys` non-empty) → returns `(SourceFrontmatter(...), body)`
  - Pass-1 enriched file with `entity_search_keys: []` explicit → returns `(SourceFrontmatter(entity_search_keys=[], ...), body)` (State C)
  - Pre-Pass-1 file (no YAML frontmatter) → returns `(None, full_content)`
  - File with YAML but missing required keys → returns `(None, body_excluding_yaml)` per `SourceFrontmatter.from_dict` contract
  - Malformed YAML → returns `(None, full_content)` — body fallback
  - Missing file → raises `OSError` (does NOT degrade — planner wraps)
  - Binary file → raises `UnicodeDecodeError`

---

## §3 — Phase B: planner integration

### B.1 — Add env-var resolution helpers

- [ ] Add module-level `_resolve_t2_mode_from_env()` in `planner.py`:
  ```python
  def _resolve_t2_mode_from_env() -> "T2Mode":
      from kdb_compiler.graph_context_loader import T2Mode
      raw = os.environ.get("KDB_T2_MODE", "").strip().lower()
      if not raw:
          return T2Mode.STRUCTURED  # default per D-90-9
      try:
          return T2Mode(raw)  # str-valued enum: 'structured' / 'layered' / 'legacy'
      except ValueError:
          raise RuntimeError(
              f"KDB_T2_MODE={raw!r} is invalid. "
              f"Expected: 'structured' / 'layered' / 'legacy'."
          )
  ```
- [ ] Add `_resolve_t2_resolver_from_env() -> Literal["simple", "batch"]` — same pattern; default `"simple"` per D-90-9; invalid raises `RuntimeError`.

### B.2 — Retire `_read_source_text`; use `parse_source_file`

- [ ] Remove `_read_source_text` (line 83-92).
- [ ] Inside `build_jobs`, replace the per-source loop body:
  ```python
  abs_path = vault_root / source_id
  try:
      frontmatter, source_text = parse_source_file(abs_path)
  except (OSError, UnicodeDecodeError):
      # Plan-time degrade per existing convention (compile_one is the
      # authoritative read-fail gate). Empty context, no frontmatter.
      frontmatter, source_text = None, ""
  ```
- [ ] Import: `from kdb_compiler.source_io import parse_source_file, SourceFrontmatter`.

### B.3 — Thread frontmatter + mode + resolver through `_build_context`

- [ ] Resolve mode + resolver ONCE at `build_jobs` entry (not per-source — Deepseek OQ 2):
  ```python
  t2_mode = _resolve_t2_mode_from_env()
  t2_resolver = _resolve_t2_resolver_from_env()
  # ... per-source loop uses t2_mode + t2_resolver ...
  ```
- [ ] Update `_build_context` signature to thread `frontmatter`, `mode`, `resolver`:
  ```python
  def _build_context(
      conn, *,
      source_id: str,
      source_text: str,
      frontmatter: SourceFrontmatter | None,
      page_cap: int = 50,
      mode: "T2Mode" = None,        # default resolved by graph_context_loader
      resolver: str = "simple",
  ) -> ContextSnapshot:
      return graph_context_loader.build_context_snapshot(
          conn,
          source_id=source_id,
          source_text=source_text,
          frontmatter=frontmatter,
          page_cap=page_cap,
          mode=mode,
          resolver=resolver,
      )
  ```

### B.4 — CLI surface

- [ ] No `kdb-plan` CLI flag change for v1. Mode + resolver controlled by env vars only (per OQ-90-6 5/5 ratification). Future v1.1 may add `--t2-mode` / `--t2-resolver`.

---

## §4 — Phase C: graph_context_loader rewrite

### C.1 — Add `T2Mode` enum

- [ ] At top of `graph_context_loader.py`, define:
  ```python
  from enum import Enum

  class T2Mode(str, Enum):
      STRUCTURED = "structured"
      LAYERED = "layered"
      LEGACY = "legacy"
  ```
- [ ] Update module docstring to reflect T2Mode-mediated dispatch.
- [ ] Preserve the existing module invariant: loader does NOT read env vars (Codex F-5). All mode/resolver selection happens at planner.

### C.2 — Extend `build_context_snapshot` signature

- [ ] Add params `frontmatter: SourceFrontmatter | None = None` and `mode: T2Mode = T2Mode.STRUCTURED` and `resolver: str = "simple"`.
- [ ] Default `mode=STRUCTURED` makes existing callers (notebook / repl) work without changes when frontmatter is None (resolves to legacy branch).

### C.3 — Implement `_build_t2` dispatcher

- [ ] Add `_build_t2(conn, *, source_text, candidate_slugs, active_entities, cold_start, frontmatter, mode, resolver) -> set[str]` per §2.1 of v0.2 blueprint.
- [ ] Dispatch on `mode` to `_t2_structured` / `_t2_layered` / `_t2_legacy`.

### C.4 — Implement `_t2_structured` (D-90-8 three-state)

- [ ] Per §2.2 of v0.2 blueprint. Three-state branch:
  1. `frontmatter is None` → call `_t2_legacy(...)` (State A pre-Pass-1)
  2. `frontmatter.entity_search_keys` non-empty → call `_t2_from_search_keys(...)` (State B)
  3. Else (explicit `[]`) → return `set()` (State C — D-90-8 honor)

### C.5 — Implement `_t2_layered` + `_t2_legacy`

- [ ] `_t2_layered`: per §2.3 v0.2 blueprint. Note: LAYERED unions structured ∪ legacy even on State C.
- [ ] `_t2_legacy`: extract current behavior verbatim — wrap existing `_t2_slug_in_text` + `_t2_title_in_text` cold-start logic.

### C.6 — Implement `_resolve_to_canonical_slugs` (simple 2-query default)

- [ ] Per §3.3 v0.2 blueprint code listing. Two queries:
  1. Direct + canonical_id (with target.status='active' check — fixes B-2)
  2. ALIAS_OF for unresolved-after-Q1
- [ ] Defensive `.strip()` + empty-input drop per Qwen O-2.
- [ ] Returns `dict[str, str]` mapping `raw_slug → canonical_slug`; unresolved raws absent from dict.

### C.7 — Implement `_resolve_to_canonical_slugs_batch` (escape hatch)

- [ ] Per §3.4 v0.2 blueprint Cypher. Single-query CASE form Codex empirically tested on Kuzu 0.11.3.
- [ ] Same return contract as simple — parity test (D.1) asserts functional identity.

### C.8 — Implement `_t2_from_search_keys`

- [ ] Per §2.5 v0.2 blueprint — calls `_resolve_to_canonical_slugs` (mode-selected via `resolver` param) once per source; set-comprehension over returned dict values filtered by `candidate_slugs`.

### C.9 — Wire mode + resolver into `build_context_snapshot`

- [ ] Replace existing T2 construction (lines 57-62 of current `graph_context_loader.py`) with `_build_t2(...)` dispatch.
- [ ] Resolver selection: if `resolver == "batch"`, `_t2_from_search_keys` calls `_resolve_to_canonical_slugs_batch`; else `_resolve_to_canonical_slugs` (simple).

---

## §5 — Phase D: tests

### D.1 — Parity test `test_t2_resolver_parity.py` (D-90-9 + Grok F-4)

- [ ] Set up a fixture graph spanning ALL §3.1 paths + B-2 + Qwen Probe-2 cases:

  | Slug | status | canonical_id | ALIAS_OF target | Purpose |
  |---|---|---|---|---|
  | `value-investing` | active | NULL | — | Path 1 direct PK hit |
  | `warren-buffett` | active | NULL | — | Path 2 canonical_id target |
  | `wb` | active | `warren-buffett` | — | Path 2 canonical_id with active target |
  | `buffett` | active | NULL | `warren-buffett` | Path 3 ALIAS_OF edge |
  | `old-name` | active | `deprecated` | — | B-2: canonical_id, but target inactive |
  | `deprecated` | inactive | NULL | — | Inactive target for `old-name` |
  | `ambiguous` | active | `target-a` | `target-b` | Qwen Probe-2: divergent canonical_id + ALIAS_OF |
  | `target-a` | active | NULL | — | Qwen Probe-2 (canonical_id wins) |
  | `target-b` | active | NULL | — | Qwen Probe-2 (ALIAS_OF unreached) |
  | `inactive-only` | inactive | NULL | — | Path 1 inactive (must return None) |
  | `alias-to-dead` | active | NULL | `dead-target` | Path 3 with inactive canon |
  | `dead-target` | inactive | NULL | — | Inactive canon for `alias-to-dead` |

- [ ] Parametrized test asserts both `_resolve_to_canonical_slugs` (simple) and `_resolve_to_canonical_slugs_batch` produce IDENTICAL `dict[str, str]` outputs on the fixture for every probe input:
  - `["value-investing"]` → `{"value-investing": "value-investing"}`
  - `["wb"]` → `{"wb": "warren-buffett"}` (Path 2)
  - `["buffett"]` → `{"buffett": "warren-buffett"}` (Path 3)
  - `["old-name"]` → `{}` (B-2: target inactive)
  - `["ambiguous"]` → `{"ambiguous": "target-a"}` (Qwen Probe-2: canonical_id wins, ALIAS_OF unreached)
  - `["inactive-only"]` → `{}`
  - `["alias-to-dead"]` → `{}` (active edge, inactive target)
  - `["nonexistent-slug"]` → `{}`
  - `["", "  ", "value-investing"]` → `{"value-investing": "value-investing"}` (strip + drop empty)
  - `["value-investing", "value-investing"]` → `{"value-investing": "value-investing"}` (dedup)
  - `[]` → `{}`

### D.2 — Resolver unit tests (`test_t2_resolver_parity.py` extension)

- [ ] Standalone tests for simple resolver (not just parity):
  - Active-status verification on canonical_id target (B-2 regression)
  - Active-status verification on ALIAS_OF target
  - Mixed valid + invalid in same batch
  - Whitespace-only / None / empty-string handling

### D.3 — Branch selector tests `test_t2_mode_dispatch.py`

- [ ] State A (`frontmatter=None`) → legacy path fires
- [ ] State B (`frontmatter.entity_search_keys=["value-investing"]`) → structured fires; T2 contains `"value-investing"`
- [ ] **State C** (`frontmatter.entity_search_keys=[]` explicit) → T2 is empty set (D-90-8 headline)
- [ ] `T2Mode.LAYERED` with State C → legacy still fires (union behavior)
- [ ] `T2Mode.LEGACY` ignores frontmatter entirely → regression check vs current behavior
- [ ] `mode=T2Mode.STRUCTURED` is the default when caller omits the param

### D.4 — Plumbing tests (extend existing `test_planner.py` if it exists, else inline)

- [ ] `planner.build_jobs` threads frontmatter into `_build_context` correctly
- [ ] `_resolve_t2_mode_from_env` returns STRUCTURED for unset / empty / whitespace
- [ ] `_resolve_t2_mode_from_env` raises on invalid value
- [ ] Same coverage for `_resolve_t2_resolver_from_env`
- [ ] Plan-time read failure: parse_source_file raises OSError → planner degrades to `(None, "")`

### D.5 — Regression `test_graph_context_loader.py`

- [ ] Parametrize existing tests with `mode=T2Mode.LEGACY` to make the regression promise explicit.
- [ ] Add inline comment per Grok O-2: "Transitional coverage — sunsets together with legacy branch under D-90-12."

### D.6 — Verify suite green

- [ ] Run `pytest -m "not live"` — expected: 1071+N pass (N = new tests), 0 fail, same skips as main.
- [ ] Run `pytest -k t2` to inspect new tests alone — all green.

---

## §6 — Phase E: live smoke (Joseph fires per `[[feedback_user_fires_api_cost_runs]]`)

### Pre-flight: Pass-1 prompt amendment (depends on §4 v0.2)

The v0.2 blueprint §4.1 amends the Pass-1 prompt body. Before live smoke fires, the actual `kdb_compiler/ingestion/pass1_prompt.j2:62-84` block must be replaced with the amended text. This is a separate small commit (not a test concern) but is a prerequisite for E.1.

- [ ] **E.0** Update `kdb_compiler/ingestion/pass1_prompt.j2:62-84` with v0.2 amended `entity_search_keys` section.
- [ ] Increment `prompt_version` constant (if applicable) so §10 watch-for #7 can correlate v0.2 hit-rate vs v0.1.

### E.1 — STRUCTURED end-to-end (State B)

- [ ] Add `test_t2_rewrite_end_to_end_structured_path` to `test_t2_end_to_end_pass1_path.py`:
  - Fixture: write a synthetic source about `value-investing` to a test vault
  - Fire `kdb-enrich` → Pass-1 emits `entity_search_keys` (expect to include `value-investing`, etc.)
  - Fire `kdb-compile` → assert `context_snapshot.pages` contains `value-investing` in T2 tier
- [ ] Decorate with `@pytest.mark.live`. Joseph fires via `pytest -m live -k t2_rewrite_end_to_end_structured_path`.

### E.2 — State C empty-signal smoke (Deepseek F-5 gate)

- [ ] Add `test_t2_rewrite_end_to_end_empty_signal_path`:
  - Fixture: write a synthetic short source (e.g., a 2-line stub note) likely to produce `entity_search_keys=[]`
  - Fire `kdb-enrich` → assert `entity_search_keys` is `[]`
  - Fire `kdb-compile` → assert `context_snapshot.pages == []` (State C honored)
  - Assert Pass-2 completes without exception (no hallucination spiral on empty context)
- [ ] Decorate with `@pytest.mark.live`. Joseph fires post-E.1.

**Ship gate:** Both E.1 and E.2 must pass before declaring Task #90 v1 closed. E.2 specifically validates Deepseek F-5's unverified-assumption concern.

---

## §7 — Open implementation questions (none v1-blocking)

- **OQ-90-9** Should `_load_active_entities` carry `canonical_id`? Defer — current per-source ≤10 raw keys means at most 2 GraphDB round-trips, no bottleneck.
- **OQ-90-10** Cold-start asymmetry on structured branch (|T2|≥threshold with empty T1). Defer to NW-9 measurement.
- **OQ-90-13** Cyclical ALIAS_OF safeguard — confirm `graphdb-kdb verify` covers it; file separate verifier task if not. (Quick verify step before implementation.)

---

## §8 — Definition of done

- [ ] All Phase A/B/C/D checkboxes complete
- [ ] `pytest -m "not live"` passes locally (1071+N tests)
- [ ] Parity test (D.1) confirms simple ≡ batch resolver
- [ ] Phase E live smoke (Joseph fires) — both E.1 + E.2 GREEN
- [ ] `docs/CODEBASE_OVERVIEW.md` Milestone Changelog entry per `[[feedback_milestone_closure_rule]]`
- [ ] TASKS.md #90 row updated to `Closed` with v1-shipped narrative
- [ ] Commit message format mirrors Task #89 closure precedent: `feat(task90): T2-rewrite shipped — entity_search_keys consumer + Option A default + escape-hatch batch resolver (closes #90)`
