# Killer App Proposal — deepseek-v4-pro (2026-06-10)

## 1. The app, in one sentence

**"Which of my own ideas do I rely on the most, but have evidence for the least?"** — a ranked list of the user's *unexamined assumptions*, surfaced from the graph's topology.

---

## 2. Why search can't do it

Lexical search counts word occurrences. It can tell you "entity X appears in 3 sources" — a flat frequency. It cannot tell you that X has 47 other ideas linking TO it (it's structurally foundational to your thinking) while those 3 sources merely *mention* it without depth. The ratio of LINKS_TO indegree to SUPPORTS count is a purely topological signal: "how much of your knowledge graph stands on this idea" divided by "how much you've actually read about it." No text query can compute structural dependence — that lives entirely in edges, not bodies.

A grep for X's slug across the vault would find the same 3 sources and every page that links to X. The LLM reading those hits would see mentions and links as undifferentiated text. It wouldn't know that the 47 incoming links make X a *load-bearing pillar* while the 3 sources are thin. The graph's topology turns raw co-occurrence into a meaningful ratio, and that ratio is what makes the difference between "I use this idea" and "I assume this idea is true without checking."

---

## 3. The mechanism

### Core query: `unexamined_assumptions(n=10, min_indegree=3)`

Composed from day-one MCP tools + one new analytics primitive:

| Step | MCP Tool / Graph Primitive | What it does |
|------|---------------------------|--------------|
| A | `communities()` (Louvain) | Assign every entity a community ID for domain context |
| B | Per-entity: count incoming LINKS_TO edges | Structural dependence — how many ideas link TO this one |
| C | Per-entity: count distinct SUPPORTS sources | Evidentiary grounding — how many sources support it |
| D | Per-entity: `pagerank()` or direct indegree | Prioritize genuinely important entities over noise |
| E | `get_entity(slug)` for top-N | Fetch title, page_type, domain for presentation |
| F | `graph_neighborhood(slug, depth=1, direction="in")` | Show the user *which* ideas depend on each assumption |
| G | `sources_for_entity(slug)` | Show the user the (thin) evidence they're relying on |

**Scoring formula:**

```
assumption_score(entity) = ln(1 + indegree) / ln(1 + support_count)
```

- `indegree` = count of distinct entities with outgoing LINKS_TO → this entity
- `support_count` = count of distinct sources with SUPPORTS → this entity
- Entities with 0 supports get `support_count = 0.5` (Laplace-style smoothing to avoid division by zero — an entity with indegree 10 and 0 supports is a MASSIVE assumption)
- Filter: `page_type != 'summary'` (summary pages are synthetic roll-ups; their high indegree is a feature, not a signal)
- Filter: `indegree >= 3` (noise floor — an idea that only 1-2 other ideas link to isn't "load-bearing")
- Filter: `status = 'active'`

**Presentation format** (the MCP server returns to the agent/chat app):

```
Top unexamined assumptions in your knowledge graph:

1. "Efficient Market Hypothesis" (score 3.4)
   Relied on by 22 ideas  |  Supported by 2 sources
   Community: Finance Theory (#3)
   Dependencies: "Capital Asset Pricing Model", "Random Walk Theory", ...
   Evidence: "Fama 1970 review", "Malkiel Random Walk ch2"
   → You've built 22 ideas on EMH but only read 2 sources on it.

2. "Bayesian updating" (score 2.1)
   Relied on by 14 ideas  |  Supported by 3 sources
   ...
```

**New primitive implied beyond day-one six + `get_body`:**

- `indegree(slug)` — count of incoming LINKS_TO edges to an entity. Trivial to add (one Cypher `MATCH (a)-[:LINKS_TO]->(b {slug: $s}) RETURN count(a)`). Alternatively computable client-side by reversing `neighbors(slug, direction="in")` and counting results, but a dedicated count avoids materializing the full neighbor list.
- `entity_list(n=None, page_type=None, status="active")` — enumerate all entity slugs matching criteria, to iterate over for the scoring loop. The day-one six doesn't have a "list all entities" tool; this is the bulk-enumeration primitive.

---

## 4. Horizon

**1.0 — now.** The query uses only LINKS_TO, SUPPORTS, Louvain communities, and PageRank — all live in the current schema. No Claim layer required. The `indegree` and `entity_list` primitives are one-Cypher additions to `queries.py`, not schema changes.

The 2.0 Claim layer would *enrich* this query (adding "and here are CONTRADICTS claims that challenge this assumption") but the core signal — structural dependence vs. evidentiary grounding — is computable today.

---

## 5. Why it's the highest-value one

**It changes what the user does after every compile.** Today, after running `kdb-orchestrate`, the user gets KPI numbers (entity_reuse, link_density, orphan_rate) — aggregate statistics. They tell you whether the *pipeline* is healthy, not whether your *thinking* is healthy. This query bridges that gap: it turns the compile artifact into a personal intellectual audit.

**It's metacognitive in the strongest sense.** It doesn't retrieve what the user already knows — it surfaces what the user *doesn't know they're assuming*. The 47 incoming links to EMH are the user's own wikilinks, authored by the user's own LLM pipeline. The query holds up a mirror: "you built this elaborate structure on 2 sources. Is that enough?"

**It's recurring — the graph evolves, the assumptions shift.** Every time new sources are ingested and new entities are compiled, the indegree landscape changes. An entity that was well-evidenced last month might become an assumption this month if new ideas link to it faster than new sources support it. The user would run this after every significant compile batch.

**It's generative — it implies the next action.** Unlike retrieval ("show me X"), the answer to this query is a TODO list: "read more about EMH," "find a second source on Bayesian updating," "or write a note acknowledging that you're taking this on authority." It doesn't just show the user their graph — it tells them where to put their attention.

**It has no alternative implementation.** You can't simulate this with search + an LLM. The LLM reading all 47 bodies that link to EMH wouldn't compute indegree — it would see mentions, not structural dependence. The ratio *requires* the graph.

---

## 6. Runner-up

**"What am I not connecting?"** — find entity pairs in different Louvain communities that share ≥2 supporting sources but have no LINKS_TO edge between them (latent syntheses the sources' authors saw but the user's graph hasn't captured). This is generative (it proposes new links to author), fully 1.0, and recurrable — but it's a suggestion engine, not an audit. The assumption detector is more uncomfortable, and discomfort is higher-value for a personal knowledge system.
