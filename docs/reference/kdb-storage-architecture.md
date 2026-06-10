# KDB Storage Architecture — The Three Coordinated Stores

Higher-level companion to [`graph-nodes-edges-logic.md`](graph-nodes-edges-logic.md)
(which covers node/edge *mechanics*). This doc records the **storage + query
mental model**: how KDB stores knowledge and how it will be searched.

Status: mental model **reconfirmed 2026-06-09**. Store (1) is built; (2) exists;
(3) is future, gated on a named consumer (see *The Gate* below).

---

## The model: polyglot persistence, sized for embedded / single-user

KDB is **not** one store. It is **three coordinated stores, each a derived
projection of the same compile output**, each answering a different *query shape*.
One source of truth (the compile result + rendered pages); everything else is a
projection that can be rebuilt from it.

| # | Store | Engine | Holds | Answers (query shape) | State |
|---|-------|--------|-------|-----------------------|-------|
| 1 | **GraphDB** | Kuzu (embedded) | Topology + metadata: Entity/Source/Domain nodes, LINKS_TO/SUPPORTS/BELONGS_TO/ALIAS_OF edges, lightweight properties (keys, titles, types, status, short summaries) | **Relational / structural** — neighborhoods, paths, hubs, provenance chains, "what connects to what" | Built |
| 2 | **Content store** | Filesystem + JSON | Canonical bodies. `KDB/wiki/*.md` = per-page Markdown (sharded, slug-addressable, O(1) point lookup). `compile_result.json` = combined run artifact (replay / audit / benchmark) | **Point lookup** ("body of slug X" → wiki file) + **replay/audit** (monolith) | Built |
| 3 | **FTS index** | SQLite FTS5 (candidate) | Full-text index over bodies, built *from* store 2 | **Lexical** ("pages containing 'cron'") | Future — gated |

> **Why three, not one:** each query shape has a store tuned for it. Forcing all
> three onto one engine means one of them is always badly served — bodies bloat a
> graph engine tuned for traversal; relationships are painful in a flat file;
> full-text search is hopeless in either.

---

## Why each engine

- **GraphDB = Kuzu (embedded).** KDB is a *local, single-user, embedded* workload
  built from an on-disk vault. Kuzu is "the SQLite of graph DBs": in-process, no
  daemon, single directory, Cypher-compatible, columnar with fast multi-hop joins.
  - *Rejected:* **Neptune** (managed AWS cloud service — wrong by construction for a
    local tool); **Neo4j** (server/daemon, JVM — overweight for single-user infrequent
    local jobs; earns its weight only at large concurrent production scale).
  - *Flip condition:* if KDB ever became a **hosted multi-user service** (concurrent
    writers, HA), revisit Neo4j / a managed graph service. Not the project today.
  - *Accepted cost:* Kuzu is younger — API churn, smaller ecosystem, fewer turnkey
    graph-algorithm libraries than Neo4j's GDS.

- **Content store = filesystem + JSON, NOT a database (for now).** The wiki/ tree is
  *already* a sharded, slug-addressable content store — point lookups never need the
  monolith. `compile_result.json` is the *combined run artifact* (replay/audit/
  benchmark want one file), not the serving store. A monolithic JSON would scale
  badly *as a serving store* (whole-file parse/rewrite, no index, must fit in memory)
  — but it is not used that way, so the concern is moot at realistic single-user
  scale (low thousands of notes ≈ ~tens of MB).

- **FTS = SQLite FTS5 (candidate), added only when a real query needs it.** A derived
  index *built from* the canonical content, never replacing it. SQLite pairs naturally
  with Kuzu: both embedded, single-file, zero-server. Do **not** migrate the content
  store into a DB pre-emptively — add the index when a lexical query demands it.

---

## How it gets searched: the MCP server is the interface

The graph earns its keep **only on relational queries.** If the only need is lexical
("find the word X"), FTS alone suffices and the graph adds nothing. The graph's unique
value is **traversal and structure** — and the application that justifies the whole
investment is **GraphRAG-style retrieval**:

> A question arrives → find entry-point entities (FTS / slug match) → **traverse the
> graph** to assemble a *connected context neighborhood* (entity + linked concepts +
> supporting sources + domain) → hand that structured sub-graph to an LLM. FTS returns
> a pile of matching documents; the graph returns a *connected sub-graph of related
> knowledge.* That is the difference between a document base and a **knowledge** base.

The **interface** is an **MCP server** exposing a small tool set an LLM agent (e.g.
Claude) can call: `graph_neighborhood(slug)`, `find_path(a, b)`, `fts_search(text)`,
`get_body(slug)`. Then Claude *is* the query engine — it calls the tools, assembles
context, answers. This is how "search my KDB efficiently" actually happens.

Build sequence:
- **(a)** GraphDB + content store — *in progress now*
- **(b)** query interface (MCP server; + FTS index when needed)
- **(c)** real-world use cases — user-defined

---

## The Gate — name one concrete question before building (b)/(c)

Apply the **consumer-purpose test** to the *entire* GraphDB, not just to fields:
name the question, the answer it produces, and what breaks if it's absent. Without a
concrete consumer we risk elegant infrastructure with no load-bearing user.

**Next-session task:** name **one concrete real-world question** you wish you could
ask your vault today (e.g. *"What have I captured about X, and what does it connect
to?"*). Use it as the North Star to validate the full stack end-to-end:
`query → graph traversal → assembled context → answer`. One real question served well
proves the architecture; the rest is expansion.

A JOURNEY.md entry for this decision arc is **deferred** until that question is named
and the arc closes (per JOURNEY's iteration-boundary maintenance rule).
