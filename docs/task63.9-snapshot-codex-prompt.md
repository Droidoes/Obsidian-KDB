# Codex Review: GraphDB-KDB Snapshot/Export (#63.9)

You are reviewing the proposed design for the last open sub-task of an
8-week graph-database refoundation effort. Project context first; then
the design proposal; then the questions we want your independent read on.

## 1. Project context

**GraphDB-KDB** is a Kuzu-embedded knowledge graph for a personal
Obsidian vault. It's the "ontology layer" of a raw-text → wiki compiler.
The producer (`kdb-compile`, a Python tool) reads `~/Obsidian/KDB/raw/*.md`
sources, LLM-extracts entities/links/supports, and writes a per-run
journal at `~/Obsidian/KDB/state/runs/<run_id>.json` plus a per-run
sidecar at `state/runs/<run_id>/{compile_result,last_scan}.json`.

A Stage 9 (graph_sync) on the producer side calls into a thin Obsidian
adapter that mutates the GraphDB-KDB Kuzu graph. The graph lives at
`~/Droidoes/GraphDB-KDB/` — sibling to the producer project, NOT
OneDrive-synced (Kuzu's binary files are mutating and OneDrive corrupts
them).

The schema (locked, in Kuzu Cypher DDL):

```cypher
CREATE NODE TABLE Entity (
    slug STRING PRIMARY KEY,
    title STRING,
    page_type STRING,      -- summary | concept | article
    status STRING,
    confidence STRING,
    created_at STRING,
    updated_at STRING,
    first_run_id STRING,
    last_run_id STRING
);

CREATE NODE TABLE Source (
    source_id STRING PRIMARY KEY,
    source_type STRING,
    canonical_path STRING,
    status STRING,
    file_type STRING,
    hash STRING,
    size_bytes INT64,
    first_seen_at STRING,
    last_seen_at STRING,
    last_ingested_at STRING,
    ingest_state STRING,
    ingest_count INT64,
    last_run_id STRING,
    moved_to STRING
);

CREATE REL TABLE LINKS_TO ( FROM Entity TO Entity, run_id STRING, created_at STRING );
CREATE REL TABLE SUPPORTS ( FROM Source TO Entity, role STRING, hash_at_time STRING, run_id STRING, created_at STRING );
```

Plus a small `_SchemaMeta` row carrying SCHEMA_VERSION.

## 2. Recovery story (what we already have)

- **Primary recovery: `graphdb-kdb rebuild`.** Drops all tables, replays
  every eligible per-run sidecar chronologically via the producer
  adapter. Eligibility = `success=true AND dry_run=false AND
  payload_present`. This means: lose the Kuzu directory entirely →
  rebuild → same graph (modulo the 9 pre-#63 historical runs whose
  payloads were overwritten before the sidecar discipline existed; we
  one-shot baton-backfilled the latest pre-#63 run; the other 8 are
  unrecoverable historical loss).

