# Manifest Succession Arc

**Status:** Forward-looking architectural intent. Documents the transition of `manifest.json` from its current swiss-knife shape to a narrower, single-purpose successor — with the ontology responsibility relocated to GraphDB-KDB.

**Date:** 2026-05-14.

**Scope:** Captures the team's shared vision for *how* manifest.json evolves once GraphDB-KDB is operationally trusted. Companion to `docs/reference/graphdb-kdb-extraction-roadmap.md` and `docs/reference/graphdb-kdb-producer-contract.md`.

---

## 1. Why this document exists

`manifest.json` exists today as an *accident of expediency* — the prototype needed a place to dump multiple concerns and JSON was the path of least resistance. There is nothing principled about housing source metadata, pseudo-ontology, and system state in one file.

The reframe locked on 2026-05-10 (paradigm shift to "KDB is a knowledge-graph compiler"; see `docs/reference/New-GraphDB-Paradigm.md`) means manifest.json's ontology role is **transitional**, not durable. GraphDB-KDB is the long-run owner of pages, edges, and provenance. Manifest's legitimate residual responsibility is **source-file metadata**.

Without this document, future sessions could (a) assume the swiss-knife shape is permanent and pile on more concerns; (b) lose track of which manifest fields are migrating where; (c) leak GraphDB-side responsibilities back into manifest writes during refactors.

---

## 2. Today's manifest.json — the mixed-concern artifact

**File:** `~/Obsidian/KDB/state/manifest.json` (~80 KB on the canonical 62-page / 4-source corpus).

**Top-level structure** (verified 2026-05-14):

```
{
  "schema_version": "...",
  "kb_id":          "...",
  "created_at":     "...",
  "updated_at":     "...",
  "settings":       { ... 12 keys ... },
  "runs":           { "last_run_id", "last_successful_run_id" },
  "stats":          { "total_pages", "total_article_pages", ... 6 keys },
  "sources":        { "<source_id>": { meta }, ... 4 entries },
  "pages":          { "<page_path>": { meta + edges }, ... 62 entries },
  "orphans":        { ... 0 entries today },
  "tombstones":     { ... 0 entries today }
}
```

**Concern decomposition** (the swiss-knife problem made explicit):

| Field | Concern | Long-run owner | Migration disposition |
|---|---|---|---|
| `schema_version` | manifest's own format version | manifest | **Keep** |
| `kb_id` | knowledge base identity | manifest | **Keep** |
| `created_at`, `updated_at` | manifest lifecycle | manifest | **Keep** |
| `settings` | compile-pipeline configuration | manifest (or split out to its own config file) | **Keep for now**; revisit if it becomes a separate `settings.json` |
| `runs.last_run_id`, `runs.last_successful_run_id` | pointers to most-recent runs | manifest (operational state, not ontology) | **Keep** |
| `sources` | per-source-file metadata (path, hash, mtime, size, compile state) | manifest | **Keep — this is manifest's durable purpose** |
| `pages` | per-page ontology data (slug, title, type, outgoing_links, incoming_links_known, supporting_sources) | **GraphDB-KDB** | **Migrate out**: this is the ontology; lives natively as `Entity` nodes + `LINKS_TO` + `SUPPORTS` edges in the graph |
| `orphans` | orphan-candidate page slugs | **GraphDB-KDB** | **Migrate out**: ontology-derived (pages with zero `SUPPORTS` edges) |
| `tombstones` | move/delete history of pages | **Open design** (not GraphDB-KDB today) | **Deferred — see OQ-M7**: current graph schema models *source*-level move/delete state only (`Source.status='moved'`, `Source.moved_to`); page-level historical tombstones (per-page move trail, archival reasons) are not yet a graph primitive. Migration target unresolved until page-history representation is designed. |
| `stats` | aggregate counts (total_pages, total_article_pages, …) | **Derivable from GraphDB** | **Migrate out**: regenerable on demand; not authoritative |

**The "pseudo-ontology" subset** — `pages`, `orphans`, `tombstones`, and `stats` together constitute manifest's current ontology responsibility. All four migrate to GraphDB-KDB. What remains is the **source-meta core**: `schema_version`, `kb_id`, timestamps, `settings`, `runs.*` pointers, and `sources`.

