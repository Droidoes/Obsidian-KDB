# Task #76 — Round 5 `domain` field implementation (blueprint v2)

**Status:** v2 — Codex + Gemini external review applied (R1–R12). Working blueprint for implementation.
**Authored:** 2026-05-21 v1 · 2026-05-21 v2.
**Lineage:** Round 5 §7.3 (C2 calibration: domain-as-coordinate, not gate) → Task #75 §6.1 (narrowed precondition) → this task.
**Pattern:** mirrors Task #74 and Task #75 — Codex 2-round + Antigravity/Gemini 2-round before implementation.

**v1 → v2 deltas:** Codex caught a P1 producer-pipeline gap (v1 only patched aggregate schema; per-call schema + `PageIntent` dataclass + `compiler.py:367` rebuild also reject/drop `domain` today — see §6.1). Codex relocated the ingest logic from adapter (wrong layer per producer contract) to `graphdb_kdb/ingestor.py` Phase 3 (see §6.3). Codex flagged migration idempotency test framing (§7.1), rebuilder `_DROP_ORDER` gap (§6.2 + §7.1), OQ-9 provenance overclaim (§8). Gemini caught the multi-domain `sub_domain` ambiguity, supplied stronger normalization regex (§6.3), alias-resolution recipe (§6.3 + OQ-10), and CLI spec (new §6.6). The multi-domain `sub_domain` shape was resolved by reconciled consensus as **omit-when-plural** (R5 locked) — see OQ-4.

---

## 0. TL;DR

Round 5 closed with the C2 calibration: each Entity gets an LLM-extracted
`domain` (and optional `sub_domain`) so that domain becomes a **coordinate
on the graph** — used as a query-time filter dimension or as the reference
set for hedge HW-3 (community-vs-domain-set comparison) — but **not** as
an ingest-time gate. No controlled vocabulary; the LLM names domains in
plain strings.

Path-forward §7.3 sketched the storage shape with the example query
`MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain {name: 'investing'})` but
expressly left "Domain node + BELONGS_TO edge **or equivalent**" to be
decided in this task's graph-side blueprint.

This blueprint:
1. Surfaces three storage options (A: flat field on Entity · B: Domain
   node + BELONGS_TO edge · C: B + hierarchical PART_OF) with pros/cons.
2. **Adopts Option B** with `sub_domain` parked as a `STRING` property
   on the `BELONGS_TO` edge — **valid only when `domain` is a single
   string** (multi-domain pages drop `sub_domain` at ingest per R5
   omit-when-plural lock). Option C's PART_OF deferred as YAGNI.
3. Predeclares the **full producer-pipeline delta** (per-call schema +
   `PageIntent` dataclass + `compiler.py` page rebuild + aggregate
   schema — all four sites; v1 had only patched the aggregate), the
   graph-side delta (schema bump 2.0 → 2.1: new `Domain` node table +
   new `BELONGS_TO` rel table + non-destructive `_migrate_2_0_to_2_1`
   + `rebuilder._DROP_ORDER` update), the **ingestor delta** (in
   `graphdb_kdb/ingestor.py` Phase 3, NOT the adapter — per R2 from
   review), the CLI delta (`graphdb-kdb domains list`), and a test
   plan covering migration / ingest / alias-resolution / multi-domain
   sub_domain-drop / rebuild round-trip.
4. Resolves 10 Open Questions (OQ-1..OQ-10) — all now have reviewer-
   reconciled positions; no open forks remain (see §8).

**Critical narrowing from Task #75:** Task #76 gates the
community/domain-ratio acceptance criterion **only**. PPR, subgraph
extraction, and probe-set curation proceed in parallel without
dependency on `domain`. So #76's scope is bounded and crisp — there is
no fan-out into broader step-3 design.

---

## 1. Context

### 1.1 Round 5 §7.3 — the C2 calibration

`docs/what-is-the-ontology-for.md` §7.3 closes Round 5 with **B + two
calibrations**: (C1) LLM-extracted, not human-defined, ontology; and
(C2) **domain as coordinate, not gate**. C2 is the subject of this
task.

The §7.3 design literal (lines 596–602):

> **Compilation:** add LLM-extracted `domain` + optional `sub_domain`
> field to pages. No controlled vocabulary; the LLM names the domain in
> plain string.
>
> **Queries (later):** domain becomes a filter dimension on the graph —
> `MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain {name: 'investing'})` etc.