- **Belt-and-suspenders backup (what #63.9 is for):** A `snapshot`
  subcommand that exports the current graph state as plain-text JSONL
  files into the OneDrive-synced vault (`~/Obsidian/KDB/state/
  graph-snapshots/<ts>/`). Diffable, human-readable, OneDrive-safe
  (text files, not binary).

- **The 3-tier recovery story when snapshot lands:**
  1. Kuzu dir corrupted: `graphdb-kdb rebuild` from journals.
  2. Journals AND Kuzu dir lost: future `graphdb-kdb load-snapshot`
     from the most recent snapshot (NOT in #63.9 scope; v1 is
     write-only).
  3. All three lost: re-run `kdb-compile` on the live vault (sources
     are the canonical truth).

## 3. The producer-independence invariant (D34)

`graphdb_kdb/` has ZERO imports from `kdb_compiler/`. Producer-specific
knowledge lives in `graphdb_kdb/adapters/obsidian_runs.py` and is
expressed as JSON parsing of producer artifacts — never as Python
imports of producer types. This is enforced by a grep invariant. Any
new code we add for snapshot must respect this.

## 4. Proposed snapshot design

**CLI:**
```
graphdb-kdb snapshot --vault-root <root>   # default out: <root>/KDB/state/graph-snapshots/<ts>/
graphdb-kdb snapshot --out <dir>           # explicit override
graphdb-kdb snapshot --json                # machine-readable summary
```

`<ts>` format: `YYYY-MM-DDTHH-MM-SS_<TZ>` (local time with TZ abbreviation,
matching the producer's run_id format — `feedback_local_time_everywhere`).

**Files written into the snapshot dir:**

| File | Content | Row schema |
|---|---|---|
| `entities.jsonl` | all Entity rows | `{slug, title, page_type, status, confidence, created_at, updated_at, first_run_id, last_run_id}` |
| `sources.jsonl` | all Source rows | `{source_id, source_type, canonical_path, status, file_type, hash, size_bytes, first_seen_at, last_seen_at, last_ingested_at, ingest_state, ingest_count, last_run_id, moved_to}` |
| `links_to.jsonl` | all LINKS_TO rels | `{from_slug, to_slug, run_id, created_at}` |
| `supports.jsonl` | all SUPPORTS rels | `{source_id, entity_slug, role, hash_at_time, run_id, created_at}` |
| `manifest.json` | snapshot metadata | `{schema_version, emitted_at, graph_dir, counts: {entities, sources, links_to, supports}, snapshot_format_version}` |

**Stable ordering** within each file: entities ORDER BY slug; sources
ORDER BY source_id; LINKS_TO ORDER BY (from_slug, to_slug, run_id);
SUPPORTS ORDER BY (source_id, entity_slug, run_id). Stable order =
diffable snapshots.

**Stable key ordering** within each JSON line: keys lexically sorted
(`json.dumps(..., sort_keys=True)`). Diffable byte-level.

**Atomicity:** write to a temp subdir `<ts>.tmp/`, then `os.rename` to
`<ts>/` on success. Same pattern as the producer's `atomic_io`.

**Module placement:** new file `graphdb_kdb/snapshot.py`. Public
function:
```python
def snapshot(graph_dir: Path, out_dir: Path) -> SnapshotResult:
    """Export the current Kuzu graph state to JSONL+manifest files
    in out_dir. Atomic: writes to <out_dir>.tmp/ first."""
```

Returns a `SnapshotResult` dataclass: `(out_dir, counts, emitted_at,
schema_version)`.

**Producer-independence (D34):** `snapshot.py` reads ONLY from the Kuzu
graph via the existing `graphdb_kdb.GraphDB` connection. No imports
from `kdb_compiler/`, no reading of producer journals, no use of the
ObsidianRunsAdapter. The snapshot represents *graph state*, not
producer state.

## 5. The one open design question

Edges layout — should LINKS_TO and SUPPORTS go in separate files (our
lean) or one merged `edges.jsonl` with a `type` discriminator (the
blueprint's literal wording)?

Our lean is split (4 files: entities/sources/links_to/supports +
manifest). Reasoning:
- Different rel-table schemas (LINKS_TO has just run_id/created_at;
  SUPPORTS has role + hash_at_time on top)
- Uniform per-file row schema matches entities.jsonl/sources.jsonl
  pattern
- Independent diff windows when only one edge type changes
- Cost: one extra file

Counter-argument for merged: blueprint says "edges.jsonl" literally;
fewer files; a single `for line in edges_jsonl: ...` reader pattern.

## 6. What we want from your review

Honest answers — go against our leans if you see issues we haven't.
Specifically:

1. **Edges layout (the open question above):** split or merged? Or a
   third option we're missing?

2. **Module placement and dependencies.** Should `snapshot.py` use the
   public `GraphDB` API (`gdb.cypher(...)`) or talk to `kuzu.Connection`
   directly? Both compile-time-OK; we have precedent for both inside
   `graphdb_kdb/` (e.g., `queries.py` operates on raw connections;
   `analytics.py` uses the public class). Which is more idiomatic for
   a bulk-export use case?

3. **Should the snapshot include the Cypher schema DDL** as a
   `schema.cypher` file alongside `manifest.json`? Two views:
   - YES: self-describing artifact; readable in isolation; lets a
     future `load-snapshot` round-trip even if schema_version drifted.
   - NO: SCHEMA_VERSION + the manifest already pin the producer
     version; the actual DDL lives in `graphdb_kdb/schema.py` in git.

4. **Snapshot identity / pointer file.** Should there be a
   `<vault_root>/KDB/state/graph-snapshots/latest.json` sidecar (or
   symlink) pointing at the most recent snapshot? Or is `ls -t` good
   enough? Concern: cross-platform symlink behavior on Windows/OneDrive.

5. **Atomicity strategy.** We're using
   "write `<ts>.tmp/`, then `os.rename` to `<ts>/`." On Windows-side
   OneDrive this MIGHT have edge cases. Is there a better pattern?

6. **What's missing.** Any class of snapshot consumer / future use case
   we should accommodate now (cheap to add early; expensive to
   retrofit)? Examples we considered: parallel snapshot/load round-trip
   tests, schema migration replay tools, audit/forensic tools, external
   indexers.

7. **Anything load-bearing later** that we'd want now while the design
   is open. (We've kept v1 strictly write-only; load-snapshot is
   deferred. Is that the right scope cut?)

Keep your review concrete — quote our proposed shape and either ratify
or replace with specifics. Brief is fine; we'd rather have 5 sharp
points than 15 hedged ones.
