# GraphDB-KDB — Producer Contract

**Version:** v1.0 (frozen 2026-05-23)

**Status:** Input boundary spec for **Task #88 (Ingestion Pipeline)**. End-A (compile-side) development paused at this freeze per the "tunnel from both ends" reframe (see `JOURNEY.md` + memory `project_tunnel_from_both_ends_pivot`). Amendments to this contract require a v1.x bump and notification to active producer/adapter implementers.

**Date:** 2026-05-14 → frozen v1.0 2026-05-23.

**Scope:** The formal contract between GraphDB-KDB (the multi-source ontology system) and any producer (today: Obsidian-KDB's `kdb-compile`; tomorrow: arxiv-compile, youtube-compile, codebase ingester, etc.). Companion to `docs/graphdb-kdb-extraction-roadmap.md` and `docs/manifest-succession-arc.md`.

**Audience:** Anyone authoring a new producer adapter, or auditing an existing one. The Obsidian-KDB compile pipeline serves as the reference implementation throughout this document.

---

## 1. Why this document exists

GraphDB-KDB is positioned as a **multi-source ontology system** (D32-tempered). The storage layer is source-agnostic; the ingestion API contract today is Obsidian-flavored as a pragmatic v1 choice. As the package extraction arc (`docs/graphdb-kdb-extraction-roadmap.md`) progresses and producer #2 arrives, the team needs a clear answer to: **what does GraphDB-KDB require from any producer to support ingestion, replay, and verification?**

Without this contract:

- Future producer authors would reverse-engineer the contract from the Obsidian adapter's code, inheriting Obsidian-specific assumptions.
- Graph-layer refactors could silently break unstated assumptions producers depend on.
- The B-lite adapter pattern's promise ("any producer can feed the graph by writing an adapter") becomes folk wisdom rather than spec.

This document defines the contract explicitly so producers and graph-layer maintainers can negotiate compatibly across versions.

---

## 2. Roles

Three roles in this architecture, with clean boundaries:

| Role | Responsibility | Today |
|---|---|---|
| **Producer** | Emits run-level artifacts (compile output, scan data, run journal, sidecar archives) to a known filesystem location with documented JSON shapes. Owns *what* the data means. | `Obsidian-KDB / kdb-compile` |
| **Adapter** | Bridges producer artifacts to graph mutations. Reads the producer's artifacts by documented JSON contract (no Python import of producer code), translates them to graph operations, calls the GraphDB-KDB core. Owns the *translation*. | `graphdb_kdb.adapters.obsidian_runs` (post-#63.6 B-lite) |
| **GraphDB-KDB core** | Owns Kuzu, the schema, mutation primitives (`apply_compile_result` and equivalent), replay mechanics, verification, query API, analytics. Producer- and adapter-agnostic. Owns the *graph mechanics*. | `graphdb_kdb/{schema, graphdb, ingestor, queries, analytics, verifier, rebuilder}.py` |

**Critical invariant** (literal, as of D-S0 2026-05-14): the core never imports from any producer or adapter. The adapter never imports producer Python types — it reads JSON by contract. Producers never call the GraphDB-KDB core directly — they emit artifacts AND/OR invoke the adapter; the adapter consumes them.

```
                                                       Live sync (Stage 9):
Producer ─emits─► [artifacts on disk] ─reads─► Adapter ─calls─► GraphDB-KDB core
   │                                              ▲
   └──── invokes for live sync ──────────────────┘
         (e.g., kdb_compile.py Stage 9 calls
          obsidian_runs.sync_current_run(...))
```

**Two invocation paths, one adapter**:

1. **Live sync** (per-run, real-time during compile): Producer's pipeline (e.g., `kdb_compile.py` Stage 9) calls `graphdb_kdb.adapters.<producer>_runs.sync_current_run(mutation_payload, scan_payload, run_id)`. The adapter opens a GraphDB connection, calls `apply_compile_result(...)` (or its successor), closes.
2. **Replay** (offline, full history): `graphdb-kdb rebuild` calls into the adapter's `discover_runs() / is_eligible() / load_payload() / apply()` for each historical run.

Both paths share the same adapter module. The discipline boundary is enforced in both directions: producer never reaches into core; core never reaches into producer.

---

## 3. The four artifacts a producer must emit

A compliant producer emits **four kinds of artifacts**. Three are per-run; one is durable. All are JSON files on disk at producer-chosen paths (passed to the adapter as configuration).

**Scope caveat — v1 assumes run-shaped artifacts**: this contract describes producers whose emission pattern is **discrete runs** (a compile pipeline that produces a `compile_result` per invocation; an arxiv-paper batch ingester that processes N papers per run; etc.). Producers with fundamentally different emission patterns (continuous streams, event sourcing without discrete run boundaries, real-time mutations) are **explicitly out-of-contract for v1** — they would require a different abstraction. See OQ-PC3 / OQ-E3. The team's lean: run-shaped is the right v1 primitive; streaming producers, if they arrive, motivate a separate contract document, not a stretch of this one.

### 3.1 Mutation payload (per run)

**Purpose**: the actual content to be applied to the graph. Carries the producer's understanding of "what changed in this run."

**Today's reference (Obsidian-KDB / `compile_result.json`)**:

```
{
  "run_id":            "2026-04-21T17-48-32_EDT",        // required
  "success":           true,                              // required
  "compiled_sources": [                                   // producer-shaped
    {
      "source_id":     "KDB/raw/some-file.md",
      "summary_slug":  "concepts/foo",
      "concept_slugs": ["concepts/foo", "concepts/bar"],
      "article_slugs": [],
      "pages":         [ { slug, title, page_type, outgoing_links, ... }, ... ],
      "compile_meta":  { ... }
    },
    ...
  ],
  "log_entries":       [ ... ],                           // optional / advisory
  "errors":            [ ... ],                           // advisory
  "warnings":          [ ... ]                            // advisory
}
```

**Contract requirements** (what *any* producer's mutation payload must carry):

| Requirement | Why | Notes |
|---|---|---|
| Stable run identifier | Primary key for replay; foreign key on all graph nodes/edges produced by this run. Format: chronologically-sortable. | Producer-chosen field name (Obsidian uses `run_id`); recommended format: ISO-8601 timestamp. Adapter normalizes to a canonical name when invoking core. |
| Source-level entries | The mutation payload must describe *which sources changed* and *what entities/edges they produced* | Shape is producer-specific; adapter translates |
| Entity-level records | Each entity (Page / Concept / Function / Segment / ...) must have a stable identifier the adapter can map to the graph's primary key | Required mapping in adapter; see §3.5 entity-id namespacing |
| Edge records | The relationships emitted between entities; the adapter translates these to `LINKS_TO` edges | Required mapping in adapter |
| Source-attribution records | Which entities each source supports; the adapter translates these to `SUPPORTS` edges | Required mapping in adapter |

**Anti-requirements**: the contract does NOT require:

- A specific top-level key called `compiled_sources` (Obsidian-specific naming).
- A specific concept of `summary` / `concept` / `article` page types (Obsidian-specific values for `page_type`).
- A specific source-ID pattern (Obsidian uses `KDB/raw/<path>`; arxiv would use `arxiv:<arxiv_id>`, etc.).

### 3.2 Scan/state payload (per run)

**Purpose**: the producer's view of *what existed* and *what changed* at the source level for this run. Used by the adapter for reconciliation (MOVED, DELETED).

**Today's reference (Obsidian-KDB / `last_scan.json`)**:

```
{
  "schema_version":     "1.0",
  "run_id":             "2026-04-21T17-48-32_EDT",
  "scanned_at":         "2026-04-21T17:48:32-04:00",
  "vault_root":         "...",
  "raw_root":           "KDB/raw",
  "settings_snapshot":  { ... },
  "summary":            { ... },
  "files":              [ { path, action, current_hash, current_mtime, size_bytes, file_type, is_binary, previous_hash }, ... ],
  "to_compile":         [ ... ],
  "to_reconcile":       [ ... ],   // MOVED + DELETED reconciliation ops
  "to_skip":            [ ... ],
  "errors":             [ ... ],
  "skipped_symlinks":   [ ... ]
}
```

**Contract requirements**:

| Requirement | Why | Notes |
|---|---|---|
| `run_id` (string, matches mutation payload) | Links scan to mutation payload | Required |
| Source inventory (which source files exist this run, with hashes/sizes/types) | Adapter populates `Source` node properties (`hash`, `size_bytes`, `file_type`, etc.) | Required; producer chooses field names; adapter maps |
| Reconciliation ops (MOVED / DELETED operations vs prior run) | Adapter applies `Source.status='moved'/'deleted'`; `moved_to` provenance | Required if producer supports MOVED/DELETED semantics; optional otherwise |

### 3.3 Run journal (per run, durable audit record)

**Purpose**: the audit record of the run — *what happened*, not *what changed*. Drives replay eligibility (D39 filter).

**Today's reference (Obsidian-KDB / `state/runs/<run_id>.json`)**:

```
{
  "schema_version":        "2.0",
  "compiler_version":      "0.1.0-m0",
  "run_id":                "2026-04-21T17-48-32_EDT",
  "started_at":            "...",
  "finished_at":           "...",
  "duration_ms":           99000,
  "success":               true,
  "dry_run":               false,
  "journal_written":       true,
  "manifest_written":      true,
  "compile_success":       true,
  "failure_message":       null,
  "failure_type":          null,
  "failure_stage_name":    null,
  "terminated_at_stage":   null,
  "config":                { ... },
  "stages":                [ ... per-stage records ... ],
  "summary":               { counts, deltas, errors, inputs, log_entries },
  "artifacts":             {
    "compile_result_path": "state/compile_result.json",
    "last_scan_path":      "state/last_scan.json",
    "journal_path":        "...",
    "manifest_path":       "...",
    "resp_stats_dir":      "..."
  },
  "vault_root":            "..."
}
```

**Contract requirements** (eligibility-filter relevant):

| Requirement | Why | Notes |
|---|---|---|
| Stable run identifier (matches payloads) | Cross-reference key | Producer chooses field name; adapter normalizes |
| Run-success signal (bool) | D39 eligibility input | Producer chooses field name (Obsidian uses `success`); adapter normalizes to a canonical eligibility key when reporting to the rebuilder |
| Dry-run signal (bool) | D39 eligibility input — dry-runs are excluded from replay | Producer chooses field name (Obsidian uses `dry_run`); adapter normalizes; default to `false` if producer doesn't model dry-runs |
| Sortable identity (chronologically-sortable run identifier OR explicit `started_at`-style field) | Replay must iterate runs in chronological order | Adapter exposes this as the `sort_key` in `discover_runs()` (see §4) |
| Path to mutation payload | Used by sidecar lookup (see §3.4) for replay | Recommended via `artifacts.<key>_path` or implicit by sidecar convention |
| Journal schema version | Adapters declare which versions they support (PR9 in extraction roadmap) — version mismatch raises `UnsupportedJournalVersionError` | Producer chooses field name (Obsidian uses `schema_version`); adapter declares `supported_journal_versions: list[str]` |
| `event_type` (string, optional) | Discriminates run kinds in one journal stream — `"compile"` (or absent) vs `"cleanup"` (Task #68 retraction event) | Optional; **absent ⇒ `"compile"`** for back-compat with 2.0 journals. A `cleanup` journal is `schema_version: "2.1"`. |

**The "canonical eligibility" indirection**: the contract does NOT require exact field names (`success`, `dry_run`). The contract requires that the *adapter* normalizes producer-specific fields into canonical eligibility values when reporting to the generic replay driver. This preserves producer-shape independence (Obsidian's `success` can be arxiv's `compile_ok` can be youtube's `transcribed: true`) while keeping the rebuilder's interface stable.

**Anti-requirements**: the contract does NOT require specific stage names, specific failure-type taxonomies, or specific summary statistics. These may be present (Obsidian-specific) but the adapter does not need them.

### 3.4 Per-run sidecar archive (durable replay payload)

**Purpose**: preserved copies of `mutation payload` and `scan/state payload` *per run* — so replay can reconstruct any historical run's contributions to the graph.

**Why a sidecar (not embedding inline in the journal)**: the run journal is an audit record (small, scannable). Mutation payloads are large (~40 KB+ today, growing with corpus). Embedding inline bloats the journal; storing alongside keeps each artifact appropriately scoped.

**Today's reference (Obsidian-KDB, post-#63.7)**:

```
state/runs/
├── <run_id>.json                       ← the run journal (already exists)
└── <run_id>/                           ← the sidecar directory (post-#63.7)
    ├── compile_result.json             ← per-run mutation payload archive
    └── last_scan.json                  ← per-run scan/state payload archive
```

**Cleanup-event sidecar (Task #68):** a `cleanup` run's sidecar directory
contains `retraction.json` (the retraction payload — `reaped` audit records +
`retracted_slugs`) instead of `compile_result.json` + `last_scan.json`. The
adapter selects the sidecar contents to require by the journal's `event_type`.

**Contract requirements**:

| Requirement | Why | Notes |
|---|---|---|
| Sidecar directory exists at a path the adapter can locate from `run_id` | Replay payload retrieval | Producer chooses naming; convention: `<journal_path_parent>/<run_id>/` |
| Mutation payload archived per run | D39: `payload_present=true` eligibility predicate | Required for replay support |
| Scan/state payload archived per run | Reconciliation replay | Required if MOVED/DELETED reconciliation must replay correctly |
| Sidecar contents are byte-identical to what would have been ingested live | Replay determinism (`replay(eligible runs) ≡ live ingestion`) | Producer must not regenerate; must archive |

**Producer absence of sidecar**: a producer that does not implement sidecar archival can still feed the graph (Stage 9 live ingestion works), but **cannot support replay** — its rebuilder will report "no eligible runs" because `payload_present` is always false. This is acceptable for one-shot or stateless producers. The Obsidian-KDB producer is committing to sidecar archival in #63.7.

---

### 3.5 Entity ID namespacing (multi-producer convention — D-S1)

When multiple producers co-tenant a single GraphDB-KDB directory, entity IDs must remain globally unique. Convention (locked 2026-05-14):

| Producer status | Entity ID convention | Example |
|---|---|---|
| **Obsidian-KDB (grandfathered)** | Bare slug (no prefix). Treated as the implicit `obsidian:` namespace. | `concepts/attention-mechanism`, `articles/buffett-on-fang-stocks` |
| **All future producers** | Explicit `<source_type>:<entity_id>` prefix. The `<source_type>` matches the discriminator value the adapter writes to `Source.source_type`. | `arxiv:concept-foo`, `youtube:segment-abc`, `code:fn:my_module.do_thing` |

**Rationale**: full retroactive migration of 62+ existing Obsidian entities to `obsidian:concepts/...` would be a destructive schema change with no operational benefit for the canonical corpus. Grandfathering as the default namespace is cheaper and preserves all existing queries.

**Trade-off accepted**: queries that need to filter by producer must use the Source's `source_type` (via `MATCH (s:Source)-[:SUPPORTS]->(e:Entity)`), not parse the entity slug prefix. This is the architecturally cleaner path anyway.

**Collision discipline**: a future producer that emits an entity with the same string as an Obsidian entity (e.g., another producer that uses `articles/buffett-on-fang-stocks` for an unrelated concept) would collide. The `<source_type>:` prefix prevents this. Adapter authors who skip the prefix without explicit team consensus are committing to a permanent reconciliation cost.

**Adapter declaration**: each adapter declares its namespace via `entity_id_namespace: ClassVar[str | None]` — `None` for the grandfathered Obsidian adapter; explicit string for all others. The adapter's `apply()` method prepends the namespace when translating producer-emitted IDs to graph keys.

---

## 4. The adapter interface

The adapter is the producer-specific Python module that lives inside `graphdb_kdb/adapters/<producer>_runs.py`. It implements a small, documented interface that:

- The generic replay driver in `graphdb_kdb/rebuilder.py` calls during **replay**.
- The producer's pipeline (e.g., `kdb_compile.py` Stage 9) calls during **live sync** (D-S0).

**Proposed interface** (subject to refinement during #63.6 implementation):

```python
# graphdb_kdb/adapters/base.py  (conceptual; may be a Protocol or duck-typed)

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

class UnsupportedJournalVersionError(Exception):
    """Adapter received a journal whose schema_version is not in supported_journal_versions.
    Lives in graphdb_kdb.adapters.base (or graphdb_kdb.exceptions, TBD at #63.6)."""

SkipReason = Literal[
    "failed",                   # producer reported run failure (success != true)
    "dry_run",                  # producer reported dry-run (excluded by D39 filter)
    "payload_missing",          # sidecar archive absent or incomplete
    "invalid_journal",          # journal JSON malformed or missing required fields
    "unsupported_version",      # journal schema_version not in supported_journal_versions; adapter raises UnsupportedJournalVersionError eagerly OR returns this skip reason for replay tolerance — choice deferred to #63.6 implementation
]

@dataclass
class RunDescriptor:
    """One discovered run; ordering deferred to core via sort_key."""
    run_id:       str
    sort_key:     str      # ISO-8601 timestamp or equivalent chronologically-sortable string
    journal_path: Path

@dataclass
class EligibilityResult:
    """Structured outcome of is_eligible — preserves skip reason for audit."""
    eligible:    bool
    skip_reason: SkipReason | None   # None iff eligible=True

class ProducerAdapter:
    """Bridge between a producer's filesystem artifacts and GraphDB-KDB mutations."""

    # ── declarations ──────────────────────────────────────────────────────────
    source_type:                ClassVar[str]              # e.g., "obsidian-kdb-raw"
    entity_id_namespace:        ClassVar[str | None]       # None for Obsidian (grandfathered); explicit for others
    supported_journal_versions: ClassVar[list[str]]        # PR9; raise UnsupportedJournalVersionError on mismatch

    # ── replay path ───────────────────────────────────────────────────────────
    def discover_runs(self, journals_dir: Path) -> list[RunDescriptor]:
        """Return all run descriptors (unsorted). Core sorts by sort_key.

        Producer-specific: knows where journals live, what the filename pattern is,
        what the chronological key is.
        """

    def is_eligible(self, descriptor: RunDescriptor) -> EligibilityResult:
        """Read journal JSON at descriptor.journal_path; return structured result.

        Encodes D39 filter (success && !dry_run && payload_present) AND the version
        check. Skip reasons preserved for audit.
        """

    def load_payload(self, descriptor: RunDescriptor) -> tuple[dict, dict, str]:
        """Return (mutation_payload, scan_payload, run_id) for this run.
        Reads sidecar archive at the producer-convention path.
        Adapter normalizes producer field names to whatever core's mutation API expects.
        """

    def apply(self, mutation_payload: dict, scan_payload: dict, run_id: str, conn) -> "SyncResult":
        """Translate producer-flavored payload to graph mutations.

        For Obsidian-KDB v1: calls graphdb_kdb.ingestor.apply_compile_result(...).
        For other producers: calls apply_mutations(...) once the normalized contract exists (OQ-PC3).
        """

    # ── live-sync path (D-S0) ─────────────────────────────────────────────────
    def sync_current_run(self, mutation_payload: dict, scan_payload: dict, run_id: str, graph_dir: Path | None = None) -> "SyncResult":
        """Entry point for producer's live-sync hook (e.g., kdb_compile.py Stage 9).

        Adapter opens a GraphDB connection at graph_dir (or default), calls apply()
        within a transaction, closes. This is the single Obsidian→graph entry point;
        producer code does NOT touch graphdb_kdb.GraphDB or apply_compile_result directly.
        """
```

**Critical adapter rules**:

1. **No Python import of producer code.** The adapter parses producer JSON artifacts by documented field names. It does not `from kdb_compiler.run_journal import RunJournal`.
2. **The adapter owns translation, not graph mechanics.** The adapter prepares inputs and calls `apply_compile_result(...)` (the Obsidian-flavored v1 entry point) — or its normalized successor `apply_mutations(...)` once the contract refactor lands per §5 path (a). Adapters do NOT call producer-specific entry points (`apply_arxiv_payload`, `apply_youtube_payload`, etc. — explicitly the anti-pattern path (b) called out in §5). The adapter does not execute Cypher directly.
3. **The adapter normalizes field names.** Producer-specific fields (`success`, `compile_ok`, `transcribed`, …) are read by the adapter and translated to canonical eligibility values before reaching the core's replay driver.
4. **The adapter owns the namespace.** Per §3.5, the adapter prepends `entity_id_namespace` (when non-None) to every entity ID before calling `apply()`. Obsidian adapter is grandfathered to namespace=None.
5. **The adapter is small.** Expected size: ≤200 LOC per adapter (post-normalization helpers). If an adapter is growing large, it likely indicates the producer's contract is misaligned with the graph schema — fix the misalignment, not the adapter.
6. **The adapter's naming is honest.** `obsidian_runs.py`, `arxiv_runs.py` — not `runs.py` (which would imply universality the adapter doesn't have). Public entry points named honestly too: `sync_current_run`, `rebuild_from_obsidian_runs`.
7. **The adapter is the single bridge.** Both live sync (Stage 9) and replay (`graphdb-kdb rebuild`) route through the adapter. No producer code, anywhere, calls `graphdb_kdb.GraphDB` or `apply_compile_result` directly.
8. **The adapter routes by `event_type`.** `is_eligible`, `load_payload`, and
   `apply` read the journal's `event_type` (absent ⇒ `compile`). A `cleanup`
   event loads `retraction.json` and `apply` dispatches to `apply_cleanup`
   (`DETACH DELETE` of `Entity` by `retracted_slugs`). An unrecognized
   `event_type` is skipped with `SkipReason='unsupported_event_type'` — it
   must never fall through to the compile path. `RunDescriptor` is unchanged;
   the discriminator lives in the journal JSON, not the descriptor.

---

## 5. The core's responsibilities

What the GraphDB-KDB core does *not* expect the adapter to handle:

| Responsibility | Lives in core |
|---|---|
| Schema management (DDL, migrations) | `graphdb_kdb/schema.py`, `graphdb_kdb/graphdb.py` |
| Transaction boundaries (per-run atomicity) | `graphdb_kdb/graphdb.py` |
| The Cypher dialect for `apply_compile_result` mutations | `graphdb_kdb/ingestor.py` |
| Chronological replay driver (drop tables, iterate, report) | `graphdb_kdb/rebuilder.py` (post-#63.6) |
| Query API (neighbors, paths, provenance) | `graphdb_kdb/queries.py` |
| Analytics (PageRank, communities, structural-holes) | `graphdb_kdb/analytics.py` |
| Verifier (sync-check between graph and any external store) | `graphdb_kdb/verifier.py` |

**The contract between adapter and core — v1 (Obsidian-only)**:

The **Obsidian adapter** provides a `(mutation_payload, scan_payload, run_id)` tuple in a shape compatible with `apply_compile_result(...)`'s expectations. Today that shape is Obsidian-flavored (D32-tempered): top-level `compiled_sources` array; each element with `source_id`, `summary_slug`, `concept_slugs`, `article_slugs`, `pages`, `compile_meta`; etc. This is the **Obsidian-adapter-specific** call signature, not a universal one.

**The contract between adapter and core — when producer #2 arrives**:

The Obsidian-flavored shape will not generalize cleanly to arxiv-papers or YouTube-transcripts. Two reasonable paths:

- **(a) Contract refactor**: `apply_compile_result` is renamed to `apply_mutations` with a normalized shape (entities, edges, supports — flat lists, no producer-flavored grouping like `compiled_sources`). Adapters do more upfront translation. *Recommended path; preserves clean core surface.*
- **(b) Parallel entry points**: core grows `apply_arxiv_payload`, `apply_youtube_payload`, etc., each Obsidian-shaped-equivalent for its own producer. *Anti-pattern; scales poorly; core ends up knowing about every producer.*

Lean: **(a)** when producer #2 arrives. Until then, the Obsidian-flavored signature is documented as v1-only and not held up as the universal shape. See OQ-PC3.

---

## 6. Obsidian-KDB's compliance — reference implementation

Today's Obsidian-KDB compile pipeline complies with the contract as follows:

| Contract artifact | Obsidian implementation | Status |
|---|---|---|
| **Mutation payload** | `state/compile_result.json` (overwritten each run) | ✅ Emitted; archived by sidecar (post-#63.7) |
| **Scan/state payload** | `state/last_scan.json` (overwritten each run) | ✅ Emitted; archived by sidecar (post-#63.7) |
| **Run journal** | `state/runs/<run_id>.json` (one per run, append-only) | ✅ Schema v2.0; eligibility fields present |
| **Sidecar archive** | `state/runs/<run_id>/{compile_result,last_scan}.json` | ⚠️ Pending #63.7 (Stage 9 wiring writes them going forward) |
| **Adapter** | `graphdb_kdb/adapters/obsidian_runs.py` | ⚠️ Pending #63.6 (B-lite split) |
| **Apply path** | `graphdb_kdb.ingestor.apply_compile_result(...)` | ✅ Shipped #63.2 |
| **Stage 9 live-sync** (D-S0) | `kdb_compile.py` Stage 9 calls `graphdb_kdb.adapters.obsidian_runs.sync_current_run(cr, scan, run_id)` — the adapter is the single Obsidian→graph entry point | ⚠️ Pending #63.7 (the wiring uses the adapter, not direct core import) |

**The pre-#63 historical compliance gap** (documented in `docs/task-graphdb-kdb-blueprint.md` §13.1 Q3 outcome (d)): 10 historical run journals exist from 2026-04-19 through 2026-04-21, but their sidecar archives do not exist (sidecars are post-#63.7). Only the latest pre-#63 run is recoverable from the current overwritten `state/compile_result.json` baton; the other 9 runs' payloads are gone.

D39's full-history independence claim is **prospective from #63 forward**, not retroactive. This is a one-time legacy artifact; future producers writing sidecars from day one have no such gap.

---

## 7. Authoring a new producer adapter — checklist

For someone (today or future) building, say, an arxiv-papers compile pipeline that wants to feed GraphDB-KDB:

### 7.1 Producer-side work

- [ ] Choose a `source_type` discriminator value (e.g., `"arxiv"`). This goes into `Source.source_type` for every Source node the adapter creates.
- [ ] Choose a `source_id` convention (e.g., `arxiv:2024.12345v1`). Document it.
- [ ] Choose entity-id convention for non-page entities (e.g., `arxiv-concept:<slug>` if reusing the slug PK, or extend schema).
- [ ] Emit mutation payload (`compile_result.json` analog): per-source records of which entities + edges + supports were emitted.
- [ ] Emit scan/state payload (`last_scan.json` analog): per-source inventory + reconciliation ops if applicable.
- [ ] Emit run journal per run with `run_id`, `success`, `dry_run` fields.
- [ ] Archive sidecars per run.

### 7.2 Adapter-side work (lives in `graphdb_kdb/adapters/arxiv_runs.py`)

- [ ] Implement `discover_runs(journals_dir)` — read the arxiv pipeline's journals directory; yield chronologically.
- [ ] Implement `is_eligible(journal_path)` — read JSON; check `success && !dry_run && sidecar_exists`.
- [ ] Implement `load_payload(journal_path)` — load sidecar `(mutation_payload, scan_payload, run_id)`.
- [ ] Implement `apply(mutation_payload, scan_payload, run_id, conn)` — translate arxiv-flavored fields to the shape `apply_compile_result(...)` (or `apply_mutations` if the core has generalized) expects; call it.
- [ ] Document field-name mappings in the adapter's docstring.
- [ ] Tests: synthetic arxiv-flavored fixtures; assert resulting graph state matches expectation.

### 7.3 CLI-side work

- [ ] Register adapter in CLI: `graphdb-kdb rebuild --producer arxiv ...` selects this adapter.
- [ ] Document in CLI help.

### 7.4 Decision points the new producer forces

- [ ] If field values diverge enough from Obsidian's (e.g., `Entity.page_type` enum no longer applies), trigger schema evolution discussion (§5 of this doc).
- [ ] If the mutation payload shape is awkwardly Obsidian-flavored for arxiv's needs, trigger the contract-refactor discussion (`apply_compile_result` → `apply_mutations` generalization).
- [ ] If the verifier needs an arxiv-specific manifest analog to compare against, define what "verify" means for the arxiv producer.

---

## 8. Anti-patterns — what producers must NOT do

| Anti-pattern | Why bad | Mitigation |
|---|---|---|
| Producer calls `graphdb_kdb.GraphDB` directly to mutate the graph | Bypasses the adapter abstraction; couples producer to graph internals. | Producer emits artifacts; adapter consumes them; core mutates. Three-step pipeline. |
| Producer's run-journal `success` field is unreliably populated (sometimes true on failed runs) | D39 eligibility filter becomes unreliable; replay produces incorrect graph state. | Run-journal-writing must happen *only after* the rest of the pipeline confirms success — atomic last-write semantics. |
| Producer overwrites the per-run sidecar between runs | Replay loses historical payloads; D39 prospective-claim fails. | Sidecar is write-once per run; never modify after creation. |
| Producer's `run_id` formats are not chronologically sortable | Replay order is undefined; out-of-order replay produces wrong graph state. | Use ISO-8601 timestamps in filenames, or include explicit `started_at` field. |
| Adapter imports producer Python types | Inverts dependency direction; breaks extraction-readiness. | Adapter parses JSON; treats it as a documented contract. |
| Adapter emits Cypher directly instead of calling `apply_compile_result` (or its successor) | Bypasses core's transaction semantics; risks schema drift. | Adapters use the core's mutation API; do not author Cypher. |
| Adapter deletes or rewrites another producer's `source_type` data | The graph is co-tenant by design (multiple producers, single Kuzu directory). Adapter must operate within its own `source_type` namespace only. | Adapter writes only to records whose `Source.source_type` matches its declared `source_type`. Reads may span producers (Cypher does not restrict by namespace) but writes must not. |
| Skipping the entity-id namespace prefix without team consensus | Collision risk between producers' bare entity IDs (e.g., two producers using slug `concepts/foo` for unrelated concepts). | All new adapters declare `entity_id_namespace` per §3.5; Obsidian grandfathered. |

---

## 9. Open questions

| ID | Question | When to answer |
|---|---|---|
| **OQ-PC1** | Should the adapter interface be a formal Python `Protocol` / ABC, or duck-typed? Lean: duck-typed for v1 (one adapter); formalize at producer #2. | When producer #2 arrives |
| **OQ-PC2** | ~~Multi-producer co-tenancy slug collision?~~ **CLOSED by D-S1 (2026-05-14)**: Obsidian grandfathered as bare slug (implicit `obsidian:` namespace); all future producers use explicit `<source_type>:<entity_id>` prefix. See §3.5. | n/a |
| **OQ-PC3** | If producer #2's payload shape is significantly different (e.g., temporal mutations rather than compile_result-style snapshots), should the core grow `apply_mutations(...)` as a normalized entry point, or keep parallel `apply_compile_result(...)` / `apply_arxiv_payload(...)`? | Producer #2 design phase |
| **OQ-PC4** | Adapter discovery mechanism: how does the CLI know about installed adapters? Entry-points, registry, explicit list? | Stage 3 of extraction roadmap |
| **OQ-PC5** | What "verify" means for a producer without a manifest-equivalent: is the verifier still useful, or is `graphdb-kdb rebuild` + structural-equality the only audit path? | Per producer |
| **OQ-PC6** | Versioning of the producer contract itself: when this contract evolves (e.g., new required field on the journal), how do existing adapters get notified? Lean: contract version field; adapters declare what version they target. | Stage 4 of extraction roadmap |
| **OQ-PC7** | Cross-producer queries: should the query API surface a `WHERE source_type IN (...)` filter naturally, or expose per-source-type query helpers? | Producer #2 |

---

## 10. Relationship to other roadmap docs

- **`docs/graphdb-kdb-extraction-roadmap.md`**: defines GraphDB-KDB's path from monorepo to standalone package. The producer contract becomes load-bearing at **Stage 3 (producer #2 arrives)** of that roadmap; today (Stage 0/1) it's documenting intent.
- **`docs/manifest-succession-arc.md`**: defines manifest.json's evolution. The Obsidian producer's contract compliance becomes operationally critical at **stage M1** of that arc (when EXISTING CONTEXT switches to GraphDB).
- **`docs/task-graphdb-kdb-blueprint.md`**: defines the technical scaffolding of #63 (#63.1–#63.9). The producer contract abstracts what #63.6's adapter is doing for Obsidian-KDB into a generalizable shape.

---

## 11. References

- **D32 (tempered)**: storage-layer multi-source; ingestion API Obsidian-flavored — `docs/task-graphdb-kdb-blueprint.md` §2.
- **D34**: independence by shared upstream — same.
- **D38**: pipeline integration via Stage 9 (non-fatal) — same.
- **D39**: rebuild eligibility filter (`success=true AND dry_run=false AND payload_present`) — same + §8.2.
- **Codex brainstorm response** (2026-05-14): the "contract ownership" frame and the B-lite recommendation that surfaced the need for this document — captured in 2026-05-14 daily note.
- **Reference implementation files**:
  - `kdb_compiler/compiler.py` (writes `compile_result.json`)
  - `kdb_compiler/run_journal.py` (writes per-run journal; schema v2.0)
  - `kdb_compiler/scanner.py` (writes `last_scan.json`)
  - `graphdb_kdb/ingestor.py` (consumes the mutation payload via `apply_compile_result`)

---

## 12. What this document does NOT do

- Does not commit any specific producer to compliance.
- Does not define the second producer (arxiv-compile or otherwise) — it specifies what such a producer *would need* to comply.
- Does not specify the Cypher dialect or schema details — those live in the blueprint.
- Does not address downstream *consumers* (query callers, RAG integrations, kdb-graph utility) — they read the graph; they don't produce.

---

**One-line summary**: a producer emits four kinds of artifacts (mutation payload, scan/state payload, run journal, sidecar archive) in JSON shapes it documents; an adapter (living in `graphdb_kdb/adapters/`) reads those artifacts by documented field names — *not* by Python import — and calls the core's mutation API. The core never knows the producer exists.