The "or equivalent — to be decided in Task #76 graph-side blueprint"
caveat from Task #75 §6.1 means this blueprint chooses the storage
model. The compiler-side intent ("LLM-extracted, no controlled
vocabulary") is locked.

### 1.2 Why now: Task #75 §6.1 narrowed the dependency

Task #75 v2 §6.1 audited which Step-3 operations actually need `domain`
and concluded:

- **Community/domain-ratio acceptance gate** (`n_communities ≥ 1.5 ×
  n_distinct_domains`, §4.2) — **requires** `domain`.
- **HW-3 hedge-watch rule** (community ≈ domain re-discovery) —
  **requires** `domain`.
- PPR · subgraph extraction · typed traversal · probe-set curation —
  **independent** of `domain`.

So Task #76 is the *critical-path* enabler for one specific Step-3
quantitative gate. Without it, the gate cannot close; with it, all
Step-3 operations can proceed.

### 1.3 What's NOT in scope

- **No domain-vocabulary controls.** No allow-list, no normalization
  rules — that's Open Question OQ-3 territory; if we land controls
  later, they're a follow-up task. v1 of #76 captures whatever the LLM
  produces.
- **No reranking/filtering inside any Step-3 op.** PPR doesn't gain a
  domain-stratified mode in #76. Subgraph extraction doesn't filter by
  domain in #76. Those are #78-and-beyond per-op blueprints.
- **No CLI tooling beyond a minimal inspection command** (OQ-7 if we
  decide to include one).

---

## 2. Glossary

### 2.1 `domain`

A short plain-string label (e.g., `"investing"`, `"buddhism"`,
`"machine-learning"`, `"chinese-history"`) describing the subject
matter an Entity primarily belongs to. **LLM-extracted, no controlled
vocabulary.** Cardinality: 1-or-more per Entity (see OQ-2).

### 2.2 `sub_domain`

An optional narrower label refining `domain` (e.g.,
`domain="investing", sub_domain="value-investing"`). **Stored on the
edge** in the recommended Option B (see §5.2). Modeled as a child
`Domain` node + `PART_OF` self-edge in Option C; not supported in
Option A.

### 2.3 `Domain` node (Options B and C only)

A first-class node table in Kuzu whose primary key is the lowercase
plain-string domain name. Populated lazily by ingest — each new domain
string the LLM emits creates a `Domain` node if one does not exist.

### 2.4 `BELONGS_TO` edge (Options B and C only)

The edge `Entity → Domain` capturing membership. v2 schema:
`run_id`, `created_at`, `sub_domain` (nullable; populated only on
single-domain pages per R5). `confidence` skipped per OQ-5; per-source
provenance (`source_id`) deferred per OQ-9/R6.

### 2.5 `PART_OF` edge (Option C only)

The self-edge `Domain → Domain` capturing hierarchical taxonomy
(`value-investing` PART_OF `investing`). Not in scope for the
recommended Option B.

### 2.6 "Coordinate, not gate"

Round 5 §7.3 phrase. Means: domain is an *output* of compilation, used
*at query time* to slice/filter — never used to *reject* sources at
ingest. We do not refuse to ingest sources because their domain is
unfamiliar; we just tag them.

---

## 3. Scope

### 3.1 In scope (this task)

| Side | Change |
|------|---|
| Compiler | Prompt extension — ask LLM for `domain` (and optional `sub_domain`) per entity. Schema updates at four sites (per R1): per-call schema, `PageIntent` dataclass, `compiler.py:367` rebuild, aggregate schema. |
| GraphDB-KDB | Schema bump `2.0 → 2.1`. New `Domain` node table + `BELONGS_TO` rel table (Option B) added by additive migration `_migrate_2_0_to_2_1`. `rebuilder._DROP_ORDER` updated (R4). |
| Ingestor | Phase 3 in `graphdb_kdb/ingestor.py` (per R2 — NOT the adapter) gains `_ingest_page_domains` after `_upsert_entity`; reads `domain` from compile_result, upserts `Domain` nodes, creates BELONGS_TO edges. Alias→canonical lookup built once per run (R7). |
| Adapter | No code changes — adapters in `graphdb_kdb/adapters/*` remain pure dispatch per producer contract. |
| CLI | New `graphdb-kdb domains list` sub-command (§6.6, R9 / OQ-7.a). |
| Tests | DDL/migration/rebuild tests in `test_schema.py`. Ingestor tests covering single/plural domain, sub_domain omit-when-plural, normalization, dedupe, alias resolution. Smoke queries in `test_analytics.py`. |
| Docs | This blueprint + (in follow-up) `CODEBASE_OVERVIEW.md` documentation-index pointer + producer-contract amendment. |

### 3.2 Out of scope (deferred to other tasks)

| Task | What |
|------|---|
| #78+ | Per-op blueprints — PPR, community routing, subgraph extraction implementations (Task #75 V1 roster). |
| #77 | Probe-set curation (Task #75 §6.2). |
| Future | Domain vocabulary controls / Levenshtein-grade canonicalization (if R8 aggressive-normalize proves insufficient empirically). |
| Future | Per-source consensus provenance on BELONGS_TO (R6 deferred — add `source_id` to edge if downstream queries need per-source history). |
| Future | Domain-stratified PPR / domain-filtered subgraph extraction (per-op refinements). |
| Future | Domain hierarchy (PART_OF) — Option C, deferred as YAGNI. |
| Future | Promoted `sub_domain` shape — `[{domain, sub_domain}, ...]` per-domain objects if multi-domain pages ever need per-domain subdomain precision (R5 promotion path). |
| Follow-up | Canonical-only filtering in `graphdb_kdb/analytics.py:29` for any query joining through BELONGS_TO (§7.4 cross-ref). |

### 3.3 Critical-path framing

Task #76 is on the critical path for **one** Step-3 acceptance gate
(community/domain-ratio, §4.2 of Task #75). Other Step-3 work runs in
parallel:

```
Task #76 (domain) ──────► community/domain-ratio gate (Task #75 §4.2)
                          HW-3 hedge (Task #75 §5)
                          domain-stratified ops (#78+, future)

Task #77 (probe set) ──► quantitative gates needing probes
                         (Task #75 §4.1 PPR top-N, §4.3 subgraph)

#78+ (PPR impl)       ──► PPR pass/fail tests (Task #75 §4.1)
#79+ (community impl) ──► community structural gates (Task #75 §4.2)
#80+ (subgraph impl)  ──► subgraph quality tests (Task #75 §4.3)
```

#76, #77, and the per-op implementations have **no inter-dependencies
between each other** — only their respective gates depend on them.

---

## 4. Design options

### 4.1 Option A — flat field on `Entity`

**Storage:**
- `ALTER TABLE Entity ADD domain STRING`
- `ALTER TABLE Entity ADD sub_domain STRING`
- No new node table, no new rel table.

**Query shape:**
```cypher
MATCH (e:Entity {domain: 'investing'}) RETURN e
```

**Cardinality:** 1-domain-per-Entity. Multi-domain would require
comma-split-strings (anti-pattern in graph DBs) or migrating to B
later.

**Pros:**
- Minimum surface area — one migration, no new tables, no upsert
  ceremony in the adapter.
- "Concrete-first" lean-MVP per memory rule (build minimal, extract
  abstraction later).
- Trivially cheap query for the common case `WHERE domain = 'X'`.

**Cons:**
- §7.3 anticipates **"domain(s) it touches"** (plural). A entity like
  `warren-buffett` plausibly belongs to both `investing` and
  `biography` — Option A forces a choice or a string-with-commas hack.
- HW-3 hedge (community-vs-domain-set) needs a **set of distinct
  domains** as a reference; with A, that's `SELECT DISTINCT domain
  FROM Entity` over a string column — fragile if the LLM produces
  drift (`"Investing"` vs `"investing"` vs `"finance"`).
- If we later need plural domains, we re-migrate every Entity row
  (destructive) — worst-case migration cost.
- No place to attach edge-level provenance (`run_id`, `confidence`).

### 4.2 Option B — `Domain` node + `BELONGS_TO` edge ⭐ RECOMMENDED

**Storage:**
```cypher
CREATE NODE TABLE Domain (
    name          STRING PRIMARY KEY,
    created_at    STRING,
    first_run_id  STRING
)

CREATE REL TABLE BELONGS_TO (
    FROM Entity TO Domain,
    run_id      STRING,
    created_at  STRING,
    sub_domain  STRING    -- nullable; LLM's narrower label if emitted.
                          -- `confidence` column deferred per OQ-5 lean.
)
```

**Query shape:**
```cypher
MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain {name: 'investing'})
RETURN e
```

**Cardinality:** native 1-or-more (multiple `BELONGS_TO` edges per
Entity).

**Pros:**
- Matches Round 5 §7.3 literal.
- HW-3 has a first-class enumerable set: `MATCH (d:Domain) RETURN
  d.name` gives the authoritative domain inventory.
- Multi-domain entities are native — no string hacks.
- `Domain` nodes are themselves discoverable / countable / queryable;
  enables future `graphdb-kdb domains list` (OQ-7) trivially.
- Schema bump is purely additive (no destructive rewrites; mirrors the
  `_migrate_1_0_to_2_0` pattern in `graphdb_kdb/schema.py` lines
  120–142).
- Edge-level provenance (`run_id`, `confidence`, `sub_domain`) lives
  exactly where it belongs.
- `sub_domain` as edge property avoids committing to a hierarchy we
  don't have queries for (concrete-first).

**Cons:**
- One extra node table + one extra rel table to maintain.
- Ingest gains an explicit upsert step (`MERGE (d:Domain {name: ...})`).
- Two-hop query is marginally more expressive but marginally heavier
  than flat-field equality (negligible at our scale).

### 4.3 Option C — Option B + hierarchical `PART_OF` self-edge

**Storage:** Option B's tables, plus:
```cypher
CREATE REL TABLE PART_OF (
    FROM Domain TO Domain,
    run_id      STRING,
    created_at  STRING
)
```

**Query shape:**
```cypher
MATCH (e:Entity)-[:BELONGS_TO]->(:Domain)-[:PART_OF*0..]->(d:Domain {name: 'investing'})
RETURN e
```
(matches entities tagged with `investing` or any sub-domain of it)

**Cardinality:** native multi; hierarchical sub-domain traversal first-class.

**Pros:**
- Maximally graph-native; sub-domain queries are full citizens.
- Future-proofs taxonomies (e.g., `quantum-mechanics` PART_OF `physics`
  PART_OF `science`).
- Single source of truth for sub-domain — vs. Option B's edge property
  where sub-domain repeats for every Entity in the same sub-domain.

**Cons:**
- **Speculative** — we have **zero** current queries that traverse
  parent/child domain. The HW-3 hedge and the community/domain-ratio
  gate need a *flat set of distinct domains*, not a hierarchy.
- Variable-length-path queries (`-[:PART_OF*0..]->`) introduce more
  complex Cypher into early step-3 code, hurting readability for
  marginal benefit.
- Violates "concrete-first, extract abstraction later" memory rule —
  we'd be designing the hierarchy without seeing two concrete queries
  that need it.
- LLM extracting *hierarchical* sub-domain reliably is a known-hard
  problem; might rely on us seeding domain relationships
  out-of-band, which moves us off the C1 ("LLM-extracted, no
  controlled vocabulary") track.

---

## 5. Recommendation: Option B

### 5.1 Headline

**Adopt Option B for storage.** `sub_domain` lives as a `STRING`
property on the `BELONGS_TO` edge — *not* as a separate node or
hierarchy. Option C's `PART_OF` is documented as a future possibility,
not part of this task.

### 5.2 Reasoning

1. **§7.3 literal is Option B.** The example query
   `MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain {name: 'investing'})`
   is exactly Option B. Per memory rule "Don't over-ask on settled
   design calls", B is the documented default.
2. **HW-3 needs a first-class Domain set.** Without enumerable Domain
   nodes, hedge-watching "are communities re-discovering domains?"
   relies on `SELECT DISTINCT` over an LLM-output string column, which
   is fragile to casing/spelling drift. With Option B, the Domain set
   is canonical.
3. **Plural is anticipated, not hypothetical.** §7.3's "domain(s) it
   touches" phrasing wasn't aspirational — entities like
   `warren-buffett` (investing + biography), `karl-marx` (history +
   economics + philosophy) are *the common case* in this vault.
4. **`sub_domain` on the edge, not a child node.** We have zero
   queries today that traverse `sub_domain → parent`. Property-on-edge
   captures the LLM's narrower label faithfully without committing to
   a hierarchy. Promotable to Option C later if a real need arises
   (concrete-first principle).
5. **Cost is trivial** — one node table + one rel table; migration is
   purely additive; mirrors `_migrate_1_0_to_2_0` pattern already
   shipped at `graphdb_kdb/schema.py:120`.

### 5.3 What was open inside Option B (resolved in v2)

v1 listed OQ-1 (granularity), OQ-2 (multi-domain cap), OQ-3 (name
normalization), OQ-4 (sub_domain shape with plural domains), OQ-9
(multi-source consensus), OQ-10 (alias propagation) as the
review-stage forks. All are resolved in v2 — see §8 for each OQ's
"Resolved" position. No remaining forks block implementation.

---

## 6. Detailed blueprint (assumes Option B)

### 6.1 Compiler-side delta

> **R1 (Codex P1):** v1 patched only the aggregate `compile_result.schema.json`.
> But live LLM output flows through **four** code-sites that v1 ignored — and the
> per-call schema + `PageIntent` dataclass both currently reject/drop `domain`
> via `additionalProperties: false`. All four sites need additive patches or
> `domain` never reaches the journal.

**Pipeline overview** (where domain plumbs through):

```
LLM response
  → (a) compiled_source_response.schema.json  — per-call validation [REJECTS unknown today]
  → (b) parsed JSON → PageIntent dataclass    — typed model [DROPS unknown today]
  → (c) compiler.py page rebuild               — PageIntent(...) constructor call
  → (d) compile_result.schema.json            — aggregate journal validation [v1 patched this only]
  → adapter ingest (Phase 3 — §6.3)
