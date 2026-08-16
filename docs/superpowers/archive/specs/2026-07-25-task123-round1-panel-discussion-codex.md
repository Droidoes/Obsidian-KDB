# #123 — Round 1 Panel Discussion: Codex Response

**Date:** 2026-07-25
**Task:** #123 — Semantic graph search
**Respondent:** GPT-5.6 / Codex
**Status:** Independent discussion position and proposal — **not ratified**

## 1. Starting point agreed with Joseph

The project is missing an intelligence capability with this responsibility:

> Given a search input, identify and return the relevant existing GraphDB
> entities.

The search input may be a name, phrase, structured key, natural-language
question, source excerpt, or another future representation. The output is
always expressed in terms of GraphDB entities, not document chunks or invented
identifiers.

That capability does not exist today.

The current exact-slug resolver is a deterministic lookup primitive. It can
answer whether an entity with a known identifier exists; it cannot determine
which graph entities are relevant by meaning. FTS, BM25, LLM selection,
text2cypher, graph traversal, embeddings, aliases, and richer ontology are
possible mechanisms or supporting layers. None of them should be confused with
the missing capability itself.

For clarity, this response calls the conceptual capability
**Graph Search Intelligence** and a possible software boundary
`GraphSearchEngine`. “Intelligence entity” does **not** mean a new node stored
inside Kuzu.

## 2. Capability contract before implementation

The architecture should begin with a stable behavioral contract, not with a
choice of retrieval technology.

### Input

A `GraphSearchRequest` should carry:

- one or more search expressions;
- optional disambiguating context, such as a source excerpt or the user's
  full question;
- optional constraints or priors, such as domain and allowed page types;
- the consumer identity (`context_loader`, `mcp`, or `cli`);
- a result limit.

The context loader should submit all Pass-1 keys for one source as one batch.
The design must not require one LLM call per key.

### Output

A `GraphSearchResult` should contain:

- ranked references to existing, active, canonical GraphDB entities;
- the search expression(s) each hit answers;
- bounded evidence explaining why the hit was selected;
- the resolution path, such as exact, alias, lexical, LLM-selected, or a
  combination;
- confidence or ranking information whose semantics are explicit;
- completeness and failure telemetry;
- no unknown, fabricated, inactive, or ambiguous entity identifiers.

An illustrative shape—not a ratified schema—is:

```text
GraphSearchRequest
  expressions: [SearchExpression]
  context: optional text
  domain_prior: optional domain
  page_types: optional set
  consumer: context_loader | mcp | cli
  max_results: integer

GraphSearchResult
  hits:
    - slug: existing canonical slug
      title: current graph title
      page_type: current graph page type
      matched_expressions: [string]
      resolution_paths: [exact | alias | lexical | semantic]
      evidence: bounded string or structured features
  unresolved_expressions: [string]
  trace: candidate and selector telemetry
```

### Invariants

1. **Graph authority:** the engine may return only entities verified against
   the graph snapshot used for the search.
2. **Read-only:** search does not mutate Kuzu, aliases, wiki pages, or source
   frontmatter.
3. **Canonical output:** aliases may be accepted as input, but the output is
   the unique active canonical entity.
4. **Fail closed on identity:** an LLM-selected slug absent from its declared
   candidate set or the live graph is rejected, never repaired by similarity.
5. **Honest empty result:** if no relevant graph entity exists, return no hit.
   Search cannot manufacture ontology.
6. **Evidence separation:** candidate generation, semantic selection, and
   downstream graph expansion are measured separately.
7. **Consumer-neutral core:** the same capability serves the context loader,
   MCP, and CLI; consumer adapters may choose different latency, ranking, and
   expansion policies.

## 3. Answer to Question 1 — industrial pattern family

There is no single industrial standard called “semantic property-graph
search.” There is a stack of established patterns:

1. **Identifier and structural query:** primary-key lookup and Cypher/GQL
   answer known-identity and known-relationship questions.
2. **Lexical candidate generation:** inverted indexes and BM25 retrieve nodes
   whose indexed text overlaps a query. Kuzu's FTS extension implements BM25
   over `STRING` properties on node tables.
