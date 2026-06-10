## 1. The app, in one sentence
**Bisociative Synthesis:** Scan the global modularity of my knowledge base to locate isolated clusters of thought connected by a single thread, and generate synthesis notes that bridge those conceptual divides.

## 2. Why search can't do it
Full-text search and vector retrieval are locally-focused operations; they excel at matching keywords or semantic similarity within documents but have no concept of global topology. They cannot calculate network partition boundaries (Louvain modularity communities) or identify structural bottlenecks (edges that connect distinct communities). Search can find *what is similar*, but it cannot detect *what is disconnected yet adjacent* or identify the single bridge node that, if synthesized further, integrates thousands of words of previously siloed reading.

## 3. The mechanism
- **Nodes/Edges/Analytics:**
  - `Entity` nodes, grouped into communities using Louvain community detection (`analytics.communities(conn)`).
  - `LINKS_TO` edges, analyzed to identify inter-community edges.
  - The `analytics.structural_holes(conn)` function to return pairs of communities sorted by the number of bridges between them (focusing on sparse bridges: `n_bridges = 1` or `2`).
  - `pagerank(conn)` to rank the relative centrality of entities within each community.
- **MCP Tools Composed:**
  - Day-one tools: `get_entity(slug)` to read metadata of bridging entities, and `get_body(slug)` to read the full body content from the wiki content store.
  - Two new MCP tools implied by this mechanism:
    1. `get_communities()` → Returns `dict[slug, community_id]` mapped via Louvain.
    2. `get_structural_holes()` → Returns `list[tuple[comm_a, comm_b, n_bridges]]` sorted by sparsity.
- **Agent Workflow:**
  1. The agent calls `get_structural_holes()` and identifies the sparsest bridge (e.g., `comm_A` and `comm_B` linked by a single `LINKS_TO` edge between `entity_x` and `entity_y`).
  2. The agent queries `get_communities()` to pull the top-3 PageRank entities for both `comm_A` and `comm_B`.
  3. The agent calls `get_body()` on the bridging entities (`entity_x`, `entity_y`) and the core hub entities.
  4. The agent bisociates: it analyzes the conceptual delta between the two clusters, highlights how they are siloed, and generates a structured synthesis draft for the user to write a new note that bridges the two fields.

## 4. Horizon
1.0-now. It relies entirely on the existing Entity and LINKS_TO topology, and leverages KDB's already-implemented Louvain community and structural hole algorithms in `kdb_graph/analytics.py`.

## 5. Why it's the highest-value one
It transforms the personal knowledge graph from a passive archive into an active partner in thought. Instead of waiting for the user to ask questions, it highlights cognitive blind spots—where their ideas are forming isolated silos—and provides a concrete prompt to cross-pollinate them. This directly automates Koestler's model of bisociation, turning ad-hoc note-taking into a systematic engine for original idea generation.

## 6. Runner-up
**The Epistemic Debt Auditor:** Identify central concepts (high PageRank) with low grounding (zero or single `SUPPORTS` source edges) to target weak assumptions that lack documentation.