```

**(a) Per-call schema delta** (`kdb_compiler/schemas/compiled_source_response.schema.json` —
the `pageIntent` definition at line 68; `additionalProperties: false` would
otherwise reject `domain`/`sub_domain`):

```json
{
  "domain": {
    "oneOf": [
      {"type": "string", "minLength": 1, "maxLength": 64},
      {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64}, "minItems": 1, "maxItems": 5}
    ],
    "description": "LLM-extracted subject area(s). Lowercase plain-string; no controlled vocabulary."
  },
  "sub_domain": {
    "type": "string",
    "minLength": 1,
    "maxLength": 64,
    "description": "Optional narrower subject-area label. R5: valid only when `domain` is a single string (multi-domain pages drop sub_domain at ingest)."
  }
}
```

Both fields **optional** — not added to `required` array.

**(b) PageIntent dataclass delta** (`kdb_compiler/types.py:171`):

```python
@dataclass
class PageIntent:
    slug: str
    page_type: PageType
    title: str
    body: str
    status: PageStatus = "active"
    supports_page_existence: list[str] = field(default_factory=list)
    outgoing_links: list[str] = field(default_factory=list)
    confidence: Confidence = "medium"
    # R1: optional fields, default None preserves back-compat with replay
    # of older journals (D39 replay-eligibility).
    domain: Optional[Union[str, list[str]]] = None
    sub_domain: Optional[str] = None
```

**(c) Compiler page rebuild delta** (`kdb_compiler/compiler.py:367`):

```python
pages=[
    PageIntent(
        slug=p["slug"],
        page_type=p["page_type"],
        title=p["title"],
        body=p["body"],
        status=p["status"],
        outgoing_links=list(p.get("outgoing_links", [])),
        confidence=p["confidence"],
        supports_page_existence=[source_id],
        # R1: plumb optional domain fields if LLM emitted them
        domain=p.get("domain"),
        sub_domain=p.get("sub_domain"),
    )
    for p in parsed["pages"]
],
```

**(d) Aggregate schema delta** (`kdb_compiler/schemas/compile_result.schema.json` —
the `pageIntent` definition at line 72; mirror of (a) since `PageIntent.to_dict()`
just calls `dataclasses.asdict`):

Same shape as (a). The aggregate JSON is just a dump of `PageIntent`
dataclasses, so the schemas stay symmetric.

**Prompt extension** (in `KDB-Compiler-System-Prompt.md` and the per-call
rendered prompt):

Add a directive in the page-emission section:

> For each page, emit a `domain` field — a short lowercase string naming
> the primary subject area the page belongs to (e.g., `"investing"`,
> `"buddhism"`, `"machine-learning"`, `"chinese-history"`). If the page
> touches more than one subject area (typically 1–3 max), emit a list
> `domain: ["investing", "biography"]`. Optionally emit a narrower label
> as `sub_domain` (e.g., `"value-investing"`) — sub_domain is only
> meaningful when `domain` is a single string; for multi-domain pages,
> omit `sub_domain`.

**Producer-contract delta** (`docs/graphdb-kdb-producer-contract.md`):

Document `domain` and `sub_domain` as optional pass-through fields the
compiler emits and the adapter ingests via `graphdb_kdb/ingestor.py`
Phase 3 (NOT via adapter Cypher — see §6.3). Pre-existing producers
without these fields remain valid (Phase 3 treats missing as "no domain
captured for this run").

### 6.2 GraphDB-KDB schema delta (`graphdb_kdb/schema.py`)

```python
SCHEMA_VERSION = "2.1"