3. **Entity linking / resolution:** candidate generation narrows the knowledge
   base; contextual ranking or disambiguation chooses the intended entries.
4. **Graph expansion and ranking:** traversal, path constraints, topology, and
   provenance expand or rerank known seeds.
5. **Natural-language graph query:** text2cypher translates an articulated
   relationship question into a structural query.
6. **GraphRAG-family retrieval:** a broad family combining text retrieval,
   graph indexing, traversal, communities, summaries, vectors, or generated
   queries. The name does not imply one retrieval algorithm.

The dominant reusable pattern for #123 is:

> high-recall candidate generation → contextual selection/disambiguation →
> graph-authoritative validation → optional structural expansion

This resembles entity linking, but #123 is broader. A search expression such as
`warren-buffett` may have no same-named person node. The desired result can
instead be knowledge-page entities about Buffett. That operation is retrieval
of relevant graph elements, not merely linking a mention to a same-identity
referent.

FTS/BM25 therefore belongs in **candidate generation**, not in the final
relevance decision. It can likely recover surname-bearing pages such as
Buffett-titled entities, but it cannot establish that differently worded
concepts are relevant.

Text2cypher belongs primarily to the MCP/CLI question-answering surface. It is
useful when the request already implies a structural query—for example,
“Which concepts supported by two sources link to capital allocation?” It does
not independently solve `warren-buffett` → relevant page entities when that
correspondence is absent from the graph.

## 4. Answer to Question 2 — compact whole-graph index plus LLM

At approximately \(10^2\)–\(10^3\) entities, sending a compact index
`{slug, title, page_type}` plus the search request to an LLM is a sound semantic
selection mechanism. It is especially appropriate as a small-graph operating
mode because:

- the complete candidate population still fits cheaply in context;
- candidate recall is 1.0 for every entity represented in the index;
- the LLM can bridge vocabulary differences that exact and BM25 cannot;
- the controller can validate every returned slug against the supplied index
  and graph;
- no secondary retrieval store is needed.

It should not be described as “feed the entire GraphDB to the LLM.” The index
contains only bounded identity metadata; it does not contain bodies, source
provenance, edges, or the complete database. This distinction is important for
both cost and authority.

The mechanism is nevertheless bounded by the information in that index. If
title and slug do not reveal what an entity means, even a capable LLM may have
insufficient evidence. Apparent success may also come from the model's
parametric knowledge rather than graph evidence. The system must evaluate
results against a fixed graph snapshot and held-out relevance truth, not
assume plausible selections are grounded.

### What breaks as the graph grows

Toward \(10^4\)–\(10^5\) entities:

- prompt size and cost grow linearly;
- selection becomes less stable as near-duplicate candidates multiply;
- a single global list exceeds practical attention and latency budgets;
- domain and community labels can be wrong or incomplete;
- the model may overlook valid candidates in long indexes;
- returning the whole index leaks implementation scale into every consumer
  call.

The scaling path should preserve the same search contract while changing only
candidate generation:

1. exact and alias resolution remain always-on;
2. lexical/FTS retrieval produces a bounded global candidate set;
3. domain and page type act as ranking features or requested constraints;
4. graph neighborhood and provenance features can rerank candidates;
5. the LLM sees only the bounded candidate set plus disambiguating context;
6. community sharding becomes useful only after communities are empirically
   meaningful.

### Domain is a prior, not automatically a gate

The current context loader uses same-domain filtering as a hard candidate gate.
That may suppress relevant cross-domain entities before search intelligence can
consider them. Buffett-related knowledge can legitimately cross investing,
insurance, management, philanthropy, and psychology boundaries.

Three distinct semantics should not be conflated:

- **constraint:** the caller explicitly permits only one domain;
- **prior:** same-domain candidates rank higher;
- **fallback shard:** search same-domain first, then search globally if recall
  is weak.

My proposal uses a domain prior with a global fallback for the context loader.
An explicit caller constraint remains possible for other consumers.

## 5. Answer to Question 3 — vector retrieval

The rejection of vector RAG is correct for the first #123 architecture, but the
reason should be precise.

