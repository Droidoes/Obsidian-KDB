# VectorDB vs GraphDB for knowledge-DB retrieval — 2026-08-09

> Filed at Joseph's request as **Task #141** (`docs/TASKS.md`) — a fundamental
> topic to record now and discuss deliberately later. Thinking-work, not
> implementation; nothing here implies code changes. Joseph's framing: *"should
> we also build a vectorDB, and the effectiveness of vectorDB vs GraphDB… not
> exactly an apple/apple comparison, but in terms of retrieval of the Knowledge
> DB it is relevant."*

## The question

Does a vector index earn a place next to the Kuzu graph as a retrieval engine
for the knowledge base — for which query classes, at what cost, and with what
evidence that it outperforms (or complements) what the graph already does?

## What we retrieve with today (so the comparison is grounded)

- **Exact identity resolution** — aliases/slugs; the founding problem (PK/regex
  couldn't find "Buffett") is solved structurally, no embeddings involved.
- **Graph traversal** — LINKS_TO/SUPPORTS walks with receipts back to source
  files (`graphdb-kdb neighbors/path/cypher`, the 7-tool MCP server).
- **Two-stage LLM selection** (pass-1.5, #123) — thin→fat selector over a
  graph-materialized space, with an audit payload per search. This is semantic
  relevance *without* an embedding index anywhere in the system.
- **FTS** — ratified as CLI/MCP-surface infrastructure (spec §7.2, D4),
  explicitly *not* the relevance mechanism; currently unwired.

So the honest baseline: we already have semantic retrieval (LLM-scored, with
provenance) and structural retrieval (edges), but **no fuzzy "find things like
this text" front door** and no cheap unsupervised similarity anywhere.

## Landscape (consistent with the 2026-08-07 survey, Part 4)

- Vector RAG wins **single-fact / fuzzy-phrase lookup** and cold-starts on any
  text with zero structure work. It returns *documents*, not assemblies.
- Graphs are required for **multi-hop reasoning, cross-referencing,
  contradiction/evolution questions** — and carry provenance natively
  (SUPPORTS edges are the receipts a vector hit can never give).
- **Hybrid is the 2026 production consensus** (Mem0 graph+vector+KV, Zep,
  Neo4j+LangChain hybrid retrieval; Microsoft GraphRAG retrieves with
  embeddings over graph-derived summaries). The frontier question is not
  "which one" but "which engine answers which query class, and how they
  hand off."
- Cost asymmetry already on record: GraphRAG-style indexing runs 5–10× the
  LLM cost of vector indexing — we *paid that once* in the maiden run; a
  vector index is cheap to add later, the graph was expensive to build first.

## Where a vector index would actually slot in (candidate roles)

1. **Query-time fuzzy front door** — "find notes about X" when the exact entity
   or wording is unknown; the one query class we genuinely cannot serve today.
2. **Ingestion hygiene** — near-duplicate clipping detection, candidate
   aliases for the resolver (assist, never authority — closed-world discipline
   stays with the controller).
3. **Corpus-gap / serendipity signals** — nearest-neighbor maps as a cheap
   complement to the Louvain/structural-holes structure we just measured.

Where it does **not** help: provenance, multi-hop assembly, contradiction
mapping (needs typed edges), pass-1.5 T2 seeding (already LLM-scored with
receipts — an embedding seed would be a *regression* in auditability there).

## Evaluation axes for the discussion

- **Joseph's real query classes** — enumerate what he actually asks the vault;
  mark each vector-only / graph-only / hybrid. This decides the question, not
  benchmark folklore.
- **Cheapest honest spike** — embed summaries (local model, one pass over
  ~1,600 sources), run ~20 real questions three ways; compare answer quality
  *and* receipt quality. Small money, real evidence.
- **FTS-first option** — D4's full-text track may be the 80% answer for the
  fuzzy front door before any embedding infrastructure exists at all.
- **Maintenance** — embedding-model churn (re-embed on model change), index
  lifecycle vs. the graph's rebuildable-from-journals discipline; new
  pipelines (#139's prompt archive + Substack flow) make this a growing
  corpus, which *strengthens* the vector case over time.
- **Sequencing** — decide after #139's use-case pick: the query-time traversal
  agent (Joseph's lean) would consume either engine, and its design tells us
  which one it wants first.

## Open threads (#141)

1. Enumerate the real query classes and their right engine (the deciding
   artifact).
2. FTS-before-vectors: does the ratified D4 track close the gap cheaper?
3. If a spike is warranted: minimal local-embedding experiment, three-way
   scored (vector / graph / hybrid) on real questions.
4. Record the decision back here and in `docs/CODEBASE_OVERVIEW.md` if a
   build follows.