# Adds to NODE_TABLE_DDL:
"""
CREATE NODE TABLE Domain (
    name          STRING PRIMARY KEY,
    created_at    STRING,
    first_run_id  STRING
)
""",

# Adds to REL_TABLE_DDL:
"""
CREATE REL TABLE BELONGS_TO (
    FROM Entity TO Domain,
    run_id      STRING,
    created_at  STRING,
    sub_domain  STRING   -- nullable; LLM's narrower label if emitted.
                         -- `confidence` column deferred per OQ-5.
)
""",
```

**Migration** (`_migrate_2_0_to_2_1`):

```python
def _migrate_2_0_to_2_1(conn) -> None:
    """Bring a v2.0 DB up to v2.1 in place (non-destructive).

    Changes:
      - New node table Domain (name PK, created_at, first_run_id).
      - New rel table BELONGS_TO (Entity → Domain, run_id, created_at,
        confidence, sub_domain). Empty at migration time; populated by
        adapter on next ingest cycle.
      - `_SchemaMeta.schema_version` updated to "2.1".

    Anchor: docs/task76-domain-field-blueprint.md §5 + §6.2 (#76).
    """
    conn.execute(NODE_TABLE_DDL[2])  # Domain
    conn.execute(REL_TABLE_DDL[3])   # BELONGS_TO
    conn.execute(
        "MATCH (m:_SchemaMeta {key: 'schema_version'}) SET m.value = '2.1'"
    )

MIGRATIONS = {
    ("1.0", "2.0"): _migrate_1_0_to_2_0,
    ("2.0", "2.1"): _migrate_2_0_to_2_1,
}
```

Migration is **non-destructive**: existing Entity rows are untouched;
they have zero outgoing `BELONGS_TO` edges until they're touched by a
recompile cycle that emits `domain`. See §6.4 for backfill choice.

**Rebuilder `_DROP_ORDER` delta** (`graphdb_kdb/rebuilder.py:31` — R4):

Whole-DB rebuild (`graphdb-kdb rebuild`) drops tables in a known order.
Adding new tables without updating `_DROP_ORDER` would leave the new
tables stale across rebuilds (or fail with dependency errors when
rel-table foreign keys still reference dropped node tables). Required
update:

```python
_DROP_ORDER: tuple[str, ...] = (
    "LINKS_TO",
    "SUPPORTS",
    "ALIAS_OF",
    "BELONGS_TO",   # R4: new in v2.1, drop before Entity + Domain
    "Entity",
    "Source",
    "Domain",       # R4: new in v2.1, drop after BELONGS_TO
    "_SchemaMeta",
)
```

### 6.3 Ingestor delta (Phase 3, `graphdb_kdb/ingestor.py`)

> **R2 (Codex P2):** v1 placed the MERGE Domain / MERGE BELONGS_TO
> Cypher in "the adapter" — wrong layer. Per
> `docs/graphdb-kdb-producer-contract.md:331` and
> `graphdb_kdb/adapters/base.py:121`, adapters dispatch compile payloads
> into core ingestion; they do not execute Cypher directly. Domain
> ingest belongs in `graphdb_kdb/ingestor.py` Phase 3 alongside
> `_upsert_entity` / `_replace_outgoing_links` / `_replace_supports_for_source`
> (currently at `ingestor.py:70-77`). Adapters in
> `graphdb_kdb/adapters/obsidian_runs.py` remain pure dispatch.

**Normalizer helper** (R8 stronger regex + R12 reused for `sub_domain`):

```python
import re
from typing import Optional

def _normalize_domain(s: Optional[str]) -> Optional[str]:
    """Aggressive ingest-side normalization for domain/sub_domain strings.

    Pipeline:
      1. Strip + lowercase.
      2. Collapse runs of spaces and dashes into single '-'.
      3. Strip all non-alphanumeric / non-dash characters.

    Examples:
      "Investing"            → "investing"
      "Value Investing"      → "value-investing"
      "value--investing"     → "value-investing"
      "value - investing"    → "value-investing"
      "investing."           → "investing"
      "machine_learning"     → "machinelearning"   (intentionally — '_' is non-alphanum)
      ""  /  None  /  "   "  → None
    """
    if not s or not s.strip():
        return None
    collapsed = re.sub(r"[-\s]+", "-", s.strip().lower())
    stripped = re.sub(r"[^a-z0-9-]+", "", collapsed)
    return stripped or None
```

**Per-page ingest function** (R5 omit-when-plural, R7 alias resolution,
R11 dedupe):

```python
def _ingest_page_domains(
    conn,
    page: dict,
    run_id: str,
    created_at: str,
    alias_to_canonical: dict[str, str],
) -> None:
    """R1+R2+R5+R7+R8+R11+R12: ingest domain tags into Domain nodes +
    BELONGS_TO edges. Called from Phase 3 pass-1, after _upsert_entity.

    Args:
      page: a dict from compiled_sources[*].pages[*]; may carry optional
        `domain` (str | list[str]) and `sub_domain` (str) per §6.1.
      alias_to_canonical: lookup map built from
        `cr["canonical_meta"]["aliases_emitted"]` at Phase 3 entry.
    """
    raw = page.get("domain")
    if not raw:
        return  # legacy journal or LLM chose not to tag

    # R5 (locked consensus): sub_domain valid only when domain is single string.
    if isinstance(raw, str):
        sub_domain = _normalize_domain(page.get("sub_domain"))   # R12
        candidates = [raw]
    else:
        sub_domain = None  # multi-domain: explicit drop (R5 omit-when-plural)
        candidates = list(raw)

    # R11: normalize + dedupe (post-normalize, since "Investing" / "investing"
    # collapse to the same key).
    seen: set[str] = set()
    normalized: list[str] = []
    for d in candidates:
        n = _normalize_domain(d)
        if n and n not in seen:
            seen.add(n)
            normalized.append(n)
    if not normalized:
        return

    # R7 + OQ-10.a: alias resolution — only canonical entities carry
    # BELONGS_TO edges. Page slugs may be canonical or alias; resolve.
    page_slug = page["slug"]
    canonical_slug = alias_to_canonical.get(page_slug, page_slug)

    for d_norm in normalized:
        # MERGE Domain node (lazy creation).
        conn.execute(
            "MERGE (d:Domain {name: $name}) "
            "ON CREATE SET d.created_at = $ts, d.first_run_id = $run_id",
            {"name": d_norm, "ts": created_at, "run_id": run_id},
        )
        # MERGE BELONGS_TO edge — one per (canonical_entity, domain) pair.
        # ON CREATE: stamp sub_domain (only meaningful for single-domain pages).
        # ON MATCH: refresh run_id/created_at; preserve original sub_domain
        #          to avoid oscillation when same entity is re-ingested across
        #          different sources (see OQ-9 — provenance is per-edge, NOT
        #          per-source — that would require source_id on BELONGS_TO).
        conn.execute(
            "MATCH (e:Entity {slug: $slug}), (d:Domain {name: $name}) "
            "MERGE (e)-[r:BELONGS_TO]->(d) "
            "ON CREATE SET r.run_id = $run_id, r.created_at = $ts, "
            "              r.sub_domain = $sub "
            "ON MATCH SET r.run_id = $run_id, r.created_at = $ts",
            {"slug": canonical_slug, "name": d_norm, "run_id": run_id,
             "ts": created_at, "sub": sub_domain},
        )
