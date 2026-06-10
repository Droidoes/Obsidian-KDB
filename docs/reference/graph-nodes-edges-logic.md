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