Today's entities expose little semantic text beyond slug and title. Embedding
that surface is unlikely to add enough recall over token/FTS candidate
generation plus an LLM selector to justify another index, lifecycle, dependency,
and evaluation regime. Vector retrieval also cannot determine graph authority;
it can only propose candidates.

However, using embeddings solely as a candidate generator would not logically
replace or “butcher” the graph. A hybrid could preserve graph authority by
requiring all selected results to be existing graph entities and using explicit
edges for expansion and reasoning. The objection is therefore not that vectors
are intrinsically incompatible with ontology-faithful search. It is that they
are unnecessary and weakly grounded for the present graph representation.

Position:

- **v1:** no vectors;
- **future:** reconsider only if the graph acquires enough entity-owned
  descriptive text and held-out tests demonstrate a lexical/LLM candidate
  recall gap;
- **never:** vector similarity must not become entity authority or substitute
  for graph validation.

## 6. Answer to Question 4 — stop-gap

I would not declare FTS alone to be the stop-gap intelligence. It is a better
recall floor, but it still answers lexical overlap rather than relevance by
meaning.

The first useful stop-gap should be the smallest end-to-end implementation of
the final contract:

1. read the active canonical compact index from Kuzu;
2. normalize and exact/alias-resolve the request;
3. at the current graph size, present the remaining expressions plus the
   complete compact index to one LLM selector call;
4. require structured output containing only supplied slugs;
5. validate selected slugs against the candidate index and live graph;
6. return ranked graph references and telemetry;
7. let the context loader separately perform T3 expansion.

This directly creates the missing semantic capability while the graph is
small. Exact match remains a zero-cost fast path.

FTS/BM25 should then be added as a bounded candidate generator and evaluated
before it becomes mandatory. Once the graph crosses a measured size, latency,
or prompt-cost threshold, the engine switches from whole-index selection to
prefiltered selection without changing the public contract.

This sequencing differs from “i1 FTS → i2 LLM linker”:

- FTS-first is cheaper and deterministic, but it does not yet satisfy the
  agreed capability;
- whole-index LLM-first integrates the actual semantic boundary immediately;
- FTS then solves an observed scaling problem rather than an anticipated one.

Both layers need independent tests. Candidate recall must be measured before an
FTS top-\(K\) cap is allowed to hide entities from the selector.

## 7. Answer to Question 5 — strongest blind spot

The strongest counterargument is that query-time intelligence may compensate
forever for missing ontology.

Pass 1 is instructed to emit real-world subjects such as `warren-buffett`, but
the graph's three page types do not require a corresponding subject node or an
explicit “about” relationship. A reader can infer that several pages concern
Buffett, while Kuzu cannot represent that inference structurally.

There are three truly distinct architectural approaches:

### Option A — query-side intelligence over the existing page graph

Keep the current ontology. Build a read-only engine that retrieves page
entities by meaning.

**Tradeoffs**

- Lowest implementation and migration cost.
- Immediately serves all three consumers.
- Highly reversible.
- Recurring LLM cost and latency unless deterministic paths suffice.
- Every search compensates for meaning absent from the graph.
- Semantic results are ephemeral unless separately recorded.

### Option B — write-side semantic ontology

Add real-world subject entities or typed subject records and explicit
relationships such as `ABOUT`. Compilation materializes page-to-subject
correspondence; search resolves subjects then traverses structurally.

**Tradeoffs**

- Meaning compounds inside the durable asset.
- Exact/structural search becomes substantially more capable.
- Higher schema, migration, prompt, canonicalization, and verifier cost.
- Requires lifecycle rules for identity, aliases, merges, and unsupported
  subjects.
- Not a stop-gap; it changes what the graph is.
- Harder to unwind if the subject model is wrong.

### Option C — learned transitional hybrid

Ship query-side intelligence now. Persist only auditable search telemetry—not
graph mutations—showing repeated, high-confidence search-expression-to-entity
correspondence. A later, separately ratified learning contract may promote
stable relationships into aliases, subject nodes, or typed edges.

**Tradeoffs**