```

**alias_to_canonical map construction** (at Phase 3 entry,
`ingestor.py` line ~70, before the page loop):

```python
# R7: build alias→canonical lookup once per run, from canonical_meta.
alias_to_canonical: dict[str, str] = {}
canon_meta = cr.get("canonical_meta", {})
for alias_record in canon_meta.get("aliases_emitted", []):
    # alias_record shape per Task #74: {alias_slug, canonical_slug, ...}
    alias_to_canonical[alias_record["alias_slug"]] = alias_record["canonical_slug"]
```

**Phase 3 wire-up** (`ingestor.py:70-77` — pass-1 page loop):

```python
# Phase 3 pass 1 — upsert canonical/alias-target Entity nodes, then domains.
for cs in cr.get("compiled_sources", []):
    for page in cs.get("pages", []):
        _upsert_entity(conn, page, run_id, now, result)
        _ingest_page_domains(conn, page, run_id, now, alias_to_canonical)  # NEW
```

**Notes:**
- **Idempotency** — `MERGE` ensures re-running the same journal does
  not duplicate Domain nodes or BELONGS_TO edges.
- **Provenance scope** — `r.run_id` is overwritten on re-match. A real
  per-source provenance trail would require adding `source_id` to
  BELONGS_TO and switching from `MERGE (e)-[:BELONGS_TO]->(d)` to
  `MERGE (e)-[:BELONGS_TO {source_id: $src}]->(d)`. Deferred per OQ-9
  lean — not on the critical path for community/domain-ratio gate or
  HW-3. Documented as a follow-up if downstream queries need it.
- **Canonical-only tagging** — alias entities (`canonical_id IS NOT NULL`)
  have zero outbound BELONGS_TO edges. Downstream analytics queries
  that count "entities per domain" must filter to canonical entities
  (`WHERE e.canonical_id IS NULL`) OR resolve aliases before joining —
  see §7.4 cross-ref note for `graphdb_kdb/analytics.py:29`.
- **`confidence` column omitted** per OQ-5 lean (skip). If OQ-5 ever
  flips to "capture", restore the column in §6.2 DDL + this code path.

### 6.4 Backfill strategy

The migration leaves existing v2.0 Entity rows with **zero**
`BELONGS_TO` edges. Two backfill paths:

**B1 — Lazy (recommended).** Don't actively backfill. Existing
entities get domains on their next compile cycle. Acceptable because
(i) the corpus is small (4 sources today), (ii) we typically recompile
sources as we touch them, (iii) the community/domain-ratio gate is
diagnostic, not blocking.

**B2 — Eager full re-compile.** Recompile all 4 sources once
post-migration to populate `domain` on all entities. Higher LLM cost
but immediate full coverage. User fires this manually per memory rule
"user fires API-cost runs themselves".

**Recommendation:** ship **B1** by default; user decides whether to
fire B2 after the migration ships.

### 6.5 Query examples (for CODEBASE_OVERVIEW v2 docs)

```cypher
-- All entities in the investing domain
MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain {name: 'investing'})
RETURN e.slug, e.title

-- Multi-domain entities (≥ 2 domains)
MATCH (e:Entity)-[r:BELONGS_TO]->(d:Domain)
WITH e, count(d) AS n_domains
WHERE n_domains >= 2
RETURN e.slug, n_domains
ORDER BY n_domains DESC

-- Distinct-domain count (for community/domain-ratio gate)
MATCH (d:Domain) RETURN count(d) AS n_distinct_domains

-- Entities with sub_domain
MATCH (e:Entity)-[r:BELONGS_TO]->(d:Domain)
WHERE r.sub_domain IS NOT NULL
RETURN e.slug, d.name, r.sub_domain
```

### 6.6 CLI command delta — `graphdb-kdb domains list` (R9)

Per OQ-7 lean (include in #76 — small surface, observability while
bootstrapping). One Cypher behind the new sub-command:

```cypher
MATCH (e:Entity)-[:BELONGS_TO]->(d:Domain)
WHERE e.canonical_id IS NULL       -- canonical-only per OQ-10.a
RETURN d.name AS domain,
       count(e) AS entities,
       d.first_run_id AS first_run
