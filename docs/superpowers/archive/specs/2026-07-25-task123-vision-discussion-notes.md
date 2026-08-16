# #123 Vision Discussion — Grounding Notes & Parked Questions

Date: 2026-07-25 · Task: **#123 Semantic graph search** · Status: **working notes** — content parked; each item is pulled into the structured discussion when the agenda reaches it. This is NOT the vision doc.

## Problem statement (ratified in conversation, 2026-07-25 — Joseph's four points)

1. **Observed**: pass-1 search keys (`warren-buffett`, `charlie-munger`, `mohnish-pabrai`) never get hits from the graphDB — on cold start or warm.
2. **Fundamental issue**: how to search the graphDB to identify relevant knowledge sources in terms of graphDB elements. **This is the single objective of the project.**
3. **First priority**: vision → spec → blueprint → implementation plan for that objective.
4. **Second priority**: chicken/egg — the build loop already consumes the missing search (pass-2 context loading), so search must be built iteratively while the graph itself is being built. Solution-venturing deferred until the vision exists.

## Grounding findings (codebase exploration, 2026-07-25; citations inline)

### Current retrieval machinery (what exists today)

- T2 resolution's effective surface is **exact primary-key equality only** (`kdb_graph/queries.py:466-489`). The resolver can also traverse `canonical_id` / `ALIAS_OF` edges, but the alias ledger that feeds those is **hand-curated** (D-R5-8; no code writes `state/canonicalization/aliases.json` — `docs/archive/tasks/task74-canonicalization-blueprint.md:68`), so it has always been empty and the alias paths never fire.
- Production always runs `T2Mode.STRUCTURED` + simple resolver (`orchestrator/kdb_orchestrate.py:711-718`); `LEGACY` (regex) and `LAYERED` are benchmark-only.
- Domain scoping already shipped: candidates are gated to the pass-1 `domain` cluster via `BELONGS_TO` before matching (`compiler/context_loader.py:189-193`).
- T3 = 1-hop BFS over `LINKS_TO` (2-hop only on cold start with <5 T2 seeds); ranking = tier then PageRank, cap 50 pages (`context_loader.py:211-241`).
- **Graph nodes carry almost no text**: `Entity{slug, title, page_type, status, canonical_id, first_run_id, …}` — no body, no summary, no embeddings (`kdb_graph/schema.py:61-74`). `Source.summary` is the only prose in the graph. No FTS/similarity index anywhere in `kdb_graph/`.
- The MCP server is a **second consumer** of the same exact resolver (`resolve_search_keys`, `kdb_mcp/adapters.py:87-104`) — this is not only the context loader's problem.
- #122 records capture per-key dispositions + tier slugs at event time (`compiler/context_record.py:49-66`) — the measurement layer for any search iteration. Baseline: T2 delivered ≈ 0.14–0.25 pages/source cold, 3.5 warm; `never_resolved` 0.56–0.74 (`docs/superpowers/evaluations/2026-07-25-task122-metric-baseline-cold-warm.md`).

### Prior art

- **NW-9 (#92, status `hypothesis`)** — `docs/archive/tasks/nw9-context-list-t2-t3-redesign-hypothesis.md`. Diagnosed the same wound ("T2 more noise than signal", doc:10; "no fuzzy/semantic bridge", doc:17). Hypothesis A = domain-scope + fuzzy-regex match on slug/title; its domain-scope half shipped (above), the fuzzy half never landed, and it was always labeled "structural retrieval, NOT semantic quality." Hypothesis B (T3 1-hop) untested.
- **#75 (closed)** — predeclared retrieval-eval criteria: the pattern for defining "the op returned the right thing" numerically BEFORE building the op (`docs/archive/tasks/task75-predeclared-eval-criteria-blueprint.md`). #123's success criteria should mirror this spine.
- **#74 canonicalization** — the alias/canonical machinery (`canonical_id`, `ALIAS_OF`) exists in the graph but is fed only by the hand-curated ledger.

### Joseph's stated priors (memory notes, quoted verbatim)

From `feedback_graph_over_vector_for_kdb.md`:

- "For Obsidian-KDB, do NOT propose VectorDB embeddings, dense vector retrieval, or RAG-style chunked similarity search as solutions to ontological / graph-traversal problems."
- "KDB's whole bet is 'explicit edges beat implicit similarity.'"
- For seed identification: "use **LLM-as-entity-linker** (hand the LLM a compact slug index `{slug, title, page_type}`, ask which slugs S mentions). Cheap at our scale (~3KB extra prompt at 62 pages). Shard by community at 10K+ pages."
- "Regex-on-slug-tokens… is a **recall floor** — cheap, deterministic… Acceptable as a recall mechanism… NOT acceptable as a relevance test… Augment with LLM entity-linking; don't replace with vectors."

From `feedback_obsidian_wikilinks_are_vanity.md`: Obsidian wikilinks/graph-view are display-only vanity; "GraphDB is the actual graph with utility."

North Star (`docs/CODEBASE_OVERVIEW.md` §8): the graph is the architectural primitive that downstream tooling (**search** listed first) consumes; §8.7 documents T1/T2/T3; **no `Open-N` question is registered for search** — #123 will need a milestone entry when its architecture lands.

## Parked questions (pull into the discussion when its agenda item arrives)

- **Q1 (backbone confirmation)** — Does `feedback_graph_over_vector_for_kdb.md` still define the vision's backbone? I.e., #123 = LLM-as-entity-linker over the graph's compact slug index, exact-match retained as the deterministic recall floor, vectors excluded by principle — context loader as first deployment surface, MCP/CLI following. Or has the thinking moved past it?
- **Q2 (scope)** — Is #123 the general search capability (with the context loader as its first client) or specifically the T2 fix? Where do MCP/CLI/human-query surfaces rank?
- **Q3 (constraints)** — Operational budget for identification: is an added LLM call (or calls) per compiled source acceptable (cost/latency), given pass-1+pass-2 already cost 2 calls? Any hard YAGNI lines beyond no-vectors?
- **Q4 (success criteria)** — What numbers define "search works" for iteration 1? (Candidates: T2 delivered mean, `never_resolved`, person-key hit rate on the probe corpus; #75-style predeclared pass/fail/gate.) What is the held-out test set?
