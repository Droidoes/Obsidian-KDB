## 1. The app, in one sentence

**"Stress-test the thinnest bridges between clusters in my thinking: where do my topic islands connect through a single wikilink — and is that bridge grounded in more than one reading?"**

## 2. Why search can't do it

Lexical search and `grep` find co-occurrence inside documents; they cannot see the **global topology** of how *you* have wired ideas together. This query requires (a) partitioning your entire `LINKS_TO` graph into latent topic communities (Louvain modularity — a global optimization over edge structure), (b) ranking **inter-community** edge pairs by sparsity (`structural_holes` — counting cross-cluster bridges, not local neighbors), and (c) auditing each bridge entity's **provenance cardinality** via `SUPPORTS` (Source→Entity). A concept that appears in two books is not the same as being the *sole topological bridge* between two Louvain communities with exactly one `LINKS_TO` edge and one supporting Source. No text index reveals modularity, bridge sparsity, or the mismatch between link-centrality and documentary grounding.

## 3. The mechanism

**Traversal (exact schema + analytics):**

1. `analytics.communities(conn)` — Louvain partition over undirected `LINKS_TO` projection; every active `Entity.slug` → `community_id`.
2. `analytics.structural_holes(conn)` — `[(comm_a, comm_b, n_bridges), ...]` sorted ascending by `n_bridges` (sparsest existing bridges first).
3. For each candidate pair: enumerate **bridge entities** — `Entity` nodes with at least one `LINKS_TO` edge whose endpoints fall in different communities (new MCP composition, ~3 lines of Cypher over the membership map).
4. Per bridge entity: `sources_for_entity(slug)` → `SUPPORTS` count + Source metadata (`domain`, `author`, `summary`); `pagerank(conn)` score for load-bearing rank; `graph_neighborhood(slug, depth=1, direction="both")` for what each island loses if the bridge fails.
5. Label communities via dominant `BELONGS_TO`→`Domain.name` or majority `Source.domain` of entities in each cluster (derived, not retrieved).
6. `get_body(slug)` on top 1–2 bridge entities + one high-PageRank neighbor per side; agent **generates** unstated integration questions ("What would have to be true for A and B to be the same mechanism?" / "What reading would add a second SUPPORTS edge here?").

**MCP tools composed:** day-one `graph_neighborhood`, `sources_for_entity`, `get_entity`, `get_body` + **one new composite tool** `knowledge_bridges(top_k=5, max_supports=1)` wrapping `communities` + `structural_holes` + bridge-entity enumeration + SUPPORTS audit (exposes analytics already in `GraphDB.structural_holes()` but not in the six thin adapters).

## 4. Horizon

**1.0-now.** All load-bearing machinery exists today: `Entity` + `LINKS_TO` + `SUPPORTS` + `BELONGS_TO` + `Source.domain` + `pagerank` / `communities` / `structural_holes` in `kdb_graph/analytics.py`. No Claim layer required. (2.0 upgrade path: annotate bridges whose endpoint entities have active `CONTRADICTS`/`QUALIFIES` chains — tension-aware bridges — but the killer insight ships on 1.0.)

## 5. Why it's the highest-value one

It converts the graph from a lookup index into a **mirror of your epistemic architecture**: which parts of your worldview are siloed, where you've *drawn* a connection in wikilinks that your reading record doesn't yet support, and what thought-work would actually strengthen the joint. A user reaches for this repeatedly — after every major ingest burst, before writing a synthesis piece, when two interests "feel related" but notes stay separate — because the answer changes as `LINKS_TO` and `SUPPORTS` evolve. It is metacognitive (reveals fragility in *your* structure, not facts in the world) and generative (produces integration questions and reading targets, not a list of pages). It decisively beats "what connects to X?" because it finds connections **you didn't query for**, ranks them by topological danger, and tells you whether they're documentary or aspirational.

## 6. Runner-up (one line)

**Single-source load-bearing hubs** — entities in the top decile of `pagerank` with `SUPPORTS` degree ≤ 1 and high `LINKS_TO` indegree: "ideas I've built a lot on but only read once" (1.0-now, simpler, less generative across domains).