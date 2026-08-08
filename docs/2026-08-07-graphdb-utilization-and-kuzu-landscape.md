# GraphDB utilization discussion + Kuzu landscape — 2026-08-07

> Captured 2026-08-08 from the session log (the original discussion happened while
> attempt 1 of the maiden vault run was in flight; the session was later killed by
> the WSL VM crash-loops). Tracked as **Task #139** in `docs/TASKS.md`.

## The question (Joseph)

How are we going to utilize the GraphDB we are building — in the most intelligent
way possible, i.e. identify the uses that would otherwise be impossible or
difficult? And: does the industry actually run graph databases (e.g. Kuzu) in
production, or is this a niche bet?

## Part 1 — What the graph uniquely enables (four primitives, ascending leverage)

1. **Resolved entity identity.** `warren-buffett` is one node across ~200 sources,
   whether a clipping says "Buffett," "Warren Buffett," or "Berkshire's chairman."
   The founding wound of the project (PK/regex couldn't find him). Everything else
   builds on this.
2. **Multi-hop traversal with provenance.** Person → Concept → Article → SUPPORTS →
   back to the exact source file. "What do the investors I track say about capital
   allocation, and where does each claim come from" is a graph walk — no vector
   search answers that, because the answer is an assembly, not a document.
3. **Global structure.** PageRank, communities, structural holes — only exist with
   the full edge set. Genuinely impossible in flat Obsidian: the graph can surface
   things about the knowledge base that were never written down.
4. **A machine-consumable schema.** Via `kdb_mcp`, any agent session can query the
   vault as structured memory instead of grepping markdown.

## Part 2 — Candidate builds, ranked (from the discussion)

- **Contradiction and evolution mapping** (top pick). The vault is full of sources
  that disagree (Shilling deflation vs others' inflation; Buffett's 2006-era vs
  later capital allocation). "Show me where my sources conflict on X," anchored on
  shared concept nodes with date-stamped sources. Pieces exist in the parked 2.0
  tier (`kdb_graph/ops`, `core` — O1 promotion, belief classifier, unwired); this
  is the natural reason to finish wiring it.
- **Structure-driven discovery.** `graphdb-kdb communities` + `structural-holes` on
  the maiden graph. Communities cross the folder taxonomy (OneNote folders are how
  things were *filed*; communities are how they *relate*). Structural holes are the
  inverse: bridges = synthesis candidates; empty holes = reading-list gaps.
- **Agentic query-time traversal.** Pass-1.5 uses the graph at *ingest* time; the
  mirror image is using it at *question* time — an agent walking the graph to
  assemble answers with citations back to source files via SUPPORTS. `kdb_search`
  was deliberately built consumer-neutral; this is its second consumer.
  **Joseph singled this out as exactly one of the use cases he has in mind.**
- **The flywheel already running.** The graph improves its own ingestion (pass-1.5
  context seeding); the same loop applies to curation (orphans, near-duplicate
  clippings, deprecated-page hygiene).

**Free vs. needs-building:** `pagerank`, `communities`, `structural-holes`, `path`,
`cypher`, and the MCP server all exist today — zero new machinery to start
exploring structure the moment the maiden run lands. Needs building: the
belief/contradiction layer (wire the parked 2.0 tier), the query-time traversal
agent, anything temporal ("how did my sources' view on China evolve 2015→2025").

**Recommended first step (unchanged):** run the free analytics on the fresh maiden
graph — the cheapest test of whether the structure is rich enough to justify the
belief layer. If communities/holes surface things the owner didn't know about his
own vault, the graph has crossed from plumbing to asset.

## Part 3 — The Kuzu fact (verified 2026-08-07, web)

- **KuzuDB was archived in October 2025 after being acquired by Apple**; active
  development of the original project stopped. We are pinned `kuzu>=0.11`, running
  0.11.3 — the last line of the original project.
- Community continuation: **LadybugDB** (MIT fork, actively evolving, Cypher-compatible).
  Vela Partners maintains their own Kuzu fork with concurrent multi-writer for
  production agent memory. GitNexus (code-intelligence) migrated Kuzu→LadybugDB.
- **Read at the time: no action needed** — Kuzu is embedded (no server, no network
  surface), the engine is stable, and our graph is rebuildable from journals, so
  migration cost is bounded if we ever move to LadybugDB.
- **Owner ruling 2026-08-07: parked as a noted fact, no ledger entry** — now
  recorded here and carried by #139 so the dependency decision is revisited
  deliberately rather than by accident.

## Part 4 — Industry landscape (verified 2026-08-07, web)

- **GraphRAG for enterprise search** — the pattern we independently built.
  Microsoft GraphRAG is the most-adopted OSS implementation (entity extraction,
  Leiden communities, hierarchical summaries — notably stores parquet + networkx,
  no graph DB). Persistent-graph production pattern: Neo4j + LangChain with hybrid
  vector+graph retrieval. 2026 consensus: vector RAG wins single-fact lookup;
  graphs are *required* for multi-hop reasoning, causal chains, cross-referencing —
  and the frontier is shifting from "graph-assisted retrieval" to "graph-driven
  reasoning" (= the query-time traversal direction Joseph picked).
- **Agent memory** — hottest 2026 category, closest analog to us: Mem0 (hybrid
  graph+vector+KV), Zep/Graphiti (temporal KG, real-time), Cognee (graph-first
  memory control plane — supports Kuzu as a backend, validating the engine choice).
  Vela Partners' Oxford research: *"the structure of relationships between signals
  and outcomes carries predictive information that the signals alone do not"* —
  the academic case for the contradiction-mapping use case.
- **Classic production uses** (pre-LLM, still where the money is): fraud rings/AML
  (TigerGraph), recommendations (Pinterest Pixie), big knowledge graphs (Google,
  LinkedIn Economic Graph, Bing Satori), identity resolution/MDM, pharma R&D, code
  intelligence.
- **Cost caveat:** GraphRAG indexing runs 5–10× the LLM cost of vector RAG — what
  the maiden run pays once, up front. Worth it for multi-hop/contradiction
  questions; not for simple lookup. Joseph's use cases are all in the "yes" column.

## Where we sit in this map

The emerging GraphRAG + agent-memory pattern, but with discipline the popular
frameworks lack: per-source incremental compile with commit semantics, provenance
edges to source files, a rebuildable live ontology authority, and a read-only MCP
surface. Microsoft GraphRAG does one-shot batch extraction; Mem0/Zep do
conversational memory; ours is a curated research corpus with receipts.

## Why the Kuzu question is now load-bearing (Joseph, 2026-08-08)

Joseph's change of mind on the "noted fact" parking: he is considering **two
additional ingestion pipelines** —

1. **Prompt archive** — prompts from different models, ingested as knowledge
   sources.
2. **Substack subscriptions** — filtered subscription emails from the Gmail inbox
   `joseph.ft.public@gmail.com`, ingested as a continuous flow (not a one-shot
   backfill).

If either is built, the graph stops being a bounded one-vault artifact and becomes
a **long-lived, continuously growing production dependency** — which is exactly
the condition under which "the engine is archived" graduates from a noted fact to
a viability question that needs a deliberate answer (stay / fork-migrate /
re-platform) *before* the new investment compounds on top of it.

Scale reality check: neither pipeline stresses the engine technically (thousands
→ tens of thousands of sources is nothing for an embedded columnar graph store).
The pressure is **dependency longevity and ecosystem drift** (no fixes, Python
version wheel decay, on-disk format obsolescence), not performance.

## Open threads for the follow-up discussion (#139)

1. Pick the first post-maiden-run use case: contradiction mapping vs structure
   exploration vs query-time traversal agent (Joseph leans traversal).
2. Run the free analytics (`pagerank`/`communities`/`structural-holes`) on the
   maiden graph and review what structure actually emerged — gate for the belief
   layer.
3. Kuzu dependency watch: when (if ever) to evaluate LadybugDB; trigger =
   hitting a Kuzu limitation or LadybugDB reaching clear maturity.
4. Temporal dimension ("how did my sources' views evolve") — no machinery exists;
   scope only if it survives the first three.