**Size impact** (rough estimate on canonical corpus):

- Today: ~80 KB (62 pages × ~1.0 KB each ≈ 62 KB of pseudo-ontology; ~18 KB of legitimate source-meta).
- Post-succession: ~18–25 KB (source-meta only).

That ~75% size reduction is incidental but signals the right scope: manifest has been doing a job it was never well-shaped for.

---

## 3. End-state vision

**Manifest.json** becomes a focused **source-file metadata ledger**:

```
{
  "schema_version": "...",         // bumped to signal new shape
  "kb_id":          "...",
  "created_at":     "...",
  "updated_at":     "...",
  "settings":       { ... },        // (or split to settings.json)
  "runs":           { "last_run_id", "last_successful_run_id" },
  "sources":        { "<source_id>": { meta }, ... }
}
```

Specifically:

- **No `pages` key.** Page-level ontology is read from GraphDB-KDB via the `graphdb-kdb` CLI or Python API.
- **No `orphans` key.** `graphdb-kdb orphans` returns this on demand.
- **No `tombstones` key once page/source history representation is designed** — the eventual home is TBD (graph-resident is one option, but not yet committed; see OQ-M7). Until that design lands, `tombstones` either stays in manifest (transitional) or is dropped if no consumer reads it.
- **No `stats` key.** `graphdb-kdb stats` returns counts on demand.

**EXISTING CONTEXT seed-selection** (the top-50 known slugs + connections feed for next-compile) reads from **GraphDB-KDB**, not from a regex-over-manifest's-pages traversal. This is the *load-bearing operational change* that proves the graph is the system, not a sidecar.

**`context_loader.py` is rewired** to call `graphdb_kdb.GraphDB.neighbors()` / `graphdb_kdb.GraphDB.pagerank()` instead of parsing `manifest.json.pages` with regex.

---

## 4. Field-by-field migration plan

For each field migrating *out* of manifest, the target shape in GraphDB-KDB:

| Manifest field | GraphDB-KDB representation | Read path |
|---|---|---|
| `pages.<path>.slug` | `Entity.slug` (primary key) | `MATCH (e:Entity {slug: $slug}) RETURN e` |
| `pages.<path>.title` | `Entity.title` | same |
| `pages.<path>.page_type` | `Entity.page_type` *(or `entity_type` post-rename when generalized)* | same |
| `pages.<path>.status` | `Entity.status` | same |
| `pages.<path>.confidence` | `Entity.confidence` | same |
| `pages.<path>.outgoing_links` | `(e:Entity)-[:LINKS_TO]->(t:Entity)` — outgoing edges | `MATCH (e:Entity {slug:$slug})-[:LINKS_TO]->(t) RETURN t` |
| `pages.<path>.incoming_links_known` | `(src_e:Entity)-[:LINKS_TO]->(e:Entity)` — Cypher *answers this natively*, no materialization needed | `MATCH (src_e:Entity)-[:LINKS_TO]->(e:Entity {slug:$slug}) RETURN src_e` |
| `pages.<path>.supporting_sources` | `(src:Source)-[:SUPPORTS]->(e:Entity)` | `MATCH (src:Source)-[:SUPPORTS]->(e:Entity {slug:$slug}) RETURN src` |
| `orphans.<slug>` | `Entity` with `status='orphan_candidate'` | `MATCH (e:Entity {status:'orphan_candidate'}) RETURN e` |
| `tombstones.<page>` | **OPEN DESIGN** — current schema models *source* move/delete state (`Source.status='moved'`, `Source.moved_to`), NOT page-level historical tombstones. Page-level tombstone modeling (per-page move history, archival reasons, etc.) is not yet a graph primitive. | TBD; for now `tombstones.*` migration is **deferred** until the team designs page-history representation (see §8 OQ-M7) |
| `stats.total_pages` | `MATCH (e:Entity) RETURN count(e)` | `graphdb-kdb stats` |
| `stats.total_article_pages` | `MATCH (e:Entity {page_type:'article'}) RETURN count(e)` | filtered count |
| `stats.total_concept_pages` | `MATCH (e:Entity {page_type:'concept'}) RETURN count(e)` | filtered count |

