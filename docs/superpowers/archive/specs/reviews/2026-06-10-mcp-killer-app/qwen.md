# Killer App Proposal — Epistemic Load-Bearing Stress Test

## 1. The App, in One Sentence

**"Which of my most influential ideas are structural bridges between knowledge clusters but rest on thin evidence?"** — a metacognitive stress test that intersects topological influence (PageRank), structural position (inter-community bridges), and evidential grounding (SUPPORTS degree) to surface load-bearing weak points in the user's knowledge.

## 2. Why Search Can't Do It

This query is a **three-dimensional graph predicate** with no textual approximation:

- **PageRank** is a global computation over the full LINKS_TO topology — an LLM reading all note bodies cannot approximate eigenvector centrality over a directed graph it never sees as a graph.
- **Structural holes** require Louvain community assignment followed by inter-community edge counting — the concept of "this idea bridges two emergent topic clusters" is invisible to text-level analysis because communities are *emergent from link structure*, not declared in prose.
- **SUPPORTS degree** is a provenance count (how many distinct Source nodes ground this Entity) — grep can find citations in a single body but cannot count how many *independently-ingested documents* converge on the same idea across the entire corpus.

The intersection — "high influence × bridge position × thin grounding" — is a compound structural query. Each dimension alone is graph-native; their conjunction is something no amount of text reading can produce. An LLM with full vault access would produce a *plausible-sounding* guess; the graph produces a *measured* answer.

## 3. The Mechanism

**Primitives composed (all existing, 1.0 graph):**

1. `analytics.pagerank(conn)` → `list[(slug, score)]` — rank all entities by topological influence.
2. `analytics.structural_holes(conn)` → `list[(comm_a, comm_b, n_bridges)]` — identify the sparsest inter-community bridges.
3. `analytics.communities(conn)` → `dict[slug → community_id]` — assign every entity to its Louvain community.
4. Per-entity SUPPORTS-degree query (one Cypher per candidate, or a single batched query):
   ```
   MATCH (e:Entity {slug: $slug})
   OPTIONAL MATCH (s:Source)-[:SUPPORTS]->(e)
   RETURN e.slug, count(DISTINCT s.source_id) AS support_count
   ```
5. `get_body(slug)` — fetch the wiki body for the top results so the LLM can explain *why* the grounding is thin.

**Algorithm:**

1. Compute PageRank; keep entities above the median score (the "influential" population).
2. Compute communities + structural holes; identify which entities sit on inter-community edges (bridge entities).
3. Intersect: entities that are both influential AND bridge-positioned.
4. For each candidate, compute SUPPORTS-degree. Rank by `pagerank_score / support_count` descending (high influence, low grounding).
5. Return top-K with: slug, title, PageRank score, community-pair it bridges, support count, and body excerpt via `get_body`.

**MCP tool it implies (beyond day-one six):**

One new tool: `stress_test(top_n=5)` — returns the ranked list. It composes three analytics calls and one aggregation query internally; the user sees a structured report, not raw Cypher. The LLM agent then reads the bodies via `get_body` and generates a natural-language explanation of each weak point.

This is *one tool call* from the user's perspective — not a three-step workflow they have to orchestrate. The composition is the value.

**No new schema, no new edges, no new nodes.** Everything runs on 1.0 primitives.

## 4. Horizon

**1.0 — answerable today.** PageRank, Louvain communities, and structural holes are all implemented in `kdb_graph/analytics.py`. SUPPORTS edges are in the schema (v1.0 baseline). `get_body` is on the day-one MCP tool list. Zero new infrastructure required.

**2.0 enhancement (optional, not blocking):** When the Claim layer lands, the stress test gains a second dimension — entities that are bridge-positioned with thin SUPPORTS *and* have CONTRADICTS edges against them from well-grounded claims become "contested load-bearing ideas." This is a strictly richer signal but not a prerequisite.

## 5. Why It's the Highest-Value One

**It changes what the user does next.** Retrieval answers a question you already had. This tells you a question you *should have had* — "is my most-connected idea about X actually well-supported, or have I been building on one source I read three months ago?"

Three concrete reasons this is the highest-value query:

1. **Recurring and time-sensitive.** Every compile run changes the topology. New sources add SUPPORTS edges (potentially strengthening weak points); new entities shift PageRank and community boundaries. The stress test is different after every compile. A user who runs it monthly gets a longitudinal view of their knowledge's structural health — "am I grounding my bridges, or building more of them on sand?"

2. **Generative downstream.** The output is not an answer — it's a *research agenda*. Each weak point is a prompt: "this idea connects your thinking about A and B, but you only have one source for it — go read more." This converts passive knowledge into active inquiry. No retrieval query does this; retrieval is backward-looking (what have I already captured?). This is forward-looking (where should I invest attention?).

3. **Uniquely personal.** Public knowledge graphs (Wikipedia, Semantic Scholar) have dense SUPPORTS by construction — millions of sources. A personal knowledge graph is *defined* by its grounding gaps. The stress test exploits exactly the property that makes a personal graph different from a public one: the user is both the author and the sole evidence base, so thin grounding is a meaningful signal about *their* epistemic state, not a data-quality problem.

## 6. Runner-Up

**Latent Connection Engine** — find entity pairs in different Louvain communities with no LINKS_TO edge, both above median PageRank, whose 1-hop neighborhoods have high Jaccard overlap (structurally similar but unlinked). Fetch both bodies via `get_body` and ask the LLM to propose a bridging hypothesis. Generative in the purest sense — *proposes connections the user never made* — but the Jaccard-over-neighbors similarity is a weaker signal than the stress test's three-dimensional intersection, and the LLM-generated bridge hypothesis risks hallucinating connections that don't genuinely exist. The stress test's output is *measured*; the latent engine's output is *speculated*. Measured beats speculated for a load-bearing tool.
