# Task #90 — Context-loader T2-rewrite Blueprint

**Status:** **v0.2 — ratified 2026-05-27 afternoon** after 5-CLI panel review (Codex + Deepseek + Gemini/agy + Grok + Qwen). Panel 5/5 guardrail-clean. Three genuine bugs caught (B-1 circular import, B-2 canonical_id target verification, B-3 §2.5↔§3.3 N+1 contradiction); all fixed in v0.2. Five new decisions ratified (D-90-8 through D-90-12). All 10 unique reviewer catches folded.

Architectural shape (Option A) ratified by Joseph 2026-05-27 morning. A/B-comparison mechanism baked in per Joseph's "we may flip to Option B after benchmarking" directive. Pass-1 prompt section inlined for panel review and amended in v0.2 per 5/5 unanimous prompt findings.

**Lineage:**
- Filed 2026-05-26 during Task #89 v0.2.2 loop-close (`docs/session-handoff-2026-05-26-task89-evening-v0.2.2-key_themes-loop-close.md`).
- **Input contract LOCKED** 2026-05-26 night via D-89-20 (`docs/task89-component1-enrichment-blueprint.md` §12).
- v0.1 drafted 2026-05-27 morning; panel dispatched same day; v0.2 folded same afternoon.
- Closes the Pass-1↔context-loader tunnel ends-meet: Pass-1 emits `entity_search_keys`; context-loader consumes them at T2.

**Parent task:** #88 (Ingestion System).
**Sibling:** Task #89 (Component #1 Enrichment) — CLOSED 2026-05-26.

---

## §1 — Problem & input contract (LOCKED — do not reopen in review)

### 1.1 Problem

`graph_context_loader._t2_slug_in_text` (`kdb_compiler/graph_context_loader.py:136`) builds T2 by whole-word regex over raw source text. This is a pre-Pass-1 heuristic: it works only when concept slugs happen to appear verbatim in the body. It misses surface-form variation, synonym mentions, author/organization names that don't share the entity slug, and any conceptual reference that doesn't use the canonical token.

With Pass-1 now emitting `entity_search_keys` (D-89-20), the LLM has produced an explicit, structured list of slug candidates designed for exactly this lookup. The regex heuristic is strictly dominated by this structured signal on Pass-1-enriched sources.

### 1.2 Input contract (D-89-20 verbatim — LOCKED)