- Delivers current value while producing evidence for ontology evolution.
- Keeps v1 search read-only and reversible.
- More extensible than Option A.
- Risks a permanent dual system if promotion is never designed.
- Promotion would overlap the parked #83–#87 metacognition tier and must not
  be smuggled into #123.

These options should be discussed explicitly. They should not block creating
the common search contract because all three require an input-to-graph-entity
resolution boundary.

## 8. Codex proposal — a layered, read-only Graph Search Intelligence

My proposed Round-1 position is **Option A as the immediate architecture, with
Option C limited to telemetry for future evidence**. Option B remains an
explicit future ontology decision, not hidden scope in #123.

### End-to-end flow

```text
search expression(s) + optional context
                    |
                    v
          normalize request shape
                    |
                    v
       exact + alias fast-path resolution
                    |
                    v
     candidate population / candidate generation
       |                               |
       | small N                       | larger N
       v                               v
 complete compact index       lexical/FTS + graph features
       |                               |
       +---------------+---------------+
                       v
          contextual semantic selector
                       |
                       v
       candidate-set + live-graph validation
                       |
                       v
 ranked canonical GraphDB entity references
                       |
                       v
       consumer-owned projection / expansion
```

### Internal responsibility split

The engine should have four replaceable roles behind one stable API:

1. **Graph index reader:** returns active canonical identity metadata from a
   read-only graph snapshot.
2. **Candidate generator:** exact/alias plus whole-index or bounded lexical
   candidates.
3. **Semantic selector:** chooses relevant candidates using the search
   expression and optional context. The first implementation is an LLM emitting
   strict JSON.
4. **Authority guard:** validates existence, activity, canonical identity,
   candidate membership, result caps, and telemetry completeness.

Candidate generation and semantic selection must remain separable. This lets
tests establish whether a miss came from poor recall or poor judgment.

### Package and integration boundary

The intelligence must not live only in `compiler`; MCP is already a second
consumer, and the project identifies search as a durable GraphDB capability.

A plausible boundary is a new top-level `kdb_search` package:

- imports `common` for model calling/pool routes;
- imports `kdb_graph` for read-only graph primitives;
- is imported by `compiler` and `kdb_mcp`;
- performs no graph or filesystem product-state writes;
- exposes a stable request/result model plus the engine;
- leaves raw Kuzu query/index primitives in `kdb_graph`;
- requires an explicit update to the AST package-boundary contract before
  implementation.

This placement is a proposal, not a settled package decision. A lower-cost
alternative is to place pure search policy in `kdb_graph.search` and inject a
semantic-selector callable so `kdb_graph` retains zero sibling imports. That
avoids a package initially but forces every consumer to compose the model port.
The blueprint should compare these two placements against the second-consumer
extraction lesson in `docs/JOURNEY.md` §6.

### Controller-style LLM boundary

The LLM owns only semantic selection among controller-supplied candidates.
Python owns:

- candidate identity and metadata;
- graph reads;
- canonical resolution;
- output validation;
- ranking tie-breaks and caps;
- failure handling and fallbacks;
- telemetry persistence at the caller-approved boundary.

The LLM response should be structured JSON and may reference only supplied
candidate slugs. It never emits Kuzu paths, writes Cypher, mutates the graph,
or invents entity identities for this use case.

### Failure behavior

- Exact/alias hits remain available if semantic selection fails.
- A failed selector does not silently promote all lexical candidates to
  relevant results.
- Unknown LLM slugs are typed contract failures.
- Incomplete evidence yields an explicit partial/fallback result.
- The caller decides whether a partial result is acceptable.
- Search telemetry records candidate count, candidate paths, selected count,
  rejected identifiers, model route/stamp, latency, and cost.

## 9. Evaluation proposal

#122's event-time context metrics are necessary downstream measurements, but
they cannot prove relevance. Increasing T2 delivery by returning many irrelevant
entities would look like improvement.

#123 therefore needs a #75-style held-out retrieval truth set defined before
implementation:

```text
fixed graph snapshot
+ search expression
+ optional disambiguating context
→ relevant graph entity set (with acceptable alternatives)
```

Measure at least:

