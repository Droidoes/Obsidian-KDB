1. **The app, in one sentence**
**The Worldview Reconciliation Engine:** Map the active contradictions and superseded beliefs across my entire reading history to show me where I am currently holding incompatible ideas, and force a cognitive resolution.

2. **Why search can't do it**
Full-text search and vector retrieval retrieve passages based on semantic similarity, but they are fundamentally blind to propositional logic. Search cannot structurally distinguish between two sources that *agree* on a topic and two sources that *formally contradict* each other. It cannot traverse a topological chain of `SUPERSEDES` edges to trace how an intellectual paradigm shifted over time. Search operates on text overlap; this app operates exclusively on explicit epistemic relationships.

3. **The mechanism**
- **Nodes/Edges:** `Claim` nodes connected by `CONTRADICTS` and `SUPERSEDES` edges, joined to `Source` nodes via `EVIDENCES` edges.
- **MCP Tools Composed:** Implies two new tools beyond the day-one surface:
  1. `get_epistemic_tensions()`: A Cypher query matching `(c1:Claim)-[r:CONTRADICTS]-(c2:Claim) WHERE c1.state = 'active' AND c2.state = 'active' RETURN c1, c2, r`.
  2. `get_claim_provenance(claim_id)`: A query retrieving the specific `quoted_text`, `score`, and `Source` metadata across the `EVIDENCES` edge.
- **Agent Workflow:** The agent fetches all active `CONTRADICTS` pairs. For the highest-confidence collisions, it fetches the exact source quotes that ground both sides. It then presents the epistemic tension to the user: *"You are maintaining two active, contradictory claims: Claim X (backed by Author A) and Claim Y (backed by Author B). Let's write a resolution note that either QUALIFIES these claims into specific contexts, or formally SUPERSEDES one of them."*

4. **Horizon**
**2.0-needs-Claim-layer.** This is precisely the feature that justifies building the 2.0 Claim layer. Without it, the graph is just a topical map. The Claim layer elevates the graph into a truth-maintenance system, which is worth waiting for because it automates the hardest part of personal knowledge management: belief revision.

5. **Why it's the highest-value one**
It provides absolute metacognitive accountability. Human memory naturally compartmentalizes contradictory ideas when they are read months or years apart. By leveraging the graph to surface logical inconsistencies across the user's entire temporal reading history, the MCP server acts as an epistemic coach. It forces the user to transition from being a passive hoarder of highlights into an active synthesizer of a coherent worldview.

6. **Runner-up**
**The Cross-Domain Convergence Extractor (1.0-now):** Identify specific `Entity` hubs backed by `SUPPORTS` edges from three or more radically distinct `Domain`s to surface the user's foundational, universal mental models.