> Consume `entity_search_keys` (list[str], ≤10 kebab-case slugs) from Pass-1 frontmatter; for each key, lookup against `Entity.slug` PK (alias-aware: extend via `ALIAS_OF` and `canonical_id` per Task #74); promote hits into T2 with current T2 score (=2). Pass-2's view of `ContextSnapshot` is **unchanged** — only the *production* path changes.

### 1.3 Scope guardrails (LOCKED — do not reopen in review)

- T1 (SUPPORTS-based) unchanged
- T3 (1/2-hop neighbor expansion) unchanged
- T2 score remains 2; cross-tier promotion remains disallowed
- PageRank tie-break unchanged
- `ContextSnapshot` schema and Pass-2's consumption unchanged
- `entity_search_keys` is **not** seen by Pass-2 — this is a producer→loader signal only

---

## §2 — Algorithm spec (Option A — clean replacement)

### 2.1 Top-level T2 construction

```python
def _build_t2(
    conn: kuzu.Connection,
    *,
    frontmatter: SourceFrontmatter | None,
    source_text: str,
    candidate_slugs: set[str],     # active_slugs - t1_slugs
    cold_start: bool,
    active_entities: dict[str, dict],
    mode: T2Mode = T2Mode.STRUCTURED,
) -> set[str]:
    """T2 production. Algorithm selected by `mode`.

    Default mode (STRUCTURED) implements Option A: Pass-1-enriched sources use
    entity_search_keys only; pre-Pass-1 sources fall back to current regex +
    cold-start title-phrase logic. Other modes exist for benchmark comparison
    only (see §7).
    """
    if mode == T2Mode.STRUCTURED:
        return _t2_structured(conn, frontmatter, source_text,
                              candidate_slugs, cold_start, active_entities)
    if mode == T2Mode.LAYERED:
        return _t2_layered(conn, frontmatter, source_text,
                           candidate_slugs, cold_start, active_entities)
    if mode == T2Mode.LEGACY:
        return _t2_legacy(source_text, candidate_slugs, cold_start,
                          active_entities)
    raise ValueError(f"unknown T2Mode: {mode}")
```

### 2.2 Mode STRUCTURED (Option A — production default) — v0.2

Branch selector distinguishes three states (D-90-8: empty-list honored as positive signal):

```python
def _t2_structured(conn, frontmatter, source_text, candidate_slugs,
                   cold_start, active_entities) -> set[str]:
    if frontmatter is None:
        # Pre-Pass-1 source: regex + cold-start title-phrase fallback
        return _t2_legacy(source_text, candidate_slugs, cold_start, active_entities)
    if frontmatter.entity_search_keys:
        # Pass-1 path: structured signal only
        return _t2_from_search_keys(conn, frontmatter.entity_search_keys,
                                    candidate_slugs)
    # Pass-1 ran and explicitly emitted []. Honor LLM's "no graph anchors"
    # signal — emit empty T2 rather than override with legacy regex.
    # (D-90-8, 3/5 panel + Joseph; rationale: empty is rare, conflating with
    # pre-Pass-1 fallback dishonors the LLM's explicit judgment.)
    return set()
```

### 2.3 Mode LAYERED (Option B — benchmark-only)

```python
def _t2_layered(conn, frontmatter, source_text, candidate_slugs,
                cold_start, active_entities) -> set[str]:
    structured: set[str] = set()
    if frontmatter is not None and frontmatter.entity_search_keys:
        structured = _t2_from_search_keys(conn, frontmatter.entity_search_keys,
                                          candidate_slugs)
    regex_pool = candidate_slugs - structured
    legacy = _t2_legacy(source_text, regex_pool, cold_start, active_entities)
    return structured | legacy
```

**v0.2 note:** LAYERED deliberately diverges from STRUCTURED on the empty-list case — when `entity_search_keys=[]` explicitly, LAYERED still runs the legacy regex (over the full candidate pool, since `structured=∅` means `regex_pool=candidate_slugs`). This lets NW-9 measure the cost of honoring the empty signal vs. always-regex head-to-head.

### 2.4 Mode LEGACY (baseline — benchmark-only)

```python
def _t2_legacy(source_text, candidate_slugs, cold_start,
               active_entities) -> set[str]:
    """Identical to today's pre-rewrite behavior."""
    t2 = _t2_slug_in_text(source_text, candidate_slugs)
    if cold_start:
        t2 = t2 | _t2_title_in_text(source_text, candidate_slugs - t2,
                                    active_entities)
    return t2
```

### 2.5 Structured-key lookup (the new core) — v0.2 batched

Fixes B-3 (v0.1 §2.5 looped over keys, contradicting §3.3's batch directive). Resolver is now batched at the per-source level: one or two queries total per source, regardless of `|entity_search_keys|`.

```python
def _t2_from_search_keys(
    conn: kuzu.Connection,
    raw_keys: list[str],
    candidate_slugs: set[str],
) -> set[str]:
    """Resolve raw keys to canonical Entity.slugs via alias-aware batched
    lookup; intersect with the candidate pool.

    Uses the simple 2-query resolver as default (D-90-9). Set semantics
    naturally deduplicate when multiple raw keys resolve to the same canonical.
    """
    if not raw_keys:
        return set()
    resolved_map = _resolve_to_canonical_slugs(conn, raw_keys)
    return {canonical for canonical in resolved_map.values()
            if canonical in candidate_slugs}
```

### 2.6 Cold-start interaction

Cold-start (T1 empty) still triggers `T3 max_hops=2` when `|T2| < _MIN_SEED_THRESHOLD`. Unchanged. Title-phrase widening (Task #71 / D48) is only invoked on the legacy / pre-Pass-1 branch — once a source is enriched, entity_search_keys IS the explicit "slugs to seed" signal, so title-phrase matching becomes redundant for that source.

### 2.7 Zero-hit behavior

If `entity_search_keys` is non-empty but resolves to zero candidates (LLM emitted slugs that don't exist in the active graph), T2 is empty for that source. T3 still walks from T1; if T1 is also empty, current 2-hop expansion fires from an empty seed set, yielding empty T3. The source ships to Pass-2 with `context_snapshot.pages = []` — the same behavior the snapshot already produces when a source genuinely has no graph anchor.

Per `[[feedback_no_imaginary_risk]]`, we ship no fallback for this case in v1. If telemetry (§10) shows zero-hit rate >5% on enriched sources with non-empty `entity_search_keys`, we file a follow-up to add a fallback layer (most likely fuzzy slug match or regex on body restricted to active slugs).

---

## §3 — Alias resolution helper (the alias-aware lookup)

### 3.1 Required behavior

Given a raw slug `s` emitted by Pass-1, return the canonical active `Entity.slug` if reachable; `None` otherwise. Reachability paths (try in order):

1. **Direct match.** `Entity{slug=s, status=active}` exists → return `s`.
2. **`canonical_id` resolution.** `Entity{slug=s}` exists but is an alias-pointer (i.e., `canonical_id IS NOT NULL`) → return `canonical_id` if that entity is active.
3. **`ALIAS_OF` edge traversal.** `(Entity{slug=s})-[:ALIAS_OF]->(canon:Entity)` exists → return `canon.slug` if `canon` is active.

Per Task #74's D-R5-13, `canonical_id` chains are flattened (no multi-hop), so a single resolution step is sufficient.

### 3.2 Signature — v0.2 batched

```python
def _resolve_to_canonical_slugs(
    conn: kuzu.Connection,
    raw_slugs: list[str],
) -> dict[str, str]:
    """Batch-resolve raw_slugs to canonical active Entity.slugs.

    Returns {raw_slug: canonical_slug} for every raw key that resolves to
    an active canonical entity via the §3.1 reachability paths. Raw keys
    that don't resolve are absent from the dict (not present with None value).

    Input handling (Qwen O-2 — defensive strip):
    - Whitespace-trimmed via str.strip()
    - Empty / whitespace-only entries dropped silently
    - Duplicates handled naturally (dict key dedup + set semantics in caller)

    Does NOT normalize slug content beyond strip — shape-validation lives at
    the Pass-1 schema layer (intentionally lenient per [[feedback_no_imaginary_risk]]).
    """
```

### 3.3 Implementation — simple 2-query default (D-90-9)

**v0.2 ratification:** Ship the simple 2-query approach as the v1 default. Codex empirically validated the single-CASE batch on Kuzu 0.11.3 in the v0.1 panel review, but 3/5 reviewers flagged zero codebase precedent for UNWIND/OPTIONAL-MATCH/CASE in this repo. Per `[[feedback_no_imaginary_risk]]`, ship the simpler approach for v1 and defer the batch optimization until perf telemetry demands it.

```python
def _resolve_to_canonical_slugs(
    conn: kuzu.Connection,
    raw_slugs: list[str],
) -> dict[str, str]:
    if not raw_slugs:
        return {}
    cleaned = [s.strip() for s in raw_slugs if s and s.strip()]
    if not cleaned:
        return {}

    resolved: dict[str, str] = {}

    # Query 1: direct match + canonical_id resolution (with target-active check)
    # Fixes B-2: canonical_id target must be active.
    q1 = conn.execute(
        """
        MATCH (e:Entity)
        WHERE e.slug IN $slugs
        OPTIONAL MATCH (target:Entity {slug: e.canonical_id})
        RETURN e.slug, e.status, e.canonical_id,
               CASE WHEN target IS NULL THEN NULL ELSE target.status END
        """,
        {"slugs": cleaned},
    )
    while q1.has_next():
        slug, status, canonical_id, target_status = q1.get_next()
        if canonical_id is None and status == "active":
            resolved[slug] = slug
        elif canonical_id is not None and target_status == "active":
            resolved[slug] = canonical_id
        # else: entity exists but resolves to nothing useful — leave unresolved

    # Query 2: ALIAS_OF traversal for raw keys not yet resolved via Q1
    unresolved = [s for s in cleaned if s not in resolved]
    if unresolved:
        q2 = conn.execute(
            """
            MATCH (e:Entity)-[:ALIAS_OF]->(c:Entity)
            WHERE e.slug IN $slugs AND c.status = 'active'
            RETURN e.slug, c.slug
            """,
            {"slugs": unresolved},
        )
        while q2.has_next():
            raw, canonical = q2.get_next()
            if raw not in resolved:
                resolved[raw] = canonical

    return resolved
```

**Performance characterization:** 2 round-trips per source, both parameterized scalar-list queries (well-supported in Kuzu). Pass-1 emits ≤10 keys, so each query scans at most 10 candidate slugs against a fully-indexed `Entity.slug` PK — negligible cost (sub-ms expected).

### 3.4 Implementation — Codex-tested batch (D-90-9 escape hatch)

A single-query batched form using `UNWIND` + chained `OPTIONAL MATCH` + `CASE` exists as an optional path, gated on `KDB_T2_RESOLVER=batch`. Codex empirically validated this against Kuzu 0.11.3 in the v0.1 panel review.

```cypher
UNWIND $raw_slugs AS raw
OPTIONAL MATCH (e:Entity {slug: raw})
WITH raw, e
OPTIONAL MATCH (e)-[:ALIAS_OF]->(canon:Entity)
OPTIONAL MATCH (target:Entity {slug: e.canonical_id})
RETURN raw,
       CASE
         WHEN e IS NULL THEN NULL
         WHEN e.status = 'active' AND e.canonical_id IS NULL THEN e.slug
         WHEN e.canonical_id IS NOT NULL AND target IS NOT NULL AND target.status = 'active' THEN e.canonical_id
         WHEN canon IS NOT NULL AND canon.status = 'active' THEN canon.slug
         ELSE NULL
       END AS canonical
```

**Implementation discipline:** A parametrized test (test_resolver_simple_vs_batch_parity) MUST assert that both implementations produce identical `{raw_slug: canonical_slug}` mappings on a shared fixture graph spanning all four §3.1 reachability cases (Grok F-4 escape-hatch + parity-test recommendation). This makes Kuzu-version risk observable and contained.

---

## §4 — Pass-1 prompt for `entity_search_keys` — v0.2 AMENDED

### 4.1 v0.2 ratified prompt body (replaces `kdb_compiler/ingestion/pass1_prompt.j2:62-84`)

Five-of-five panel reviewers converged on three load-bearing amendments: (a) add consumer-mechanism anchoring sentence; (b) tighten Category 4 from speculative co-occurrence to substantively-referenced concepts; (c) replace single finance-domain example with ≥2 domain-diverse examples. Four-of-five also converged on (d): name disambiguation should emit one form per person, not surname-AND-full-name. Plus Deepseek's clarification about conjunctions inside slugs.

```
- `entity_search_keys`: list of up to 10 kebab-case slug candidates designed
  to seed a downstream context-loader that looks up existing entities in a
  knowledge graph. The graph contains entities for notable people, concepts,
  frameworks, themes, and named ideas across many sources. These keys are
  matched against entity slugs by exact string comparison, with an
  alias-resolution layer that maps known variant slugs (and "ALIAS_OF"
  edges) to their canonical form — so emit the slug form most likely to
  match an existing entity record directly, and avoid emitting multiple
  variants of the same entity. What to include:
    1. Each item in `key_themes` (themes themselves are often already entity slugs).
    2. Common slug variants of each theme — but only if the variant is a
       distinct concept (e.g., for "value-investing" the related concept
       "intrinsic-value" is a distinct entity, not an orthographic variant
       of "value-investing").
    3. Slugs for entity names mentioned substantively in the source —
       people, organizations, named frameworks. Prefer the full-name form
       ("warren-buffett") over surname-only ("buffett"). Do NOT emit both
       forms for the same individual; the alias-resolution layer handles
       variant matching downstream.
    4. Closely-related concepts that are substantively referenced or
       load-bearing to the source's core argument, and that you believe
       likely have their own entity records in a well-populated graph
       (e.g., a framework's foundational principle, a theory's key critic).
       Emit only concepts the source actually engages — do not include
       speculative or weak co-occurrences.
  Format: lowercase, hyphens between words, no spaces, no punctuation other
  than hyphens. Conjunctions and prepositions inside slugs are fine
  ("graham-and-doddsville", "theory-of-mind"). Prefer specificity over
  breadth: "value-investing" beats "investing"; "graham-and-doddsville"
  beats "investors". Cap at 10 keys total; aim for 5–10.

  Examples (domain-diverse):

  - Finance: source about Warren Buffett and Charlie Munger's value-investing
    approach with key_themes ["value-investing", "margin-of-safety",
    "compounding"]
    → `["value-investing", "margin-of-safety", "compounding",
         "warren-buffett", "charlie-munger", "intrinsic-value",
         "berkshire-hathaway", "circle-of-competence",
         "graham-and-doddsville"]`.

  - AI/ML: source about transformer architectures in NLP with key_themes
    ["attention-mechanism", "self-attention", "transformers"]
    → `["attention-mechanism", "self-attention", "transformers",
         "multi-head-attention", "positional-encoding",
         "sequence-to-sequence", "bert", "scaling-laws"]`.

  - Philosophy: source about Rawls' veil of ignorance with key_themes
    ["veil-of-ignorance", "distributive-justice", "original-position"]
    → `["veil-of-ignorance", "distributive-justice", "original-position",
         "john-rawls", "theory-of-justice", "social-contract",
         "kantian-ethics"]`.
```

### 4.2 v0.2 amendments to the prompt (vs v0.1 / current j2)

| Change | Rationale | Panel convergence |
|---|---|---|
| New anchoring sentence: "matched against entity slugs by exact string comparison, with an alias-resolution layer..." | LLM was blind to exact-PK + alias-resolution mechanism | 5/5 unanimous |
| Category 2 tightened: "variants only if distinct concepts" — drops orthographic-variant fanout | Hit-rate metric punishes orthographic redundancy after alias-resolution | 4/5 (Codex/Deepseek/Gemini/Qwen) |
| Category 3: "Prefer full-name; do NOT emit both forms" — single form per person | Surname+full-name burns cap budget without adding hits | 4/5 (Codex/Deepseek/Gemini/Qwen); Grok mild dissent (cap mitigates) |
| Category 4 substantively rewritten: "substantively referenced or load-bearing... do not include speculative co-occurrences" | Speculative fanout adversarial to hit-rate metric (Qwen F-3) | 5/5 unanimous |
| Conjunctions clarification: "graham-and-doddsville, theory-of-mind are fine" | Prevents LLM from stripping function words | Deepseek 4.6 unique catch |
| ≥2 domain-diverse examples (finance + ai-ml + philosophy as 3rd) | Single finance example anchors LLM to person-name-heavy patterns | 5/5 unanimous |

### 4.3 Out-of-scope (not amended)

- **Cap of 10** stays. 5/5 reviewers ratify; cap mitigates speculative fanout; the top-50 page cap gives natural headroom. NW-9 telemetry will measure if a sharper cap improves Pass-2 quality.
- **The required-LLM-output shape** (lowercase kebab-case, hyphens-only punctuation) stays. Codex/Qwen flagged that schema-level shape validation was relaxed in v0.2.2 (`see's-candies` accepted) — see §8 test plan for the apostrophe gap (folded as Deepseek F-4).

---

## §5 — Code surface (files touched) — v0.2

| File | Change |
|---|---|
| **NEW** `kdb_compiler/source_io.py` | **(B-1 fix, D-90-10)** Shared helper module hosting `SourceFrontmatter` dataclass + `parse_source_file(path) -> tuple[SourceFrontmatter \| None, str]`. Both planner and compiler import from here, eliminating the planner→compiler circular import that would crash startup under v0.1's plumbing. |
| `kdb_compiler/compiler.py` | `SourceFrontmatter` definition relocates to `source_io.py`; `compiler.py` re-imports it. `source_text_for(job)` becomes a thin wrapper around `parse_source_file(Path(job.abs_path))`. No external API change. |
| `kdb_compiler/graph_context_loader.py` | Add `T2Mode` enum (stays in this module per D-90-11) + `_build_t2()` dispatcher + `_t2_structured` / `_t2_layered` / `_t2_legacy` / `_t2_from_search_keys` / `_resolve_to_canonical_slugs`. Existing `_t2_slug_in_text` + `_t2_title_in_text` + `_whole_word_alternation` retained as private helpers under `_t2_legacy`. Loader does NOT read env vars (Codex F-5 — preserves existing purity invariant). |
| `kdb_compiler/graph_context_loader.py` | Extend `build_context_snapshot` signature: add `frontmatter: SourceFrontmatter \| None` param, `mode: T2Mode = T2Mode.STRUCTURED` param. |
| `kdb_compiler/planner.py` | (a) Import `parse_source_file` + `SourceFrontmatter` from `source_io.py`. (b) `build_jobs` calls `parse_source_file(abs_path)` once per source (no double disk-read per Gemini F-4 — `_read_source_text` retired in favor of single parse). (c) Parse `KDB_T2_MODE` env var once at planner entry; thread explicit `T2Mode` value into `_build_context`. |
| `kdb_compiler/types.py` | **No change.** `CompileJob` schema stays as-is (D-90-7 ratified by 5/5). T2Mode stays in `graph_context_loader.py` (D-90-11 — 4/5 panel + my call). |

**No changes** to: Pass-1 producer's enrichment path beyond the prompt amendment in §4 (the producer already emits `entity_search_keys`); Pass-2 compile prompt; GraphDB schema; verifier; ingestor.

### §5.1 Env-var contract

| Variable | Default | Purpose |
|---|---|---|
| `KDB_T2_MODE` | `structured` | Selects T2Mode: `structured` / `layered` / `legacy`. Parsed once at planner entry. |
| `KDB_T2_RESOLVER` | `simple` | Selects resolver: `simple` (2-query default, D-90-9) or `batch` (Codex-tested escape hatch). |

Both env vars are read in `planner.py` and threaded explicitly into downstream modules. The loader and resolver remain env-var-free.

---

## §6 — Backward-compat semantics — v0.2

### 6.1 Branch selector — three states (D-90-8)

The v0.1 selector collapsed two distinct states ("absent frontmatter" and "explicit empty list"). v0.2 distinguishes three:

```python
# Inside _t2_structured(...):
if frontmatter is None:
    # State A: pre-Pass-1 source — fall back to legacy regex + cold-start
    return _t2_legacy(source_text, candidate_slugs, cold_start, active_entities)

if frontmatter.entity_search_keys:
    # State B: Pass-1 enriched with non-empty signal — use structured lookup
    return _t2_from_search_keys(conn, frontmatter.entity_search_keys, candidate_slugs)

# State C: Pass-1 enriched with EXPLICIT empty signal — honor LLM judgment
# (D-90-8 ratified by Joseph + 3/5 panel: Codex, Grok, Qwen)
return set()
```

**Why honor empty (D-90-8):** an LLM that ran Pass-1 enrichment and produced `entity_search_keys=[]` made an explicit "no graph anchors" judgment. Falling back to legacy regex would override that judgment with a heuristic — dishonest semantics. Joseph's intuition: empty list is a *rare* occurrence; in the rare case it happens, respect the signal. If telemetry (§10) shows empty-rate is high or that empty-signal sources benefit from legacy regex on Pass-2 quality, revisit via NW-9 axis.

### 6.2 Frontmatter plumbing — single parse, single disk read (B-1 + Gemini F-4)

**v0.1's option (i)** would have looped through `compiler.py::source_text_for` from `planner.py`. That's a circular import that crashes startup (Bug B-1, caught 4/5 panel). **v0.2 fix:** new `kdb_compiler/source_io.py` module hosts both `SourceFrontmatter` and `parse_source_file(path) -> tuple[SourceFrontmatter | None, str]`. Planner and compiler both import from this neutral module.

Gemini F-4 also surfaced that the planner already loads the source file from disk (current `_read_source_text` at `planner.py:83-92`). v0.2 retires `_read_source_text` and routes the parse through `parse_source_file`, eliminating the double-disk-read. Frontmatter is parsed ONCE per source per compile cycle.

```python
# planner.py (post-rewrite):
from kdb_compiler.source_io import parse_source_file, SourceFrontmatter

# Inside build_jobs:
abs_path = vault_root / source_id
frontmatter, source_text = parse_source_file(abs_path)  # one disk read, one parse
snapshot = _build_context(
    conn,
    source_id=source_id,
    source_text=source_text,
    frontmatter=frontmatter,
    page_cap=context_page_cap,
    mode=_resolve_t2_mode_from_env(),  # KDB_T2_MODE parsed here, once
)
```

**Compiler side unchanged:** `source_text_for(job)` becomes a 1-line wrapper around `parse_source_file(Path(job.abs_path))`. External API stable; downstream call sites unaffected.

### 6.3 Pre-Pass-1 corpus state

Per the 2026-05-26 A.0 vault scan, the vault has 0 hand-tagged sources across 1663 .md files — all existing GraphDB Source rows came from prior pre-Pass-1 compile runs. Until `kdb-enrich` runs against the vault, **all sources hit State A** (legacy branch). This is correct and intended.

The migration story is **incremental**: as sources are enriched, they transition State A → State B (or State C, rarely). No flag day, no migration script needed. The legacy branch (~70 LOC) stays live until the sunset gate fires (D-90-12 — see §11).

---

## §7 — Benchmark plan (separate task — gated)

Per Joseph 2026-05-27: empirical comparison is load-bearing. **The decision to keep Option A as default vs. flip to Option B is gated on a benchmark, not on this blueprint's intuition.**

### 7.1 Architectural support for A/B comparison

The `T2Mode` enum + dispatch (§2.1) is the mechanism. By switching mode, the same corpus produces three measurable T2 sets:

- `STRUCTURED` — Option A (production default)
- `LAYERED` — Option B (structured ∪ legacy)
- `LEGACY` — baseline (current code's behavior)

Switch via env var: `KDB_T2_MODE=structured|layered|legacy` (default `structured`).

### 7.2 Benchmark task (NW-9 — filed in TASKS.md) — v0.2 expanded

Predeclared-eval-criteria pattern (precedent: Task #75/#87/NW-5). Sub-deliverables:

1. **Eval criteria** — what does "better T2" mean?
   - **Hit rate**: |T2| > 0; also per-source `|alias-resolved| / |entity_search_keys emitted|`
   - **Precision proxy**: Pass-2 compile output quality (page reuse, dedup wins)
   - **Recall proxy**: compare to a hand-curated "gold T2" on a small probe set
   - **Cold-start density**: |T2| when T1 is empty
   - **Drift cost**: LLM-emitted slugs that don't match — fraction; split by structural failure (no entity in graph for the concept) vs. orthographic drift (entity exists but slug form differs) — Qwen OQ-90-2 elaboration
   - **D-90-5 axis** (Deepseek): does LAYERED outperform STRUCTURED on cold-start sources with non-empty `entity_search_keys`? I.e., does title-phrase widening + regex add signal or noise on enriched cold-start sources?
2. **Probe corpus** — stratified across:
   - ≥3 domains and ≥3 source_types from the 23/21 vocabs
   - **T1 state stratification** (Grok OQ-1): deliberately oversample cold-start sources (T1=∅ or T1<3), where T2 signal change is most load-bearing
   - **Empty-signal sources**: include a small bucket of `entity_search_keys=[]` sources to verify State C semantics produce reasonable Pass-2 output (Deepseek F-5 unverified-assumption check)
3. **Run harness** — fire same probe corpus through all three modes (STRUCTURED / LAYERED / LEGACY) and both resolvers (simple / batch) on STRUCTURED; collect per-source T2 + downstream metrics + resolution-path breakdown (Grok OQ-2 telemetry).
4. **Decision report** — quantifies:
   - STRUCTURED vs LAYERED on hit rate / precision / cold-start density
   - LAYERED vs LEGACY on Pass-2 quality (does the regex layer add real value on enriched sources, or just noise?)
   - simple resolver vs batch resolver parity (must be functionally identical — sanity check)
   - D-90-5 axis result determines whether title-phrase widening stays gated to legacy or gets promoted to a structured-fallback layer
   - Locks production default for `KDB_T2_MODE` based on the answer.

**Gating:** the benchmark CANNOT run until §2/§3/§5 ship (Option A's default) AND a non-trivial fraction of the vault is enriched. Realistically, benchmark fires after ~50–200 sources are enriched. Not blocking the v1 ship.

### 7.3 Flip protocol

If the benchmark shows Option B is decisively better, flipping the default is a one-line change to the default mode argument. No code restructure. This is the "we paint ourselves no corner" property Joseph called for.

---

## §8 — Test plan — v0.2 expanded

### 8.1 Unit tests (non-live)

**Resolver (simple, default per D-90-9):**
- `_resolve_to_canonical_slugs`: direct hit / canonical_id hit (with active target) / **canonical_id hit with INACTIVE target** (B-2 regression — must return absent) / ALIAS_OF hit (active canonical) / ALIAS_OF hit (inactive canonical — must return absent) / nonexistent slug / empty input / whitespace-only input / mixed valid+invalid+duplicate input.
- **Parity test** (new, D-90-9 + Grok F-4): `test_resolver_simple_vs_batch_parity` — parametrized fixture graph spans all §3.1 paths + B-2 inactive-target case + Qwen Probe-2 (entity with both `canonical_id` and divergent `ALIAS_OF`); both implementations MUST return identical `{raw_slug: canonical_slug}` mappings.

**Branch + dispatch:**
- `_t2_from_search_keys`: all-resolve / partial-resolve / all-miss / empty input / candidate-pool filtering (resolved slugs already in T1).
- `_t2_structured`: **three states** (D-90-8) — State A `frontmatter is None` → legacy / State B non-empty keys → structured / **State C explicit `[]` → empty T2** (new test, headline D-90-8 coverage).
- `_t2_layered`: structured ∪ legacy correctness; LAYERED with State C still runs legacy regex on full candidate pool.
- `_t2_legacy`: identical to current behavior (regression check, T2Mode.LEGACY parametrized).
- `build_context_snapshot`: mode dispatch via planner-supplied param; T2Mode default = STRUCTURED.

**Plumbing (B-1 fix coverage):**
- `parse_source_file` in new `source_io.py`: returns `(SourceFrontmatter | None, str)` correctly for Pass-1 enriched / pre-Pass-1 / non-existent path / decode-error path.
- `planner._build_context` threads `SourceFrontmatter` correctly; env-var parsing for `KDB_T2_MODE` + `KDB_T2_RESOLVER` happens once at planner entry.

### 8.2 Live smoke (gated — `pytest -m live`)

Two E.1-style end-to-end tests:

```python
def test_t2_rewrite_end_to_end_structured_path():
    """Pass-1 enriched source → kdb-compile → assert T2 contains slugs
    from entity_search_keys (alias-resolved). Verifies State B."""

def test_t2_rewrite_end_to_end_empty_signal_path():
    """Pass-1 enriched source with explicit entity_search_keys=[] →
    kdb-compile → assert T2 is empty AND Pass-2 produces valid output
    on empty context_snapshot.pages. Verifies State C + Deepseek F-5."""
```

**Deepseek F-5 smoke gate:** before claiming v1 ship, run `test_t2_rewrite_end_to_end_empty_signal_path` to confirm Pass-2 (compile prompt) gracefully handles `ContextSnapshot(pages=[])` on a non-trivial source (no crash, no hallucination spiral). This is the production state that v0.1 assumed safe but never verified.

### 8.3 Regression coverage

Existing `test_graph_context_loader.py` suite must remain green — legacy mode preserves current behavior verbatim. Add `T2Mode.LEGACY` parametrization to existing tests to make this assertion explicit. Per Grok O-2: document the LEGACY parametrization as transitional regression-coverage — once production runs are 100% STRUCTURED, these tests guard a path fewer real runs exercise. Sunset together with the legacy branch (D-90-12).

---

## §9 — Open questions — v0.2 resolution

All eight v0.1 open questions resolved via 2026-05-27 panel + Joseph ratification. Status table:

| OQ | v0.1 Question | v0.2 Resolution | Reference |
|---|---|---|---|
| OQ-90-1 | `entity_search_keys=[]` semantics | **Honor empty signal** — emit empty T2 (State C); do NOT fall back. | D-90-8, §2.2, §6.1 |
| OQ-90-2 | 5% zero-hit threshold | 5% raw rate as initial tripwire + dedicated drift-vs-coverage telemetry split in §10 watch-fors. | §10 #6 (new) |
| OQ-90-3 | Kuzu batch query compatibility | **Simple 2-query as v1 default** (D-90-9); Codex-tested batch retained as `KDB_T2_RESOLVER=batch` escape hatch with parity test. | §3.3 + §3.4 |
| OQ-90-4 | Pass-1 prompt review | All 5/5 unanimous prompt amendments folded; plus 4/5 name-disambiguation + Deepseek conjunction note. | §4.1 + §4.2 |
| OQ-90-5 | Plumbing option (i) vs (ii) | (i) ratified 5/5 BUT via shared `source_io.py` (B-1 fix); single disk read (Gemini F-4). | D-90-10, §6.2 |
| OQ-90-6 | Env var sufficient for v1? | Yes, 5/5 ratified. `KDB_T2_MODE` + `KDB_T2_RESOLVER`. CLI flag may follow post-NW-9. | §5.1 |
| OQ-90-7 | T2Mode enum location | Stays in `graph_context_loader.py` (4/5 panel + my call). | D-90-11, §5 |
| OQ-90-8 | Sunset trigger | **Define now** (Joseph + Codex/Deepseek). 3-part AND-gate per D-90-12. | D-90-12, §11 |

### New open questions surfaced in v0.2 review (deferred — not v1 blockers)

- **OQ-90-9** (Qwen). `_load_active_entities` doesn't currently return `canonical_id`. Should it be extended to carry `canonical_id` (avoiding a second query in some paths), or kept separate for cleanliness? Touch-test post-v1 implementation if profiling shows cost.
- **OQ-90-10** (Qwen). Cold-start interaction asymmetry: on STRUCTURED branch, if `|T2_structured|` ≥ `_MIN_SEED_THRESHOLD`, the 2-hop T3 expansion never fires even when T1 is empty. Is this correct? Or should cold-start 2-hop gate depend on T1-emptiness independently of T2 size? Defer to NW-9 — measure whether structured cold-start sources benefit from 2-hop T3.
- **OQ-90-11** (Qwen). `prompt_version` correlation with hit-rate telemetry — add as a watch-for dimension so prompt changes (v0.2 amendments) can be correlated with hit-rate shifts. Folded into §10 #7.
- **OQ-90-12** (Grok). Should `ContextSnapshot` carry a `T2 explanation` sidecar so Pass-2 + debug tooling can see whether a page came via T1 SUPPORTS / T2 structured / T2 legacy? Not needed for v1; revisit if Pass-2 debugging surfaces ambiguity.
- **OQ-90-13** (Gemini). Cyclical ALIAS_OF safeguard — sanity check belongs in `graphdb-kdb verify`, not in the resolver. Confirm verifier covers this; file as separate verifier follow-up if not.
- **OQ-90-14** (Gemini). PageRank in-memory NetworkX scale — track computation latency in resp-stats post-ship to detect when graph grows past comfortable in-memory bounds.

---

## §10 — Empirical watch-fors (post-ship telemetry) — v0.2 expanded

To be observed after v1 ships, ideally surfaced via NW-5 (Pass-1 benchmark) or compile resp-stats:

1. **Hit rate per source** — |alias-resolved slugs| / |entity_search_keys emitted|. Low (<30%) signals normalization drift or LLM slug invention. Expected well-tuned range: 50–80% (Codex + Qwen converge).
2. **Zero-hit rate** — % of Pass-1-enriched sources where `_t2_from_search_keys` returns ∅ despite non-empty `entity_search_keys`. Threshold for filing follow-up: 5% raw + dedicated precision-on-substantive-sources view.
3. **State C rate** (NEW — D-90-8 instrumentation) — % of Pass-1-enriched sources with explicit `entity_search_keys=[]`. Joseph's intuition: this should be rare. If >5%, surface as anomaly (prompt may be over-conservative).
4. **T2 size delta** — average |T2_structured| vs historical |T2_legacy| on same source. Expected: structured larger when LLM extracts well; smaller when LLM is conservative.
5. **Alias-resolution path counts** — fraction of resolutions via direct PK vs canonical_id vs ALIAS_OF (Grok OQ-2 — surface per-hit). Skewed → alias ledger needs grooming OR Pass-1 prompt's slug conventions diverge from graph reality.
6. **Drift-vs-coverage split** (NEW — Qwen OQ-90-2 elaboration) — when a key fails to resolve, categorize: (a) orthographic drift (concept exists in graph under a different slug form, often a hyphenation/apostrophe variant — fixable via prompt tuning or alias ledger update), (b) coverage gap (genuine concept not yet in graph — fixable via more compile runs). Actionable telemetry, not just raw rate.
7. **Prompt-version correlation** (NEW — Qwen OQ-90-11) — group hit-rate stats by Pass-1 `prompt_version`. Validates that v0.2 prompt amendments (anchoring + Category 4 tightening + ≥2 examples) improve hit rate versus v0.1 baseline.
8. **Cold-start improvement** — comparison of |T2| under cold-start (T1=∅) for STRUCTURED vs LEGACY. The original Task #71 win was empirical (17–23 pages on cold-start vs 0–8 from manifest); does STRUCTURED preserve or improve that?
9. **Legacy-branch invocation count** (NEW — D-90-12 telemetry) — counter `legacy_t2_sources_total` per compile cycle. Sunset gate (a) trips when this stays at 0 across a full vault compile cycle.
10. **Shape validation drift** (NEW — Deepseek F-4) — count raw keys with format anomalies (apostrophes, uppercase, embedded spaces) that pass relaxed schema validation but fail PK lookup. Calibrates whether prompt-vs-schema coherence is causing miss-able hits.

---

## §11 — Decision log — v0.2

| ID | Decision | Date | Status |
|---|---|---|---|
| D-89-20 | Input contract: consume `entity_search_keys`; alias-aware lookup; T2 score=2 | 2026-05-26 night | Locked (parent #89) |
| D-90-1 | Option A (clean replacement) selected as v1 production default | 2026-05-27 morning | Locked by Joseph |
| D-90-2 | A/B-comparison mechanism baked in via `T2Mode` enum (STRUCTURED / LAYERED / LEGACY) | 2026-05-27 morning | Locked by Joseph |
| D-90-3 | Pass-1 `entity_search_keys` prompt inlined in blueprint §4 for 5-model panel review | 2026-05-27 morning | Locked by Joseph |
| D-90-4 | Benchmark task filed as separate sibling (predeclared-eval-criteria pattern); gates production-default change, not v1 ship | 2026-05-27 morning | Locked by Joseph |
| D-90-5 | Cold-start title-phrase widening (Task #71) survives on legacy branch only; retired per-source as enrichment rolls out | 2026-05-27 morning | **Ratified 5/5 panel + Joseph 2026-05-27 afternoon** |
| D-90-6 | Zero-hit fallback: none in v1 per `[[feedback_no_imaginary_risk]]`; gated on >5% zero-hit telemetry | 2026-05-27 morning | **Ratified 5/5 panel + Joseph 2026-05-27 afternoon** |
| D-90-7 | Frontmatter plumbing: planner single-parses via shared helper; `CompileJob` schema unchanged | 2026-05-27 morning | **Ratified 5/5 panel + Joseph 2026-05-27 afternoon (amended via D-90-10 for B-1 fix)** |
| D-90-8 | **`entity_search_keys=[]` (State C) honors LLM "no graph anchors" signal — emits empty T2; does NOT fall back to legacy regex** | 2026-05-27 afternoon | Locked (Joseph + 3/5 panel: Codex, Grok, Qwen). Rationale: rare occurrence, honoring is more honest than overriding with heuristic. |
| D-90-9 | **Resolver: simple 2-query as v1 default; Codex-tested batch retained as `KDB_T2_RESOLVER=batch` escape hatch + parity test enforces functional identity** | 2026-05-27 afternoon | Locked (my call). Rationale: 3/5 cite zero codebase precedent for UNWIND/OPTIONAL-MATCH/CASE; perf not load-bearing for v1; Codex empirical evidence preserved. |
| D-90-10 | **Shared `kdb_compiler/source_io.py` module hosts `SourceFrontmatter` + `parse_source_file()`; both planner and compiler import from here (fixes Bug B-1 circular import + Gemini F-4 double disk-read)** | 2026-05-27 afternoon | Locked (4/5 panel: Codex, Gemini, Qwen explicit + Grok latent) |
| D-90-11 | **`T2Mode` enum stays in `graph_context_loader.py`; not promoted to `types.py`** | 2026-05-27 afternoon | Locked (my call, 4/5 panel: Codex, Deepseek, Grok, Qwen). Algorithm control flow, not data shape. |
| D-90-12 | **Legacy-branch sunset trigger: 3-part AND-gate** — (a) `legacy_t2_sources_total == 0` across one full `kdb-compile` vault cycle, AND (b) NW-9 confirms STRUCTURED ≥ LEGACY on cold-start T2 density, AND (c) NW-9 confirms STRUCTURED ≥ LEGACY on Pass-2 quality precision. When all three hold, legacy branch removable in single follow-up commit. | 2026-05-27 afternoon | Locked (Joseph + Codex/Deepseek). |

---

## §12 — Next steps — v0.2

1. ~~Joseph review of v0.1~~ — ✅ done 2026-05-27 morning (ratified Option A)
2. ~~5-model panel dispatch~~ — ✅ done 2026-05-27 (5/5 guardrail-clean)
3. ~~Fold panel feedback → v0.2~~ — ✅ done 2026-05-27 afternoon (this document)
4. **Algorithm details task** (#2 in task list) — pin down implementation specifics: `parse_source_file` exact shape in `source_io.py`, env-var parsing helper in planner, `_build_t2` dispatcher exact signature, parity-test fixture graph spanning all §3.1 paths + B-2 + Qwen Probe-2 cases.
5. **Implementation task** (#3 in task list) — code + tests + verify full suite green (currently 1071 passing on `main`). Honor pytest discipline: `-m "not live"` filter when running as assistant.
6. **Live smoke gate** — fire `test_t2_rewrite_end_to_end_structured_path` + `test_t2_rewrite_end_to_end_empty_signal_path` (Deepseek F-5 gate). Joseph fires per `[[feedback_user_fires_api_cost_runs]]`.
7. **NW-9 benchmark task** (#14 in task list) — predeclared eval criteria → probe corpus → run harness → decision report. Gates production-default flip; not v1 ship blocker.
8. **Milestone Changelog entry** — when Task #90 closes, add a dated line to `docs/CODEBASE_OVERVIEW.md` per `[[feedback_milestone_closure_rule]]`.

---

## §13 — v0.2 amendments table (v0.1 → v0.2 delta)

| Section | v0.1 | v0.2 | Source |
|---|---|---|---|
| §2.2 STRUCTURED branch selector | Two-state: present-non-empty vs everything-else → legacy | **Three-state**: `frontmatter is None` → legacy / non-empty → structured / **explicit `[]` → empty T2** | D-90-8 (Joseph + 3/5 panel) |
| §2.3 LAYERED note | (none) | Added clarification: LAYERED runs legacy regex even on State C, to support NW-9 comparison axis | v0.2 internal consistency |
| §2.5 `_t2_from_search_keys` | Loop-per-key (N+1 anti-pattern, contradicting §3.3 batch directive) | **Batched**: calls `_resolve_to_canonical_slugs` once per source, set-comprehension over returned dict | Bug B-3 (Gemini F-1 unique catch) |
| §3.2 Resolver signature | Per-slug `_resolve_to_canonical_slug(conn, str) -> str \| None` | **Batched** `_resolve_to_canonical_slugs(conn, list[str]) -> dict[str, str]` + defensive `strip()` | Bug B-3 + Qwen O-2 |
| §3.3 Implementation | Single-CASE batch query as default (Kuzu compatibility caveat noted) | **Simple 2-query as v1 default** (D-90-9); batch (B-2-fixed) demoted to optional escape hatch | D-90-9 (3/5 panel + my call) |
| §3.3 CASE expression | `WHEN e.canonical_id IS NOT NULL THEN e.canonical_id` (no target-active check) | **Adds `OPTIONAL MATCH (target {slug: e.canonical_id})` + `target.status = 'active'` clause** | Bug B-2 (4/5 panel) |
| §3.4 NEW | (none) | **Codex-tested batch resolver documented as escape hatch** with parity-test enforcement | Codex empirical + Grok F-4 |
| §4 Pass-1 prompt body | v0.1 text (single finance example, surname+full-name, speculative Cat 4) | **Amended**: new anchoring sentence; Cat 2 tightened to distinct-concept variants; Cat 3 single-form-per-person; Cat 4 substantively-referenced only; conjunction-clarification; ≥3 domain-diverse examples (finance + AI/ML + philosophy) | 5/5 + 4/5 panel + Deepseek 4.6 unique |
| §4.2 NEW | (none) | **v0.2 prompt amendments table** with rationale + convergence | v0.2 audit trail |
| §5 Code surface | Option-(i) plumbing (planner→compiler) | **B-1 fix**: new `kdb_compiler/source_io.py` module; planner imports from neutral helper. Single disk read (Gemini F-4 retires `_read_source_text`). | Bug B-1 (4/5 panel) |
| §5 Env-var contract | Env var read in loader (implicit) | **Loader stays env-var-free** (Codex F-5 purity boundary); planner owns env-var parsing | Codex F-5 unique |
| §5.1 NEW | (none) | **`KDB_T2_MODE` + `KDB_T2_RESOLVER` env-var table** | D-90-9 + Codex F-5 |
| §6.1 Branch selector | `frontmatter is not None and entity_search_keys` (collapsed) | **Three-state explicit ladder** (D-90-8) | Bug B-3 / OQ-90-1 |
| §6.2 Plumbing path | Two options posed (planner double-parses OR `CompileJob` carries) | **Single ratified option**: shared `source_io.py` + single parse + single disk read | D-90-10 |
| §8.1 Unit tests | Per-slug resolver tests | **Batched-resolver tests** + parity-test (simple vs batch) + B-2 regression (inactive canonical_id target) + State-C explicit-empty test | Bugs B-2/B-3 + D-90-8 + D-90-9 |
| §8.2 Live smoke | One STRUCTURED end-to-end | **Two**: STRUCTURED + State-C empty-signal (Deepseek F-5 gate on Pass-2 empty-context behavior) | Deepseek F-5 unique |
| §8.3 Regression | T2Mode.LEGACY parametrization | Same + **Grok O-2 transitional-coverage note** (sunset together with legacy branch under D-90-12) | Grok O-2 |
| §9 Open questions | 8 open (OQ-90-1..8) | **All 8 resolved** + 6 new (OQ-90-9..14) deferred — none v1-blocking | 2026-05-27 afternoon resolution |
| §10 Watch-fors | 5 metrics | **10 metrics** — adds State C rate, drift-vs-coverage split, prompt-version correlation, legacy-branch invocation count, shape-validation drift | Multiple panel catches |
| §11 Decision log | D-90-1..7 (3 open) | **D-90-1..12 (all locked)** — adds D-90-8 honor-empty / D-90-9 simple-resolver / D-90-10 source_io / D-90-11 T2Mode location / D-90-12 sunset gate | Panel + Joseph ratification |

---

## §14 — Reviewer convergence summary (2026-05-27 panel)

5/5 guardrail-clean (Codex + Deepseek + Gemini/agy + Grok + Qwen). Convergence pattern:

| Tier | Count | Items |
|---|---|---|
| **5/5 unanimous** | 9 | D-90-5/6/7 + OQ-90-5/6 + 3 prompt amendments (anchoring / Cat 4 / examples) + (implicit) all LOCKED items respected |
| **4/5** | 3 | Surname-vs-full-name (Grok mild dissent on cap-mitigates); T2Mode location (Gemini dissents → `types.py`); B-1 circular import (Grok latent) |
| **3/5** | 3 | OQ-90-1 empty-signal (Codex+Grok+Qwen for honor; Deepseek+Gemini for fall-back); OQ-90-3 Kuzu (3/5 prefer simple; Codex empirically tested batch); OQ-90-8 sunset (split 2 fix-now / 3 defer) |
| **Genuine bugs** | 3 | B-1 circular import (4/5); B-2 canonical_id target verification (4/5); B-3 §2.5↔§3.3 N+1 contradiction (Gemini F-1 unique) |
| **Unique catches** | 10 | Codex Kuzu 0.11.3 empirical test; Codex purity-boundary preservation; Deepseek shape-validation gap; Deepseek conjunction-in-slug clarification; Deepseek Pass-2-empty-context unverified-assumption; Qwen defensive strip; Qwen `_load_active_entities` canonical_id gap; Qwen cold-start asymmetry; Qwen prompt-version correlation; Grok T2-path provenance telemetry; Grok T2-explanation sidecar; Grok regression-coverage transitional note; Gemini double-disk-read avoidance; Gemini cyclical-alias safeguard; Gemini PageRank scale watch-for |

All unique catches folded (no vetoes per Joseph 2026-05-27 afternoon).

**Reviewer track-record note (per `docs/external-review-panel.md`):**

- **Codex** — 6/6 clean. Unique value: empirical Kuzu validation; purity-boundary preservation.
- **Deepseek** — 4/4 clean. Unique value: schema/prompt coherence gaps; verifying assumed-safe production states.
- **Gemini/agy** — 4/4 clean post-strike re-trial (Task #89 v0.1 + round-2 + NW-7 v0.1 + Task #90 v0.1). Re-instatement holds.
- **Grok** — 2/2 clean. Unique value: telemetry granularity; transitional-debt awareness.
- **Qwen** — 4/4 clean. Unique value: codebase-grounded analysis (verified no UNWIND precedent); edge-case probing.

Panel stays at 5 reviewers for v0.3 / future deep-design reviews.
