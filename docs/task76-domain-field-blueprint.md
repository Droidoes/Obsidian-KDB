# Task #76 — Round 5 `domain` field implementation (blueprint v1)

**Status:** v1 draft — **awaiting Codex + Gemini external review.**
**Authored:** 2026-05-21.
**Lineage:** Round 5 §7.3 (C2 calibration: domain-as-coordinate, not gate) → Task #75 §6.1 (narrowed precondition) → this task.
**Pattern:** mirrors Task #74 and Task #75 — Codex 2-round + Antigravity/Gemini 2-round before implementation.

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
2. **Recommends Option B** with `sub_domain` parked as a `STRING`
   property on the `BELONGS_TO` edge — defers Option C's PART_OF
   hierarchy as YAGNI for current scale.
3. Predeclares the compiler-side delta (prompt + `compile_result.schema.json`
   additive field), graph-side delta (schema bump 2.0 → 2.1: new
   `Domain` node table + new `BELONGS_TO` rel table + non-destructive
   `_migrate_2_0_to_2_1`), adapter delta, and test plan.
4. Surfaces 10 Open Questions (OQ-1..OQ-10) covering tagging
   granularity, multi-domain semantics, name normalization, backfill,
   alias propagation, multi-source consensus, and operator inspection.

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

The edge `Entity → Domain` capturing membership. Carries provenance
properties: `run_id`, `created_at`, optionally `confidence` (OQ-5),
optionally `sub_domain` (Option B).

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
| Compiler | Prompt extension — ask LLM for `domain` (and optional `sub_domain`) per entity. `compile_result.schema.json` gains optional `domain: string` and `sub_domain: string` per page object. |
| GraphDB-KDB | Schema bump `2.0 → 2.1`. New `Domain` node table + `BELONGS_TO` rel table (Option B) added by additive migration `_migrate_2_0_to_2_1`. |
| Adapter | Phase 3.x (ingest) reads `domain` from compile_result, upserts `Domain` nodes, creates `BELONGS_TO` edges. |
| Tests | DDL/migration tests in `test_schema.py`. Adapter tests for new tables + edge upsert. Probe queries in `test_analytics.py` if any (likely none — §7 lays this out). |
| Docs | This blueprint + (in v2) `CODEBASE_OVERVIEW.md` documentation-index pointer + §5 schema doc updated. |

### 3.2 Out of scope (deferred to other tasks)

| Task | What |
|------|---|
| #78+ | Per-op blueprints — PPR, community routing, subgraph extraction implementations (Task #75 V1 roster). |
| #77 | Probe-set curation (Task #75 §6.2). |
| Future | Domain vocabulary controls / normalization rules (if OQ-3 surfaces a need). |
| Future | `graphdb-kdb domains list` and other domain-inspection CLI (OQ-7). |
| Future | Domain-stratified PPR / domain-filtered subgraph extraction (per-op refinements). |
| Future | Domain hierarchy (PART_OF) — Option C, deferred as YAGNI. |

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

### 5.3 What's still open inside Option B

Locking Option B does not finish design. The OQs in §8 still need
review-stage answers — especially OQ-1 (granularity), OQ-2 (multi-
domain cap), OQ-3 (name normalization), OQ-9 (multi-source consensus),
OQ-10 (alias propagation). Those are downstream of the storage
choice but upstream of the compiler-prompt and adapter blueprints in §6.

---

## 6. Detailed blueprint (assumes Option B)

### 6.1 Compiler-side delta

**Prompt extension** (in `KDB-Compiler-System-Prompt.md` and the
per-call rendered prompt):

Add a directive in the page-emission section:

> For each page, emit a `domain` field — a short lowercase string
> naming the primary subject area the page belongs to (e.g.,
> `"investing"`, `"buddhism"`, `"machine-learning"`,
> `"chinese-history"`). If the page touches more than one subject
> area, emit a list `domain: ["investing", "biography"]`. Optionally
> emit a narrower label as `sub_domain` (e.g., `"value-investing"`).

**Schema delta** (`kdb_compiler/schemas/compile_result.schema.json` —
additive optional fields on each `pages[]` entry):

```json
{
  "domain": {
    "oneOf": [
      {"type": "string", "minLength": 1, "maxLength": 64},
      {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 64}, "minItems": 1, "maxItems": 5}
    ],
    "description": "LLM-extracted subject area(s) the page belongs to. Lowercase plain-string; no controlled vocabulary."
  },
  "sub_domain": {
    "type": "string",
    "minLength": 1,
    "maxLength": 64,
    "description": "Optional narrower subject-area label."
  }
}
```

