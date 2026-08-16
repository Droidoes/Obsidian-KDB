# #123 — Round 1 Panel Discussion Packet: HOW to implement semantic graph search?

Date: 2026-07-25 · Task: **#123 Semantic graph search** · Round 1 of the everyone-answers process (Joseph, Kimi, opus5, gpt5.6sol → synthesis → ratify → next step).
Respondents: please give independent reasoning. Our positions are included as seeds to react to — agreement is not expected or desired where you see a flaw.

## How to respond (opus5, gpt5.6sol, and any future respondent)

1. **This packet opens a discussion, not a one-shot questionnaire.** Engage Joseph in back-and-forth deliberation on the §5 questions — challenge the seeds in §3–§4, ask for clarification, refine the framing itself if you think it is wrong.
2. **Record the deliberation.** When the discussion converges, save a summary of the deliberations and the resulting positions/solutions as a doc named after this packet plus your respondent suffix — `2026-07-25-task123-round1-panel-discussion-<respondent>.md` (e.g. `-opus5`, `-gpt5.6sol`, `-codex`) in this same directory. Structure: your answer to each §5 question → key deliberation points → convergences and open disagreements.
3. Kimi (this project's resident agent) does the same on its side; all four answers are then synthesized into a convergence map that Joseph ratifies before the next step.

---

## 1. Ratified problem statement (settled between Joseph & Kimi, 2026-07-25)

1. **Observed**: pass-1 search keys (`warren-buffett`, `charlie-munger`, `mohnish-pabrai`) never get hits from the graphDB — cold start or warm.
2. **Fundamental issue**: how to search the graphDB to identify relevant knowledge sources **in terms of graphDB elements**. **This is the single objective of the project.**
3. **First priority**: vision → spec → blueprint → implementation plan for that objective.
4. **Second priority (chicken/egg)**: the build loop already consumes the missing search (pass-2 context loading issues ~10 key lookups per compiled source), so search must be built iteratively **while** the graph itself is being built.

Evidence record: `docs/superpowers/evaluations/2026-07-25-task122-metric-baseline-cold-warm.md` (T2 delivered ≈ 0.14–0.25 pages/source cold, 3.5 warm; `never_resolved` 0.56–0.74).
Grounding notes (current machinery, prior art): `docs/superpowers/archive/specs/2026-07-25-task123-vision-discussion-notes.md`.

## 2. System facts the answers must respect

- GraphDB = Kuzu. Node text is minimal: `Entity{slug, title, page_type}` only — no bodies, no summaries, no embeddings on nodes (`Source.summary` is the only prose in the graph). The compact index `{slug, title, page_type}` × N entities is effectively the graph's entire text (~3KB at 62 pages).
- Today's T2 resolution = exact primary-key equality (`kdb_graph/queries.py:466-489`); alias/canonical traversal exists but the hand-curated alias ledger has always been empty, so it never fires.
- A domain gate already shards candidates by the source's pass-1 domain (`compiler/context_loader.py:189-193`).
- Joseph's standing priors (memory notes, verbatim): **no VectorDB/embeddings/chunked-similarity** for this class of problem — "KDB's whole bet is explicit edges beat implicit similarity"; "use **LLM-as-entity-linker** (hand the LLM a compact slug index `{slug, title, page_type}`, ask which slugs S mentions)… shard by community at 10K+ pages"; regex/exact-match is "a **recall floor**… acceptable as a recall mechanism, NOT acceptable as a relevance test… Augment with LLM entity-linking; don't replace with vectors."
- Measurement exists: per-key dispositions + delivered tier pages at event time (#122), cold/warm baselines taken 2026-07-25.
- Consumers of search, in priority order claimed so far: (1) pass-2 context loader (per-source, automated, latency/cost-sensitive); (2) MCP server tools; (3) CLI/human queries.

## 3. Joseph's seed positions (2026-07-25, verbatim in substance)

- **[1]** Is there any industrial standard for searching Kuzu-type graphs?
- **[2]** Feed both the query and the entire graphDB to the LLM and ask it for the answer — brute force; one efficiency is subgraph-by-domain to reduce graph size. ("Overall this is a brute-force method for me.")
- **[3]** Implement RAG — not on the source, but on the graphDB. But by doing RAG we are effectively butchering the GraphDB as a meaningful AI search entity and treating it just like any document source.
- **Stop-gap question**: is there a stop-gap method for semantic graph search that we can use *while* building the GraphDB itself?

## 4. Kimi's position (to be tested)

- **[1]** No single standard; a layered canon: (a) exact/structural Cypher match (today's floor); (b) full-text/BM25 index — Kuzu has an unused FTS extension; token-level matching recovers surname-class hits for free (`warren-buffett` → "Buffett's Balance Sheet Rules of Thumb"); (c) **entity linking** — the NLP discipline whose name is literally our problem: candidate generation (cheap, high recall) → disambiguation (context-aware); (d) text2cypher — the industrial pattern for human/NL graph QA, relevant to MCP/CLI, not to per-source context loading; (e) GraphRAG-family vector retrieval — excluded by prior.
- **[2]** Raw form is impossible (nodes carry no bodies) and brute force. But feeding the query + the **compact index** (the graph's entire text) to an LLM and asking which slugs the source engages *is* the memory note's LLM-as-entity-linker — not brute force at current scale; the domain gate already provides the sharding. [2]-refined collapses into the sanctioned design.
- **[3]** Agreed — vector-chunk RAG butchers the graph; killed by prior. Keep one separation precise: "retrieve-then-reason" generically is not the sin; it is the objective. Only the retrieval mechanism is in question.
- **Stop-gap**: stop-gap and end-state as the same mechanism at different coverage, two iterations — **i1 deterministic recall layer** (exact + FTS/BM25 over slug+title; zero LLM cost; Kuzu-native) → **i2 semantic layer** (LLM-as-entity-linker over the domain-sharded compact index, batched to +1 call/source). Each iteration judged by the #122 event-time metrics against the 2026-07-25 baselines. Status-quo exact-match stays as the floor throughout.

## 5. Questions for the panel (opus5, gpt5.6sol)

1. **[1]** Is there an industrial standard (or dominant pattern family) for searching a Kuzu-class property graph to *identify relevant elements by meaning*? Where do FTS/BM25, entity-linking, text2cypher, and GraphRAG-style approaches each sit on the map — and which, if any, are we misjudging?
2. **[2]** Is "query + compact whole-graph index → LLM identification" a sound primary mechanism at ~10²–10³ nodes? What breaks first as N grows toward 10⁴–10⁵, and what is the right sharding/pre-filter discipline (domain, community, FTS candidate-gen) before the LLM step?
3. **[3]** Is the rejection of vector RAG over the graph correct *for this system's purpose* (ontology-faithful retrieval), or is there a hybrid that preserves "explicit edges beat implicit similarity" while recovering embedding recall where edges are sparse (cold graph)?
4. **Stop-gap**: what would YOU ship first as the stop-gap that lets the build loop consume real search immediately, without foreclosing the end-state? Is the i1-FTS → i2-LLM-linker sequencing right, inverted, or wrong?
5. **Blind spots**: what is the strongest argument that this whole framing (identify-by-meaning over a slug index) is the wrong level — e.g., should the graph be changed so that exact match *works* (write-time canonicalization, auto-alias edges, minted person/organization nodes) instead of making the reader smarter?
