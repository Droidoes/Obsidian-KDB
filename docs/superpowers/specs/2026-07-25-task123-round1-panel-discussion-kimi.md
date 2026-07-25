# #123 Round 1 — Kimi's answer & deliberation record

Date: 2026-07-25 · Respondent: **Kimi** (resident agent) · Packet: `2026-07-25-task123-round1-panel-discussion.md`
Independence note: written **before** reading opus5's or gpt5.6sol's responses, deliberately — this record is my independent answer plus a summary of the Joseph↔Kimi deliberation that produced it.

## Answers to the §5 questions

### Q1 — Industrial standards for searching a Kuzu-class graph by meaning

No single dominant standard exists for "identify relevant elements by meaning" over a property graph; the industrial reality is a **layered canon**, and production systems compose layers rather than pick one:

1. **Exact/structural match** (Cypher predicates, PK lookup) — deterministic, free, the floor. This is all we run today.
2. **Full-text / BM25 index** — the database-standard recall layer (Neo4j Lucene, Kuzu FTS extension — unused by us). Token-level matching over `{slug, title}` recovers surname-class hits (`warren-buffett` → "Buffett's Balance Sheet Rules of Thumb") with zero LLM cost. Not semantic, but materially better recall than exact-slug.
3. **Entity linking** — the NLP discipline whose name *is* our problem: mention → candidate generation (cheap, high recall) → disambiguation (context-aware, more expensive per candidate). Any honest version of #123 is an instance of this shape whether we name it or not.
4. **text2cypher** — the industrial pattern for *human/NL* graph QA (Neo4j, LangChain GraphCypherQAChain). Relevant to our MCP/CLI surface later; wrong tool for per-source context loading (keys are already structured).
5. **GraphRAG-family** (vector retrieval over graph-extracted chunks) — the current hype default; excluded here by Joseph's standing prior, and I concur (see Q3).

The search-engine two-stage pattern (deterministic recall → expensive ranking) is the closest thing to a "standard"; entity-linking is its graph-native name.

### Q2 — Is "query + compact whole-graph index → LLM identification" sound at 10²–10³ nodes?

Yes, and it is the memory note's LLM-as-entity-linker. It is not brute force at this scale because nodes carry no bodies — the compact index `{slug, title, page_type}` *is* the graph's entire text (~3KB at 62 pages). What breaks first as N grows:

1. **Prompt size** — linear in N; dies somewhere between 10³ and 10⁴ without sharding.
2. **Attention dilution** — identification quality over long flat lists degrades well before the context window is full; scoped candidate sets are a quality requirement, not just a cost one.
3. **Cost/latency** — one linker call per compiled source is sustainable; per-key calls are not.

The right discipline: deterministic pre-filter (domain gate — already shipped; FTS candidate-gen — cheap to add) → LLM disambiguates *within* scope. The LLM should not see the whole graph once N exceeds a few hundred; the index is the sharding currency, domain/community is the shard key (memory note: "shard by community at 10K+ pages").

### Q3 — Is rejecting vector RAG over the graph correct for this system's purpose?

Yes, and stronger than taste: embeddings would let retrieval *appear* to work while the ontology stays sloppy — the similarity glow masks exactly the signal (misses, orphans, bad slugs) that forces ontological discipline. That is the vanity-graph failure mode this project has hedged against since the Round-5/6 reviews. The honest caveat: on a cold/sparse graph, pure-structure retrieval starves. The answer is not stored vectors — it is the LLM-linker, which borrows the LLM's *parametric* semantics at query time while the graph itself stays explicit. A vector layer as *measurement* (benchmarking recall against the linker) would be legitimate; as *mechanism* it is excluded.

### Q4 — What stop-gap ships first?

My position: **i1 deterministic recall layer → i2 semantic layer**, each judged by the #122 event-time metrics against the 2026-07-25 baselines.

- **i1**: exact + FTS/BM25 over `{slug, title}`, token-level. Deterministic, zero marginal cost, Kuzu-native, ships in days; immediately lifts surname-class recall; and it is the candidate-generation layer the linker will need at scale anyway.
- **i2**: LLM-as-entity-linker over the domain-sharded compact index, batched to +1 call per source.

Inverted order (linker first) is defensible — the linker is the end-state and may make FTS moot. My reason for FTS-first is sequencing risk: i1 is cheap and certain, i2 is where the design questions live. What is **not** negotiable either way: exact-match stays as the floor throughout, and nothing ships unmeasured. I hold the ordering loosely — if the panel flips it with a strong argument, fine.

### Q5 — Blind spot: is read-time intelligence the wrong level? Should the graph be changed so exact match works?

The strongest counter-framing, and it deserves to be taken seriously: the `ALIAS_OF`/`canonical_id` machinery already exists but is fed by a hand-curated ledger that has *always* been empty — write-time intelligence was designed and never switched on. The compiler prompt already tells the LLM to "reuse by meaning, not spelling" at write time; extending compile to *emit* alias edges (and, at the extreme, mint person/org nodes) would make exact match succeed for the recurring-name class (`buffett` → `warren-buffett`) with zero query-time cost.

My take: write-time and read-time intelligence are **complements, not rivals**. Auto-aliasing shrinks the miss set but cannot cover open-world naming ("Oracle of Omaha" → `warren-buffett`); the linker covers open-world naming at per-query cost. The empty-machinery fact says write-time automation is cheap to switch on (intake already upserts alias entities — someone just has to emit them). Likely synthesis: both, sequenced — and the stop-gap question may partly dissolve if auto-alias lands early. Flagged as the item most likely to change my Q4 answer.

## Deliberation record (Joseph ↔ Kimi, 2026-07-25)

1. Kimi's first framing — "pass-1↔pass-2 entity-vocabulary mismatch" — was **wrong**: it accepted exact-slug matching as a law and prescribed vocabulary alignment (stop emitting person keys / mint person pages / discount them in metrics). Joseph rejected it: string matching is not the premise; intelligent identification is the point of building the graph at all.
2. Reframed and ratified as the four-point problem statement (packet §1): the graph *knows*; the lookup is literal; semantic graph search is the project's single objective and does not exist; the context loader impersonates it.
3. Joseph's boundary discipline: no solution-venturing before vision; chicken/egg acknowledged and deferred; metrics (#122 T1/T2/T3) stand unchanged — "T2 is 0 while it should be 50 (numbers arbitrary)".
4. Naming discipline: no fluff in terms ("entity mention" struck from the task title; task is **Semantic graph search**, full stop).
5. Process ratified: everyone-answers rounds (Joseph, Kimi, opus5, gpt5.6sol) with recorded deliberations → synthesis → Joseph ratifies → next step.

## Open items I carry into the synthesis

- i1/i2 ordering (Q4) — weakest part of my position.
- Whether write-time auto-alias belongs in #123's scope or as its own fast follower (Q5).
- Success criteria for iteration 1 (deferred from this round; needs its own round — targets for T2 delivered mean / `never_resolved` on the baseline corpus, #75-style predeclared).