**Key insight from the migration plan**: GraphDB-KDB already supports every read manifest does, and several of them more naturally. `incoming_links_known` in manifest is *materialized* (computed during each compile by walking everyone's outgoing_links — pure bookkeeping overhead); in GraphDB-KDB it's just `MATCH (s)-[:LINKS_TO]->(e)`. The succession isn't trading one denormalization for another — it's removing one.

---

## 5. Stages of transition

### Stage M0 — Dual-write, manifest-primary (target state once #63.7 lands)

- **Status as of 2026-05-14**: Stage 9 pipeline wiring (`graph_sync`) is **not yet shipped** — that's #63.7. Today (post-#63.5), `kdb-compile` writes manifest.json but does NOT yet sync to GraphDB on each run. M0 describes the **planned transitional state after #63.7 lands**, not the current state.
- **State (post-#63.7)**: every compile run writes both manifest.json AND GraphDB. Manifest.json's `pages`/`orphans`/`stats` are still populated and treated as authoritative by all readers (notably `context_loader.py`). Tombstones remain manifest-only (no graph counterpart per §4 open design).
- **Why this stage**: GraphDB is not yet operationally trusted. Stage 9 ingestion is non-fatal (D38), meaning the graph might be transiently out of sync. Manifest remains the reliable source of truth for ontology *during the trust-building period*.
- **Validation**: `graphdb-kdb verify` reports zero divergence against manifest after every compile run (proves the graph is keeping up, even though no consumer is reading from it yet).
- **Duration**: until `graphdb-kdb verify` has reported zero divergence across N consecutive compile runs (suggested N=5) AND across at least one MOVED/DELETED reconciliation event.

### Stage M1 — Dual-write, GraphDB-primary for EXISTING CONTEXT

- **Trigger**: M0 validation complete; `graphdb-kdb verify` has zero divergence track record.
- **State**: compile pipeline still writes both. `context_loader.py` is **rewired** to read EXISTING CONTEXT seed slugs from GraphDB-KDB. Manifest's `pages` dict is still populated but no longer authoritative for compile-time decisions.
- **Sub-task**: this is what was originally scoped as **Task C** (graph-native seed selection) in the pre-#63 era. Becomes a real sub-task in this stage.
- **Fallback behavior on GraphDB unavailability** (load-bearing, locked):
  - **Fail loud, do not silently fall back to manifest.**
  - Rationale: the *whole point* of M1 is to prove GraphDB is reliable enough to be on the critical path. A silent manifest fallback would mask regressions and defeat the trust-building purpose. By M3 fallback is impossible by design (manifest no longer carries pages).
  - Implementation: `context_loader.py` raises `GraphDBUnavailableError` (or equivalent) and `kdb-compile` exits with a clear message: "GraphDB at <path> is unavailable; run `graphdb-kdb rebuild` to reconstruct, or revert M1 by setting `KDB_CONTEXT_SOURCE=manifest`."
  - Optional escape hatch: `KDB_CONTEXT_SOURCE` env var allows manual revert to manifest-sourced context. *Operator-visible*, not silent.
- **Validation**:
  - **EXISTING CONTEXT comparison harness**: a dedicated `kdb-benchmark --context-source <manifest|graphdb>` mode that fires the same canonical corpus through the same model with both context sources side-by-side. Accept M1 only when GraphDB-sourced runs reach **parity or better** on the canonical quality measures (S0, M1–M5) within the same session (apples-to-apples per `feedback_apples_to_apples_within_session`). This is a deliberate harness, not a "monitor benchmark drift over time" gate.
  - `graphdb-kdb verify` still reports zero divergence after each compile run.
- **Operational note**: this is the **first stage where GraphDB-KDB is on the critical path** — a graph failure now breaks compile. Stage 9 ingestion remains non-fatal at the *write* path (per D38) — failures are journaled and `graphdb-kdb rebuild` is the recovery — but the *read* path during compile is critical-path.

### Stage M2 — Manifest's ontology fields deprecated (still written, marked stale)

- **Trigger**: M1 has run cleanly for N successful compiles; EXISTING CONTEXT from GraphDB is performing at least as well as the legacy path.
- **State**: manifest_update.py still writes `pages`/`orphans`/`tombstones`/`stats` but adds a **deprecation marker** (`_deprecated: true` on those sub-objects, or moves them under a `_legacy` parent key). Schema version of manifest bumps to signal the change.
- **Why this stage exists** (not jumping straight to M3): backward compatibility for any tool that *might* still be reading the legacy ontology fields. The marker gives one release cycle of warning before removal.
- **Validation**:
  - No internal code reads the deprecated fields.
  - Any external tooling has been notified or audited (in practice for this single-user project: just the person at the keyboard).

### Stage M3 — Manifest's ontology fields removed (write-side stops emitting them)

- **Trigger**: M2 has been stable for ≥1 month (or one major design iteration); no deprecation warnings tripped.
- **State**: `manifest_update.py` is refactored to emit only the source-meta core. `pages`, `orphans`, `tombstones`, `stats` are *gone* from new writes. Existing manifest.json files on disk get migrated on first read (one-time strip + rewrite) or by running a `kdb-compile --migrate-manifest` subcommand.
- **Manifest schema version bumps** to the next major version, declaring the new shape canonical.
- **Validation**:
  - manifest.json file size drops to ~25% of pre-succession size (the swiss-knife pseudo-ontology was that much of the file).
  - `kdb-compile` end-to-end still works without the deprecated fields.
  - `graphdb-kdb verify` no longer has anything in manifest to verify against for the migrated-out fields (verifier's L4 "overlap only" scope shrinks accordingly).

### Stage M4 — `manifest_update.py` becomes "source-meta-only" by code structure

- **Trigger**: M3 has been stable.
- **State**: the code module renames from `manifest_update.py` to something like `source_metadata.py`. The function `update_manifest_in_place(...)` becomes `update_source_metadata(...)`. Type hints + docstrings reflect the narrower scope. This is the *naming-catches-up-to-substance* stage.
- **Optional refinement**: `settings` may be split out to its own `settings.json` if the team decides that mixing settings with source-meta is a residual mini-swiss-knife.

---

## 6. Validation at each stage

| Stage | Quantitative check | Qualitative check |
|---|---|---|
| M0→M1 | `graphdb-kdb verify` returns zero divergence across N=5 successive runs incl. ≥1 MOVED or DELETED | Team consensus: trust the graph |
| M1→M2 | **EXISTING CONTEXT comparison harness**: fire canonical 5-source corpus through same model, same settings, side-by-side `--context-source=manifest` vs `--context-source=graphdb`. GraphDB-sourced runs must reach parity or better on S0, M1, M2, M3, M4, M5 — pinned in a `task_C_acceptance_2026-MM-DD.json` artifact (or equivalent) before stage advances. Apples-to-apples session per `feedback_apples_to_apples_within_session`. | At least one MOVED page case validated end-to-end via the comparison harness |
| M2→M3 | Zero internal callers of deprecated fields (grep audit) | One release cycle elapsed |
| M3→M4 | manifest.json on disk has new shape; old shape migrated cleanly | Naming refactor doesn't break any caller |

**Post-M3 verification path** (when manifest no longer carries `pages`/`orphans`/`stats`): `graphdb-kdb verify_against_manifest` becomes useless for the ontology dimension — manifest has nothing to compare against. Replacement audit path:

- **Replay-to-temp-DB structural equality**: `graphdb-kdb verify --mode replay` rebuilds a temporary Kuzu DB from `state/runs/*.json` into a scratch location, then compares the temp DB's graph state to the live GraphDB-KDB. If structurally equal, the live DB faithfully represents the run-history truth. If divergent, surface the diff.
- This is the durable audit path post-succession. `verify_against_manifest` is retained for the source-meta dimension only (Source nodes vs manifest's `sources` dict).

---

## 7. Anti-patterns — what must NOT happen

| Anti-pattern | Why bad | Mitigation |
|---|---|---|
| Adding new ontology-flavored fields to manifest "for convenience" during the transition | Re-bloats the swiss-knife; counter to the succession direction. | Any new ontology need goes to GraphDB-KDB; if expressible as Cypher, it lives there. |
| Making manifest the source of truth for any field that exists in both places | Two sources of truth → divergence; verifier becomes load-bearing for correctness not just audit. | One field, one owner. `graphdb-kdb verify` is for *checking* sync, not for *enforcing* it via one-way correction. |
| Skipping Stage M1 (read-from-graph) and going straight to manifest-strip | Removes the safety net before the alternative is proven; high risk of compile-quality regression. | Walk the stages. The middle stages exist *because* trust-building is needed. |
| Leaving `incoming_links_known` materialization in `manifest_update.py` because "it might still be useful" | Costly bookkeeping (every compile walks N pages × M links) for no reader. | Remove at M3 alongside `pages` dict removal. |
| Treating `settings` migration as part of this arc | Different concern; conflates source-meta with config. | If `settings` warrants its own file, that's a separate task (`settings.json` split). |
| Forgetting that `kdb_compile.py` writes `compile_result.json` independently of manifest | Conflating manifest with compile output; their lifecycles are different. | This arc is about manifest specifically. `compile_result.json` is per-run truth; manifest is durable source-meta. |

---

## 8. Open questions

| ID | Question | When to answer |
|---|---|---|
| **OQ-M1** | Should `settings` move out of manifest to its own file? Or stay? | M3 or later; cosmetic |
| **OQ-M2** | Should `runs.last_run_id` / `last_successful_run_id` migrate to GraphDB (as graph metadata) or stay in manifest? Lean: stay in manifest (operational state, not ontology). | M2 |
| **OQ-M3** | Migration mechanism for existing manifest.json files: rewrite on first read, or explicit `kdb-compile --migrate-manifest` command? | M2→M3 transition |
| **OQ-M4** | After M4, does `manifest.json` keep its current filename or rename to `source_metadata.json` to match the new scope? | M4 |
| **OQ-M5** | Should the verifier's L4 ("overlap only") scope be adjusted at each stage as fields migrate out? Or is the current "skip non-overlap fields" rule self-adapting? | Each stage |
| **OQ-M6** | EXISTING CONTEXT design (the Task C originally) — what's the actual seed selection algorithm? Top-N by PageRank? By community membership? By prior-compile reference? This is a *separate* design decision but is the operational milestone of M1. | M1 design phase |
| **OQ-M7** | Page-level tombstone modeling in the graph — how should per-page move history, archival reasons, and historical title-changes be represented? Today the schema models source-level moves/deletes only (`Source.status='moved'`, `Source.moved_to`). | Whenever the team has a real need for page-history queries (e.g., "when was page X retitled?", "what's the audit trail for archived page Y?") |

---

## 9. Relationship to other roadmap docs

- **`docs/reference/graphdb-kdb-extraction-roadmap.md`**: defines GraphDB-KDB's path from monorepo to standalone package. Manifest-succession arc is independent of extraction — it happens at the *Obsidian-KDB side* whether or not the package is extracted. Both arcs can proceed in parallel.
- **`docs/reference/graphdb-kdb-producer-contract.md`**: defines what GraphDB-KDB expects from any producer's emitted artifacts. Once M2/M3 is complete and EXISTING CONTEXT reads from the graph, the Obsidian adapter's compliance with the producer contract is operationally critical (compile quality depends on graph health).
- **`docs/reference/task-graphdb-kdb-blueprint.md`**: defines #63's implementation. D32-tempered, D34, D38, D39 all anchor the technical scaffolding that *enables* this arc. The arc itself is post-#63.

---

## 10. References

- **Paradigm doc**: `docs/reference/New-GraphDB-Paradigm.md` (2026-05-10 conversational record of the reframe).
- **Blueprint**: `docs/reference/task-graphdb-kdb-blueprint.md` D32, D34, D38, D39.
- **Memory**: `project_graphdb_kdb_refoundation`.
- **Originally-scoped Task C**: closed/superseded by Task #63; the EXISTING CONTEXT design lives in M1 of this arc.
- **Verifier**: `graphdb_kdb/verifier.py` and L4 ("overlap only") rationale captured in 2026-05-14 daily note.

---

## 11. What this document does NOT do

- Does not commit to a timeline for M1–M4.
- Does not authorize any code change to `manifest_update.py` or `context_loader.py`.
- Does not define the EXISTING CONTEXT seed-selection algorithm (that's M1's design work).
- Does not address `manifest.json`'s relationship to OneDrive sync (operational concern, not architectural).
