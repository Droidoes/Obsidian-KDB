# Graph Nodes & Edges — Logic Reference

Canonical reference for what becomes a node vs. an edge in GraphDB-KDB, who creates it, and from what source.

---

## Node Types

| Node | `page_type` | Origin | Created by | From |
|------|-------------|--------|------------|------|
| `Entity:summary` | `summary` | Pass-2 `pages[]` | Ingestor (code) | One per source — the top-level distillation |
| `Entity:concept` | `concept` | Pass-2 `pages[]` | Ingestor (code) | Individual ideas/concepts extracted by LLM |
| `Entity:article` | `article` | Pass-2 `pages[]` | Ingestor (code) | Synthesized long-form pieces referencing concepts |
| `Source` | — | File metadata | Ingestor (code) | Source file path, hash, domain, author |
| `Domain` | — | Pass-1 `domain` field | Ingestor (code) | LLM-classified domain per source |

> **Key distinction:** Entity nodes are LLM-extracted content (the LLM decides what entities exist and writes their body). Source and Domain nodes are code-created from metadata.

---

## Connection Matrix

Node-to-node edge summary. Read row (FROM) → column (TO).

| FROM ↓ \ TO → | Source | Domain | Entity:summary | Entity:concept | Entity:article |
|---|---|---|---|---|---|
| **Source** | — | — | `SUPPORTS` | `SUPPORTS` | `SUPPORTS` |
| **Domain** | — | — | — | — | — |
| **Entity:summary** | — | `BELONGS_TO` | — | `LINKS_TO` | `LINKS_TO` |
| **Entity:concept** | — | `BELONGS_TO` | — | `LINKS_TO` | `LINKS_TO`† |
| **Entity:article** | — | `BELONGS_TO` | `LINKS_TO`† | `LINKS_TO` | `LINKS_TO`† |

> † Allowed by schema; rarely observed in practice — LLM rarely links concept→article or article→summary/article.
>
> Source never receives incoming edges. Domain never has outgoing edges.
>
> `ALIAS_OF` (alias Entity → canonical Entity) is a structural identity edge, not a content link — not shown here. Alias entities don't participate in `LINKS_TO` or `SUPPORTS`.

---

## Edge Types

| Edge | Direction | Origin | Created by | Logic |
|------|-----------|--------|------------|-------|
| `LINKS_TO` | Entity → Entity | Pass-2 `pages[].body` wikilinks | Ingestor (code) | LLM writes `[[slug]]` in body text; code materializes each wikilink as an edge |
| `SUPPORTS` | Source → Entity | Pass-2 compile result | Ingestor (code) | Every entity in a source's `pages[]` gets a SUPPORTS edge from that source |
| `BELONGS_TO` | Entity → Domain | Derived | Ingestor (code) | Deterministic: Entity BELONGS_TO Domain D if any Source with domain=D SUPPORTS it (D1-A) |
| `ALIAS_OF` | alias Entity → canonical Entity | `aliases.json` ledger | Canonicalization stage (#74) | Code reads aliases ledger; alias slug → canonical slug |

> **Key distinction:** `LINKS_TO` edges are LLM-decided — the LLM chooses which entities reference which others through the wikilinks it writes. All other edges are deterministic code derivations from the compile output.

---

## Node Properties — Stored vs. Externalized

The graph is a **topology + metadata projection**, not the content store of record. It holds *what exists and how it connects* — not the prose. The full body text lives in two canonical homes:

- `KDB/wiki/{summaries,concepts,articles}/*.md` — rendered Markdown (human-readable)
- `KDB/state/compile_result.json` — full page-level output: `body`, `outgoing_links`, `title`, `page_type`, `confidence` (machine-readable)

The graph references that content by `slug` (the foreign key back to it).

### What each node stores

| Node | Key | Stored properties | From |
|------|-----|-------------------|------|
| `Entity` | `slug` | `title`, `page_type`, `status`, `confidence`, `canonical_id`, `created_at`, `updated_at`, `first_run_id`, `last_run_id` | Pass-2 `pages[]` |
| `Source` | `source_id` | `canonical_path`, `hash`, `size_bytes`, `file_type`, `source_type`, `status`, `summary`, `author`, `domain`, `last_seen_at`, `ingest_state`, run-tracking fields | File scan + Pass-1 `source_meta` |
| `Domain` | `name` | `created_at`, `first_run_id` | Derived from `Source.domain` |

### What is deliberately NOT stored on a node

| Excluded | Where it lives instead |
|----------|------------------------|
| `body` (full page text) | `KDB/wiki/` + `compile_result.json` — reached by `slug` |
| `outgoing_links` | Materialized as `LINKS_TO` edges, not a node property |
| `log_entries`, `warnings` | Compile-time diagnostics — not persisted to the graph |

> **The principle is a gradient, not a binary.** It is not "no text on nodes" — it is **titles and short summaries in, full bodies out**. The graph stores what *traversal and cheap display/filtering* need (keys, titles, types, status, and short summaries like `Source.summary`); it externalizes what only *content consumption* needs (full bodies). `Source.summary` is a deliberate denormalization on exactly this line.

> **Why externalize bodies:** (1) graph engines are tuned for pointer-chasing across relationships, not blob storage — fat body properties bloat node records and hurt traversal cache locality; (2) single source of truth — the body has one canonical home (wiki/compile_result), so no copy can drift; (3) full-text search belongs in an FTS engine or `ripgrep` over the wiki, not a graph traversal.

> **The tradeoff:** a consumer needing body-at-the-node (e.g. a future GraphDB MCP recall server, or graph-aware retrieval) must do a *second lookup* — the graph hands back slugs, then it reads `compile_result.json`/wiki for bodies. At KDB's scale (single user, low thousands of nodes) that join is free. If it ever becomes latency-critical, the answer is to **denormalize a short summary onto the node** (as `Source.summary` already does) or pair the graph with a content store keyed by slug — **never** put the full body in the graph.

---

## 2.0 Claim Layer (TBD — design pending)

| Node/Edge | Direction | Origin | Created by | Logic |
|-----------|-----------|--------|------------|-------|
| `Claim` | — | Pass-2 body text | TBD | Discrete proposition extracted by LLM from source body |
| `ABOUT` | Claim → Entity | TBD | TBD | LLM identifies which entity the claim asserts about |
| `EVIDENCED_BY` | Claim → Source | TBD | Code | Deterministic: claim appeared in this source |
| `CONTRADICTS` | Claim ↔ Claim | TBD | TBD | Two claims on same entity that conflict — detection mechanism TBD |

---

## Design Rules

- **LLM decides:** which entities exist, what their body says, which entities link to which (LINKS_TO)
- **Code decides:** all provenance edges (SUPPORTS, BELONGS_TO, ALIAS_OF) — fully deterministic from compile output
- **No pre-declared edges / hints in prompts** — the LLM organically surfaces connections (D-NW4-5)
- **Post-LLM deterministic override** — provenance/path/config decisions happen in code, never in the prompt
- **Graph stores topology, not content** — node properties are keys + metadata + short summaries; full bodies stay externalized in `wiki/` + `compile_result.json`, reached by `slug` (see *Node Properties* above)