1. candidate recall@\(K\);
2. selected precision@\(K\);
3. selected recall@\(K\);
4. first-relevant rank / MRR or nDCG where ordering matters;
5. person-key probe hit rate for Buffett/Munger/Pabrai-class cases;
6. invalid or fabricated slug rate (required: zero after controller guard);
7. abstention correctness when no relevant entity exists;
8. latency and cost per request/source;
9. fallback and selector-failure rates;
10. downstream #122 T2-seed, T2-delivery, unresolved, and T3-delivery changes.

Candidate-generation truth and selector truth must be reported separately.
Suggested numerical gates should be proposed only after the probe set and
acceptable-alternative rules are visible; otherwise thresholds invite grading
against an undefined target.

Verification should include:

- direct search-engine tests on a fixed graph fixture;
- deterministic candidate-generation tests;
- adversarial LLM-output contract tests;
- context-loader integration with one batched search per source;
- MCP integration against the same engine;
- cold and warm end-to-end sandbox cohorts;
- prompt/cost regression measurement;
- a comparison of whole-index versus FTS-prefilter modes on identical truth.

## 10. Deliberation record

### Initial Codex framing

I initially emphasized that `warren-buffett` cannot be classically
entity-linked to a Buffett node because no such node exists, and asked whether
the graph should eventually contain first-class subject nodes.

### Joseph's correction

Joseph clarified that the starting point is more general: the project needs an
“intelligence entity” that receives a search entity—whatever its
representation—and returns relevant GraphDB entities. The absence of that
intelligence capability precedes questions about particular node kinds or
retrieval mechanisms.

### Resolution

I agree with the correction. Subject nodes and write-side ontology are
downstream architectural alternatives and blind spots, not prerequisites for
the capability definition. This response therefore starts with a
consumer-neutral search contract and evaluates mechanisms beneath it.

## 11. Convergences and open disagreements

### Convergences

- The missing object is intelligent search-to-GraphDB-entity resolution.
- Today's exact-slug matching is a lookup floor, not semantic search.
- Search output must remain graph-authoritative.
- The context loader is the first deployment surface; MCP and CLI are later
  consumers of the same core capability.
- Whole compact-index LLM selection is viable at the current graph size.
- FTS/BM25 is a candidate-generation mechanism, not sufficient relevance
  intelligence.
- LLM outputs must be controller-validated structured references.
- Vectors are unnecessary for v1.
- #122 metrics remain downstream live evidence but require relevance truth to
  prevent “more context” from masquerading as “better context.”

### Open disagreements / decisions for synthesis

1. Should the first semantic stop-gap be whole-index LLM selection, or should
   FTS ship first even though it does not complete the intelligence contract?
2. Is an added batched LLM call per compiled source acceptable, or should the
   selector be folded into an existing pass while preserving the rule that
   source frontmatter remains intrinsic and graph-independent?
3. Should domain be a hard constraint, a soft ranking prior, or a first-shard
   fallback policy?
4. Does the durable capability justify a new `kdb_search` package now, or
   should the initial selector be injected into a sibling-free
   `kdb_graph.search` core?
5. What graph size/cost/latency threshold triggers prefiltered rather than
   whole-index selection?
6. Does #123 remain permanently read-only, with subject/`ABOUT` materialization
   filed separately?
7. What held-out graph snapshot and relevance judgments define “search works”
   before any implementation begins?

## 12. Primary references checked

- [Kuzu full-text-search documentation](https://bighorndb.github.io/docs/extensions/full-text-search/)
  — node-table `STRING` indexes and BM25 query behavior.
- [Kuzu repository and v0.11.3 extension packaging](https://github.com/kuzudb/kuzu)
  — current installed project version and bundled FTS availability.
- [Text2Cypher: Bridging Natural Language and Graph Databases](https://arxiv.org/abs/2412.10064)
  — natural-language-to-structural-query scope and evaluation.
- [CypherBench](https://aclanthology.org/2025.acl-long.438/)
  — execution-grounded text-to-Cypher retrieval evaluation and GraphRAG
  distinctions.
- [A Graph-based Method for Entity Linking](https://aclanthology.org/I11-1113/)
  — entity linking as mapping contextual mentions to candidate knowledge-base
  entries using graph structure.