Both fields are **optional** to preserve backwards-compatibility with
existing journals (D39 replay-eligibility).

**Producer-contract delta** (`docs/graphdb-kdb-producer-contract.md` §3
or §4):

Document `domain` and `sub_domain` as optional pass-through fields the
compiler emits and the adapter ingests. Pre-existing producers without
these fields remain valid (the adapter treats missing as "no domain
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

### 6.3 Adapter delta (ingest path)

In whichever adapter phase handles per-page ingest (the equivalent of
where `Entity` upsert happens today — likely Phase 3 in the existing
adapter):

```python
# Pseudocode — replace with actual adapter code paths in v2 of this blueprint
def _ingest_page_domains(conn, entity_slug, page_dict, run_id, created_at):
    domains = page_dict.get("domain")
    if domains is None:
        return  # legacy journal or LLM chose not to tag — skip
    if isinstance(domains, str):
        domains = [domains]
    sub_domain = page_dict.get("sub_domain")
    for d in domains:
        # OQ-3 recommended normalization: lowercase + strip + space→dash.
        # Collapses "Investing", "investing", "Value Investing", "value-investing"
        # into a small canonical set. Confidence capture deferred per OQ-5.
        d_norm = re.sub(r"\s+", "-", d.strip().lower())
        # MERGE Domain
        conn.execute(
            "MERGE (d:Domain {name: $name}) "
            "ON CREATE SET d.created_at = $ts, d.first_run_id = $run_id",
            {"name": d_norm, "ts": created_at, "run_id": run_id},
        )
        # MERGE BELONGS_TO edge (one per (entity, domain) pair; re-emit
        # updates run_id/created_at; sub_domain captured on first write).
        conn.execute(
            "MATCH (e:Entity {slug: $slug}), (d:Domain {name: $name}) "
            "MERGE (e)-[r:BELONGS_TO]->(d) "
            "ON CREATE SET r.run_id = $run_id, r.created_at = $ts, "
            "              r.sub_domain = $sub "
            "ON MATCH SET r.run_id = $run_id, r.created_at = $ts",
            {"slug": entity_slug, "name": d_norm, "run_id": run_id,
             "ts": created_at, "sub": sub_domain},
        )
```

Notes:
- Normalization at ingest = `lower() + strip() + whitespace→dash` per
  OQ-3 recommended. Collapses LLM casing/spacing drift into a small
  Domain set, protecting HW-3.
- `MERGE` ensures idempotency — re-running the same journal does not
  duplicate Domain or edges.
- `ON CREATE` vs `ON MATCH`: re-ingest refreshes `run_id`/`created_at`
  but preserves `sub_domain` from first capture (avoids oscillation
  when different sources emit different sub_domain tags — see OQ-9).
- `confidence` column omitted per OQ-5 recommended (skip). If OQ-5
  resolves to "capture", restore the column in §6.2 DDL + this
  pseudocode.

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

---

## 7. Test plan

### 7.1 Schema/migration tests (`graphdb_kdb/tests/test_schema.py`)

- `test_v2_1_schema_creates_domain_and_belongs_to`: rebuild from
  scratch, assert tables present.
- `test_migrate_2_0_to_2_1_is_idempotent`: migrate twice, no errors,
  no duplicate tables.
- `test_migrate_2_0_to_2_1_preserves_existing_entities`: seed v2.0
  with N Entities, migrate, assert N entities still present + zero
  BELONGS_TO edges.
- `test_v2_1_supported_journal_versions`: adapter still accepts
  journals v2.2 (no version bump needed if `domain` is optional).

### 7.2 Adapter tests

- `test_ingest_page_with_string_domain`: page emits
  `domain: "investing"` → one Domain node, one BELONGS_TO edge.
- `test_ingest_page_with_list_domain`: page emits `domain:
  ["investing", "biography"]` → two BELONGS_TO edges to two Domains.
- `test_ingest_page_with_sub_domain`: edge captures
  `sub_domain` property.
- `test_ingest_page_without_domain`: page has no `domain` field →
  ingest succeeds, no BELONGS_TO edge, no Domain node.
- `test_reingest_idempotency`: same journal applied twice → no
  duplicate Domain nodes, no duplicate edges.
- `test_alias_entity_domain_propagation`: alias Entity (canonical_id
  set) — per OQ-10's resolution, either inherits domain via traversal
  or has its own edges.

### 7.3 Live-graph probe (optional, in `test_analytics.py`)

Once a real run with `domain`-emitting LLM output completes:

- Query `MATCH (d:Domain) RETURN count(d)` and confirm > 0.
- Query distinct-domain count vs entity count — sanity check (we
  expect ≪ entity count, ≥ 1).

These are smoke tests, not gates.

### 7.4 What we are **not** testing in #76

- The community/domain-ratio gate itself (that's Task #79+/community-impl).
- HW-3 hedge-watch behavior (that's Task #79+).
- Domain accuracy or LLM-tagging quality (that's a future scoring task
  if needed; out of scope per "no controlled vocabulary" stance).

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

**Lean: (a) Entity-level.** Matches §7.3 literal query; preserves
granularity; aligns with "LLM-extracted at compilation". The cost is
slightly more LLM tokens per page — acceptable.

### OQ-2 — Multi-domain cap

If Entity-level (OQ-1.a), should we cap how many domains a single
Entity can have? §7.3 says "domain(s)" (plural). Schema allows
`maxItems: 5` in the JSON schema as a soft cap.

- (a) No cap — accept whatever LLM emits.
- (b) Soft cap N=5 in compile_result.schema.json; LLM-prompt also
  asks for "1–3 domains max".
- (c) Hard cap N=1 (force a primary domain).

**Lean: (b).** Plural anticipated, but if LLM goes wild and emits 10
domains per entity, the Domain table inflates with low-signal tags.
Soft cap protects without forbidding.

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

**Lean: (a).** Protects HW-3 distinct-domain count from arbitrary
LLM-output drift; cheap and reversible (we can see if (a) over-
collapses by inspecting the Domain set after the first compile
cycle). We deliberately do *not* introduce a richer domain-
canonicalization layer (Task #74-shaped Levenshtein/LLM-judge work)
unless aggressive-normalize proves insufficient.

### OQ-4 — `sub_domain` shape: edge property or child node?

Recommended Option B parks `sub_domain` as a STRING property on the
BELONGS_TO edge. The alternative (Option C's `PART_OF` child node) is
deferred. Reviewers: does the property-on-edge choice break any
queries you'd want to write? Specifically: "show me all entities in
any sub-domain of `investing`" is hard with property-on-edge (you'd
need to know the sub-domain names upfront).

**Lean: stay with property-on-edge.** If sub-domain-traversal becomes
a real need, promote to Option C in a follow-up task.

### OQ-5 — Capture `confidence` on `BELONGS_TO`?

The §3 schema example `confidence STRING` (high/medium/low) mirrors
what `compile_result.json` already does for entity confidence. Three
positions:

- (a) Capture: ask LLM for domain confidence per tag; store on edge.
- (b) Skip: we don't have any current query that filters by
  domain-confidence; YAGNI.
- (c) Capture as edge property but don't ask LLM for it — derive from
  page-level confidence as a proxy.

**Lean: (b) skip.** No current query needs it. Promotable later.
Removing the `confidence STRING` from §6.2 DDL if (b) is selected.

### OQ-6 — Backfill: lazy (B1) or eager (B2)?

§6.4 leans B1 (lazy — entities get domain on next compile). B2 (eager
full re-compile) costs LLM tokens but gives immediate coverage.

**Lean: B1.** Single-user, no urgency, gate is diagnostic. User can
fire B2 anytime via `kdb-compile --all`.

### OQ-7 — Operator inspection CLI?

Should #76 ship a `graphdb-kdb domains list` command (or similar) for
operator inspection? Trivial to add (one Cypher query). Or defer.

- (a) Include in #76 — small surface, useful while bootstrapping.
- (b) Defer to a future ergonomics task.

**Lean: (a).** Tiny addition; valuable for inspecting LLM output
early. Command: `graphdb-kdb domains list` → prints
`name, n_entities, first_run_id` per Domain.

### OQ-8 — Compile_result.schema.json — additive only?

`domain` and `sub_domain` are documented as **optional** additive
fields on `pages[]`. This preserves D39 replay-eligibility for older
journals.

- (a) Additive only — old journals replay fine; new journals can
  carry `domain`.
- (b) Bump journal `schema_version` to 2.3 and gate ingest.

**Lean: (a).** Matches the Task #74 canonical_meta precedent (added
optionally without journal-version bump). Adapter handles "domain
missing" gracefully by skipping the BELONGS_TO insert.

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

**Lean: (a) additive.** Matches the "coordinate, not gate" stance —
we capture all signals; queries can filter by edge property
(`run_id`) if needed.

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

**Lean: (a) canonical only.** Cleaner; aligns with "canonical is the
authority" stance from #74. Adapter resolves alias slug → canonical
slug before edge insert (small adapter change to wire into existing
canonicalization helpers). Queries that hit aliases must traverse
`canonical_id` (already required for many post-#74 queries).

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
  review. **Awaiting review.**