ORDER BY entities DESC
```

Output format (tabular):

```
domain                  entities  first_run
investing                     12  run-20260521-0942
buddhism                       7  run-20260518-1730
machine-learning               5  run-20260520-0830
chinese-history                3  run-20260514-2015
```

Implementation lives in `graphdb_kdb/cli/domains.py` (or in the existing
CLI module if a `domains` sub-command isn't yet split out). The handler
opens the GraphDB read-only, runs the query above, and prints a
fixed-width table. No flags in v1.

---

## 7. Test plan

### 7.1 Schema/migration tests (`graphdb_kdb/tests/test_schema.py`)

- `test_v2_1_schema_creates_domain_and_belongs_to`: rebuild from
  scratch, assert `Domain` node table and `BELONGS_TO` rel table present.
- **`test_migrate_2_0_to_2_1_is_idempotent_via_double_open` (R3 Codex P2):**
  per `graphdb_kdb/schema.py:110`, migration idempotency is the *caller's*
  job — `_ensure_schema()` runs migrations at most once per
  (from→to) pair. So the test is "open the DB twice; first open runs
  the migration, second open is a no-op", **NOT** "call
  `_migrate_2_0_to_2_1(conn)` twice in a loop" (which would crash on
  duplicate-table errors per migration semantics).
- `test_migrate_2_0_to_2_1_preserves_existing_entities`: seed v2.0
  with N Entities + M Sources + alias edges, migrate, assert all
  original rows still present + zero BELONGS_TO edges + zero Domain nodes.
- **`test_rebuild_includes_belongs_to_and_domain` (R4 Codex P2):**
  `graphdb-kdb rebuild` enumerates tables via
  `_DROP_ORDER` (`rebuilder.py:31`). Add a test that runs a full
  rebuild against a populated v2.1 DB and confirms (i) drop succeeds,
  (ii) re-create succeeds, (iii) round-trip preserves no stale tables.
- `test_v2_1_journal_compat`: adapter still accepts older journals
  without `domain` / `sub_domain` fields (per R1 — both fields are
  optional).

### 7.2 Ingestor + adapter tests (`graphdb_kdb/tests/test_ingestor.py`)

**Single-domain (R5 single-string allows sub_domain):**
- `test_ingest_page_with_string_domain`: page emits
  `domain: "investing"` → one Domain node, one BELONGS_TO edge,
  `r.sub_domain IS NULL`.
- `test_ingest_page_with_string_domain_and_sub_domain`: page emits
  `domain: "investing"`, `sub_domain: "value-investing"` → edge
  captures normalized `sub_domain` property.

**Multi-domain (R5 omit-when-plural):**
- `test_ingest_page_with_list_domain`: page emits
  `domain: ["investing", "biography"]` → two BELONGS_TO edges to two
  Domain nodes; both edges have `sub_domain IS NULL`.
- **`test_ingest_page_plural_domain_drops_sub_domain` (R5 critical):**
  page emits `domain: ["investing", "biography"]`,
  `sub_domain: "value-investing"` (LLM mis-emission) → ingest succeeds,
  two edges created, **both edges have `sub_domain IS NULL`** —
  sub_domain silently dropped per R5 omit-when-plural lock. No warning
  required.

**Normalization (R8 + R11 + R12):**
- `test_normalize_domain_collapses_drift`: feed
  `["Investing", "investing", "value--investing", "value-investing",
  "Value Investing"]` separately as `domain` strings → 2 distinct
  Domain nodes total (`investing` + `value-investing`), not 5.
- `test_normalize_domain_strips_punctuation`: `"investing."` →
  Domain `investing`; `"machine, learning"` → Domain
  `machine-learning`.
- `test_normalize_sub_domain`: `sub_domain: "Value Investing"` →
  edge `r.sub_domain == "value-investing"` (R12 — same normalizer
  applied to sub_domain).
- `test_dedupe_after_normalize`: page emits
  `domain: ["Investing", "investing", "INVESTING"]` → exactly one
  BELONGS_TO edge (R11).

**Alias resolution (R7 + OQ-10.a):**
- `test_alias_page_tags_canonical_entity`: page has alias slug
  (e.g., `oracle-of-omaha`) with `domain: "investing"`,
  `canonical_meta.aliases_emitted` maps it to `warren-buffett`. After
  ingest, BELONGS_TO edge connects `warren-buffett` (canonical),
  **not** `oracle-of-omaha`.
- `test_canonical_only_no_alias_edges`: post-ingest,
  `MATCH (e:Entity)-[:BELONGS_TO]->() WHERE e.canonical_id IS NOT NULL
  RETURN count(*)` returns 0.

**Idempotency + edge cases:**
- `test_ingest_page_without_domain`: page omits `domain` field
  entirely → ingest succeeds, no BELONGS_TO edge, no Domain node.
- `test_reingest_idempotency`: same journal applied twice → no
  duplicate Domain nodes, no duplicate edges; `r.run_id` /
  `r.created_at` refreshed but `r.sub_domain` preserved from first
  insert.
- `test_empty_string_domain_treated_as_missing`:
  `domain: ""` / `domain: "  "` → treated as missing (normalizer
  returns None), no edge created.

### 7.3 Live-graph probe (optional, in `test_analytics.py`)

Once a real run with `domain`-emitting LLM output completes:

- Query `MATCH (d:Domain) RETURN count(d)` and confirm > 0.
- Query distinct-domain count vs canonical-entity count — sanity check
  (we expect ≪ entity count, ≥ 1).

These are smoke tests, not gates.

### 7.4 Downstream filtering — not in #76, but required (cross-ref)

**Codex P2 OQ-10 follow-up:** Once alias entities exist (Task #74),
the existing `graphdb_kdb/analytics.py:29` loader walks every Entity
row without filtering by `canonical_id`. After #76 lands, any
domain-coverage or community/domain-ratio query that joins
through BELONGS_TO must filter to canonical entities
(`WHERE e.canonical_id IS NULL`) — otherwise counts will be skewed by
aliases (which deliberately carry no edges).

This filtering work is **not in #76**. It's surfaced here so the
follow-up tasks (#79+/community-impl that builds the gate) wire it in.
The new `graphdb-kdb domains list` CLI in §6.6 demonstrates the
correct pattern.

### 7.5 What we are **not** testing in #76

- The community/domain-ratio gate itself (that's Task #79+/community-impl).
- HW-3 hedge-watch behavior (that's Task #79+).
- Domain accuracy or LLM-tagging quality (that's a future scoring task
  if needed; out of scope per "no controlled vocabulary" stance).
- Per-source provenance trail on BELONGS_TO (deferred per OQ-9 — see §6.3 notes).

---

## 8. Open Questions (for Codex + Gemini review)

### OQ-1 — Tagging granularity: Entity-level or Source-level?

§7.3's wording is mixed: "tag sources/pages with a `domain`" and
"domain(s) it touches" appear in adjacent sentences. The literal
example query targets `Entity`. Two readings:

- **(a) Entity-level (this blueprint's default):** each Entity gets
  its own domain tag(s). High granularity; "Warren Buffett" can be
  tagged independently of the source's main subject.
- **(b) Source-level fanned out:** each Source has a single
  `domain` tag, propagated to all Entities it touches via SUPPORTS.
  Cheaper LLM-side (one tag per source vs N per page) but
  fan-out can over-tag (a Buddhism essay quoting Buffett shouldn't
  make `warren-buffett` Buddhism).
- **(c) Both:** Source has `domain`; Entity also has `domain`. Two
  signals; queries can use either.

**Resolved (R10, both reviewers concur): (a) Entity-level.** Matches
§7.3 literal query and preserves granularity. Crucially, source-level
fan-out (b) would over-tag generic entities mentioned in specific
sources (e.g., tagging `google` or `gpu` as `deep-learning` because
they appear in an ML paper), resulting in high graph entropy and
degraded domain-filtering precision. The slightly higher token cost is
acceptable.

### OQ-2 — Multi-domain cap

If Entity-level (OQ-1.a), should we cap how many domains a single
Entity can have? §7.3 says "domain(s)" (plural). Schema allows
`maxItems: 5` in the JSON schema as a soft cap.

- (a) No cap — accept whatever LLM emits.
- (b) Soft cap N=5 in compile_result.schema.json; LLM-prompt also
  asks for "1–3 domains max".
- (c) Hard cap N=1 (force a primary domain).

**Resolved (R10 + R11): (b) Soft cap N=5.** Plural is anticipated, but
a soft cap protects the coordinate space from dilution while still
supporting realistic polymath entities (`karl-marx` →
history + economics + philosophy). The prompt asks for 1–3 domains;
the schema enforces a hard ceiling at 5. **R11 add-on:** dedupe after
ingest-side normalization — if the LLM emits
`["Investing", "investing"]` the cap counts them once, not twice.

### OQ-3 — Domain name normalization

LLMs produce variants: `"Investing"` / `"investing"` /
`"value investing"` / `"value-investing"` / `"Value Investing"`. Three
positions:

- **(a) Aggressive normalize at ingest:** `lowercase + strip +
  whitespace→dash`. Collapses all five examples above to one canonical
  form (`"investing"` or `"value-investing"`). This is what §6.3
  pseudocode does.
- **(b) Minimal normalize at ingest:** `lowercase + strip` only.
  `"value investing"` and `"value-investing"` remain distinct Domain
  nodes; only casing drift collapses.
- **(c) Accept drift verbatim:** ingest as-is; queries do their own
  case-folding. Distinct-domain count is inflated by every LLM
  variant.

**Resolved (R8 + R10 + R12): (a) Aggressive normalize at ingest** —
upgraded regex per Gemini Revision 3.3:

```python
re.sub(r"[^a-z0-9-]+", "", re.sub(r"[-\s]+", "-", s.strip().lower()))
```

Collapses casing, spacing, dashes, and strips trailing punctuation
(handles `"investing."`, `"value--investing"`, `"value - investing"`,
`"Value Investing"` → all canonicalize to one form). Protects the
HW-3 distinct-domain count and stabilizes the
community/domain-ratio gate input. **R12 add-on:** the same normalizer
applies to `sub_domain`. Richer canonicalization layers
(Task #74-shaped Levenshtein/LLM-judge) deferred until aggressive
normalize proves insufficient empirically.

### OQ-4 — `sub_domain` shape with multi-domain entities (R5 LOCKED)

**Resolved (R5, reconciled consensus — Codex + Gemini converged):**
`sub_domain` is v1 observability metadata, **scoped only to
single-domain pages**. Multi-domain entities get BELONGS_TO edges with
`sub_domain = NULL` regardless of whether the LLM emitted one. This is
an explicit, reversible v1 constraint — **not** a claim that
subdomains are globally unimportant.

The decision rule applied: **choose the least ambiguous shape that
preserves the critical path.** sub_domain is not on the critical path
(no acceptance gate consumes it); domain is. Per-domain-object shapes
(`[{name, sub_domain}, ...]`) and primary-domain-only assignment both
solve a non-critical ambiguity by adding producer-contract complexity
before any query needs the precision.

**Schema implications:**
- `compiled_source_response.schema.json` + `compile_result.schema.json`
  document the constraint in the field description (soft).
- `_ingest_page_domains` enforces it hard (see §6.3 — `sub_domain =
  None` when `domains` is a list).
- Plural-domain + LLM-emitted `sub_domain` (a misuse) is silently
  dropped (test `test_ingest_page_plural_domain_drops_sub_domain`
  in §7.2 covers this).

**Promotion path if a future query needs domain-specific subdomains:**
either (a) promote to per-domain tag objects `[{domain, sub_domain},
...]` in a follow-up task, or (b) adopt Option C's `PART_OF` child
node. Both are clean schema migrations — by avoiding either today, we
keep v1 minimum-viable.

### OQ-5 — Capture `confidence` on `BELONGS_TO`?

The §3 schema example `confidence STRING` (high/medium/low) mirrors
what `compile_result.json` already does for entity confidence. Three
positions:

- (a) Capture: ask LLM for domain confidence per tag; store on edge.
- (b) Skip: we don't have any current query that filters by
  domain-confidence; YAGNI.
- (c) Capture as edge property but don't ask LLM for it — derive from
  page-level confidence as a proxy.

**Resolved (R10): (b) Skip.** Page-level confidence already exists;
edge confidence is YAGNI overhead. `confidence STRING` removed from
§6.2 DDL. Promotable later if a real query needs it.

### OQ-6 — Backfill: lazy (B1) or eager (B2)?

§6.4 leans B1 (lazy — entities get domain on next compile). B2 (eager
full re-compile) costs LLM tokens but gives immediate coverage.

**Resolved (R10): B1 (Lazy).** Single-user, no urgency, gate is
diagnostic; prevents automatic high-cost LLM API calls during
migration. User fires B2 manually via `kdb-compile --all` per memory
rule "user fires API-cost runs themselves".

### OQ-7 — Operator inspection CLI?

Should #76 ship a `graphdb-kdb domains list` command (or similar) for
operator inspection? Trivial to add (one Cypher query). Or defer.

- (a) Include in #76 — small surface, useful while bootstrapping.
- (b) Defer to a future ergonomics task.

**Resolved (R9 + R10): (a) Include.** Tiny addition; valuable for
inspecting LLM domain-extraction behavior during bootstrapping.
Command and Cypher spec'd in §6.6. The query is canonical-only-filtered
per OQ-10.a.

### OQ-8 — Compile_result.schema.json — additive only?

`domain` and `sub_domain` are documented as **optional** additive
fields on `pages[]`. This preserves D39 replay-eligibility for older
journals.

- (a) Additive only — old journals replay fine; new journals can
  carry `domain`.
- (b) Bump journal `schema_version` to 2.3 and gate ingest.

**Resolved (R10): (a) Additive only.** Crucial for D39
replay-eligibility of historical journals. Mirrors the Task #74
`canonical_meta` precedent (added optionally without journal-version
bump). Phase 3 ingestor handles "domain missing" gracefully — early
return in `_ingest_page_domains` (see §6.3).

### OQ-9 — Multi-source domain consensus

If Source A's compile tags `warren-buffett` with `domain="investing"`
and a later Source B's compile tags the same canonical entity with
`domain="biography"`, what's the result?

- (a) **Additive (current §6.3 pseudocode):** Entity has BELONGS_TO
  edges to both `investing` and `biography`. The Domain set grows
  monotonically over compiles.
- (b) **Latest-source-wins:** Drop B's tag if A's exists, or
  overwrite. Domain set risks oscillation.
- (c) **Per-source edges:** edge property names the contributing
  source. Same entity can carry contradictory domain tags scoped to
  source.

**Resolved (R6 + R10): (a) Additive membership, with provenance claim
tightened.** Matches the "coordinate, not gate" stance — Source A
tagging `warren-buffett` as `investing` and Source B tagging the same
canonical entity as `biography` results in both BELONGS_TO edges
existing; the Domain set grows monotonically.

**Codex P2 correction (R6):** v1 claimed "queries can filter by edge
property (`run_id`)" — but the §6.3 `MERGE ... ON MATCH SET r.run_id`
overwrites the run_id on every re-ingest. The edge sees only the
*latest* contributor, not full additive consensus history. So:

- The **set of domains an entity belongs to** is genuinely additive
  (multiple edges, one per (entity, canonical_domain) pair).
- The **per-source provenance trail** for each membership is **NOT**
  captured by the v1 edge shape.

If a downstream query ever needs per-source consensus history (e.g.,
"how many sources agreed Buffett belongs to investing?"), the
required schema change is: add `source_id STRING` to BELONGS_TO and
switch from `MERGE (e)-[:BELONGS_TO]->(d)` to
`MERGE (e)-[:BELONGS_TO {source_id: $src}]->(d)` — yielding one edge
per (entity, domain, source) triple. **Deferred** as YAGNI; no
current query consumes per-source provenance. Documented as the
explicit promotion path.

**Architectural insight from Gemini:** `graphdb-kdb rebuild` purges
stale domain edges from modified/deleted sources automatically by
nature of rebuilding from current journals — no tombstone tracking
needed on the incremental path.

### OQ-10 — Alias entity domain propagation

Post-#74, entities have a `canonical_id` chain. If `the-oracle-of-omaha`
is an alias of `warren-buffett`, do we:

- (a) **Tag canonical only:** only `warren-buffett` gets BELONGS_TO
  edges; aliases pass through via `canonical_id`. Query helpers must
  resolve alias → canonical before joining to Domain.
- (b) **Tag both:** both alias and canonical have BELONGS_TO edges.
  Redundant but query-simple.
- (c) **Tag whichever is observed in the journal:** if the LLM
  output references the alias slug, the alias gets the BELONGS_TO; the
  canonicalization stage rewires it onto canonical post-hoc.

**Resolved (R7 + R10): (a) Canonical only.** Keeps the canonical
entity as the single source of truth; aligns with the Task #74
"canonical is the authority" stance.

**Ingest implementation** (detail in §6.3):

1. At Phase 3 entry, pre-build a fast `alias_to_canonical: dict[str, str]`
   lookup from `cr["canonical_meta"]["aliases_emitted"]`.
2. Inside `_ingest_page_domains`, resolve `page["slug"]` to
   `canonical_slug = alias_to_canonical.get(slug, slug)` before the
   `MERGE BELONGS_TO` clause.
3. The MERGE then targets the canonical Entity. Alias Entity rows
   (materialized in Phase 3.5 at `ingestor.py:79`) carry **zero**
   outbound BELONGS_TO edges.

**Cold-start safety:** Because Phase 3 pass-1 calls `_upsert_entity`
before `_ingest_page_domains` (see §6.3 wire-up), the canonical Entity
row always exists before BELONGS_TO is created. No additional
`MERGE (e:Entity {slug: $canonical_slug})` defensive clause needed.

**Downstream consequence (cross-ref to §7.4):** Any analytics or
gate-evaluation query that joins through BELONGS_TO must filter to
canonical entities (`WHERE e.canonical_id IS NULL`), otherwise counts
will be wrong. `graphdb_kdb/analytics.py:29` is the most prominent
loader that currently doesn't filter — flagged as a follow-up.

---

## 9. References

- `docs/what-is-the-ontology-for.md` §7.3 — Round 5 C2 calibration
  (domain-as-coordinate); §8 — closeout.
- `docs/task75-predeclared-eval-criteria-blueprint.md` §6.1 — narrowing
  of Step-3 dependency on `domain` (this task's scope precondition).
- `docs/task74-canonicalization-blueprint.md` §5 + §8.3 — schema
  migration pattern (`_migrate_1_0_to_2_0`) used as the template for
  `_migrate_2_0_to_2_1` in §6.2.
- `graphdb_kdb/schema.py` — Kuzu DDL + migration registry the v2.1
  delta plugs into.
- `kdb_compiler/schemas/compile_result.schema.json` — compile-result
  schema where optional `domain`/`sub_domain` fields land.
- `docs/graphdb-kdb-producer-contract.md` — producer-contract document
  to amend in §6.1.
- Memory: `feedback_concrete_first_extract_later`, `feedback_dont_overask_settled_calls`,
  `feedback_no_imaginary_risk`, `feedback_user_fires_api_cost_runs`,
  `feedback_gemini_review_only_guardrail`, `project_ontology_purpose_kernel_question`.

---

## 10. Change log

- **2026-05-21 — v1 draft.** Three storage options (A/B/C) surfaced;
  Option B recommended with sub_domain on edge; compiler + graph
  schema delta sketched; 10 OQs surfaced for Codex + Gemini external
  review.
- **2026-05-21 — v2 (this version).** Codex + Gemini external review
  applied. R1–R12 deltas:
  - **R1 (Codex P1):** §6.1 expanded to cover the full producer
    pipeline — per-call schema (`compiled_source_response.schema.json`),
    `PageIntent` dataclass (`kdb_compiler/types.py:171`), compiler page
    rebuild (`kdb_compiler/compiler.py:367`), aggregate schema. v1
    patched only the aggregate; per-call `additionalProperties: false`
    would have rejected the new fields.
  - **R2 (Codex P2):** §6.3 ingest logic relocated from "adapter" to
    `graphdb_kdb/ingestor.py` Phase 3 — adapters are dispatch-only per
    `graphdb-kdb-producer-contract.md`.
  - **R3 (Codex P2):** §7.1 migration idempotency test reframed as
    "open DB twice" (per `schema.py:110` migration semantics — caller
    handles idempotency).
  - **R4 (Codex P2):** §6.2 + §7.1 updated to include
    `rebuilder._DROP_ORDER` patch + round-trip rebuild test.
  - **R5 (LOCKED — Codex + Gemini reconciled consensus):** §6.1, §6.3,
    §7.2, OQ-4 all reflect **omit-when-plural** as the v1
    `sub_domain` rule. Reviewers had initially split (Codex
    "primary-only or omit"; Gemini "primary-only"); reconciled on the
    rule "choose the least ambiguous shape that preserves the
    critical path" → omit-when-plural since sub_domain isn't gate-load-bearing.
  - **R6 (Codex P2):** OQ-9 provenance overclaim tightened — the v1
    `MERGE ... ON MATCH SET r.run_id` overwrites history, so the
    edge shape captures additive *membership* but NOT additive
    *provenance*. Per-source `source_id` deferred as YAGNI with
    explicit promotion path documented.
  - **R7 (Gemini + Codex):** §6.3 + OQ-10 enriched with explicit
    `alias_to_canonical` lookup recipe from `cr["canonical_meta"]["aliases_emitted"]`.
  - **R8 (Gemini):** §6.3 + OQ-3 normalizer upgraded to handle
    `"value--investing"`, `"investing."`, etc. via two-stage regex.
  - **R9 (Gemini):** new §6.6 — `graphdb-kdb domains list` CLI spec
    with canonical-only-filtered Cypher.
  - **R10 (Gemini):** all OQ leans reworded to "Resolved" with concise
    rationale; ambiguity wording removed since reviewers concur.
  - **R11 (Codex):** §6.3 + OQ-2 add post-normalize dedupe.
  - **R12 (Codex):** §6.3 + OQ-3 — same normalizer applied to `sub_domain`.
- **Pending (post-v2 — implementation tasks):** Tests defined in §7
  must be written first; concrete §6.1–§6.6 edits then land as code.
  Per-source provenance schema upgrade (R6 deferred) and
  `analytics.py` canonical filtering (§7.4 cross-ref) are
  follow-up tickets.
