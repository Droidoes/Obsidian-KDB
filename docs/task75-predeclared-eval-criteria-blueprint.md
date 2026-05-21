# Task #75 — Predeclared Evaluation Criteria for Step-3 Graph Operations

**Status:** blueprint v2 (2026-05-21) — Codex + Gemini external review applied
(mirrors the Task #74 pre-implementation review pattern). Pending final user
sign-off before Task #75 closure and step-3 implementation kick-off (Task
#76 / #77 / #78+).

**Lineage:** Round 5 §8.5/§8.6 (`docs/what-is-the-ontology-for.md`) named
"predeclared eval criteria for step 3" as a **binding path-forward
precondition** (Codex Q6). This doc is the deliverable that satisfies that
gate.

---

## 0. TL;DR

The Round 5 path forward commits to **B with calibrations (C1 + C2)**: broad
ingestion, LLM-extracted ontology, graph operations as the value-producing
machinery. Codex Q6 (and §8.5/§8.6) made a precondition binding: **define
success/failure tests for the step-3 graph operations BEFORE building them**,
so that we don't slide into "implementation momentum disguised as
empiricism" — i.e., shipping operations and then rationalising whatever they
return as proof the system works.

This blueprint satisfies that precondition by:

1. Locating step 3 in the Round 5 roadmap (§1).
2. Establishing **shared vocabulary** so external reviewers and future Joseph
   can engage with the same grounding (§2 — glossary).
3. Locking the **operations roster** — which graph operations we will build
   at step 3, with rationale for include / defer / skip on each candidate
   (§3).
4. **Predeclaring per-operation success / failure criteria and quantitative
   gate thresholds** (§4) — the actual binding content of the precondition.
5. **Predeclaring hedge-watch rules** — the diagnostic mapping from observed
   step-3 symptoms back to the three §8.3 empirical hedges, so that failure
   has a known reading (§5).
6. Naming step-3 **preconditions** that this blueprint surfaces (§6).
7. Listing **Open Questions for external review** (§7).

Nothing in this doc is code or a code constraint. It is the contract step-3
implementation will be measured against.

**v2 (2026-05-21) — what changed:** Codex + Gemini external reviews
were applied as revisions R1–R8 (see §9 change log). The most material
changes: §4.2 community-routing criteria are now algorithm-neutral
(current code is Louvain only, not Leiden); the §6.1 `domain` blocker
is **narrowed** — only the community/domain-ratio gate depends on it,
not all of step 3; multi-hop is split into V0 existing (`graphdb-kdb
path`) and V2 deferred (scored / explanatory); OQ-8's (a)→(b)→(c)
ladder gains explicit stop conditions (HW-5 lock + iteration ceiling +
post-pivot preservation clause).

---

## 1. Context — where step 3 sits

Per `docs/what-is-the-ontology-for.md` §7.3 + §8, the project's path forward is:

| Step | What | Status |
|---|---|---|
| 1 | Harvester / ingestion (B + X6 mechanical exclusion) | Partial (vault harvester + raw/ namespace; chats / Droidoes-docs harvesters deferred) |
| 2 | Compile pipeline (extraction → reconciliation → **canonicalization**) | **Done** through canonicalization (M1–M4, Task #74) |
| 3 | **Query-time graph operations** (PPR, community routing, …) | **Not started — this is what §8.5/§8.6 demands criteria for** |

Step 3 is the part of the system that justifies a graph over a flat document
store. Until step 3 exists and is exercised, the B-claim
("operations self-partition signal from noise on a broadly-captured corpus")
is untested. Step 3 is where the project's reason-for-being is settled.

Three §8.3 empirical hedges are pre-flagged as plausible failure modes at
step 3 — **scale**, **cross-domain density**, **critical density**. §8.3
explicitly says these are *not* design constraints; they are
diagnostic-only ("watch for these, intervene if observed"). §5 of this
blueprint operationalises that "watch for" instruction.

---

## 2. Glossary

This section exists so external reviewers (Codex, Gemini) start from the
same grounding. Each term names a load-bearing concept used downstream.

### 2.1 "Operation"

A **graph operation** is a computation invoked at *query time* — taking a
seed (one or more entity IDs, or a free-text query) and returning a result
useful to a downstream consumer (a human reader, an LLM answering a
question, an automated workflow).

Distinguish from:

- **Compile-time computations** — things that happen once per source change
  (extraction, canonicalization, edge writes). Not operations.
- **Queries** — the user-facing question. A query is *expressed using* one
  or more operations; an operation is the algorithmic primitive that
  implements part of the query.

### 2.2 "Operations roster"

The **operations roster** is the explicit list of operations we commit to
building at step 3, with disposition (include / defer / skip) and rationale
for each candidate.

Why naming it matters: you cannot predeclare success criteria for an
operation you haven't named. Locking the roster turns "predeclare success
criteria" from a vague directive into a finite, write-able set of
sub-tasks.

### 2.3 "Per-op success / failure criteria"

For each operation in the roster, written *before* building it:

- **Pass test** — a concrete query + the shape of result we'd accept as
  evidence the operation is working. Specific enough to be falsifiable.
- **Fail test** — the failure pattern we expect if the operation
  degenerates. Specific enough that we can recognise it when we see it,
  rather than rationalising it as "kinda worked."
- **Quantitative gate** (where defensible) — the numeric line above which
  we declare the criterion met, below which we either iterate or pivot.

Shape mirrors **Task #19** (compile-pipeline KPI predeclaration that
became `docs/CODEBASE_OVERVIEW.md` §7). Same discipline, applied to
query-time instead of compile-time.

### 2.4 "Hedge-watch rule"

The three §8.3 empirical hedges (scale, cross-domain density, critical
density) are **NOT design constraints**. We do *not* build to avoid them.
§8.3: "if at step 3 you see symptom X, suspect cause Y; otherwise ignore."

A **hedge-watch rule** is a row in a symptom → suspect-hedge table. It tells
us how to *read* failure when it occurs, not how to *prevent* it from
occurring.

### 2.5 "Gate threshold"

The numeric line above which we declare a per-op criterion met. Some
criteria are inherently binary (yes/no); others are graded. A threshold is
defensible when (a) it is measurable and (b) the rationale for picking
*this* number rather than a nearby one is named.

A threshold may be qualitative ("Joseph judges acceptable on ≥ 80% of
probes") when no defensible numeric line exists yet — see OQ-2.

### 2.6 "Probe set"

A small, hand-curated set of `(seed, expected-neighborhood)` mappings used
to evaluate per-op criteria. The probe set is itself a project artefact —
size, curation method, and scoping are open questions (OQ-3).

---

## 3. Operations roster

### 3.1 Candidate operations

| # | Operation | Disposition | Rationale |
|---|---|---|---|
| 1 | **Personalized PageRank (PPR)** | **V1 — include** | The B-justifying primitive from HippoRAG. Tests "operations activate a local neighborhood rather than returning popularity" — the core claim that distinguishes a graph from a flat index. Without PPR we cannot test the B-claim. |
| 2 | **Community routing** (Louvain now; Leiden TBD in #78) | **V1 — include** | The B-justifying primitive from GraphRAG. Tests "communities of the LLM-extracted graph correspond to themes, not just to (C2) domain tags." Without community routing we cannot test the C2 disposition (domain-as-coordinate). Algorithm choice is implementation-scope (§4.2); criteria are algorithm-neutral. |
| 3 | **Typed traversal** | **V0 — already exists** | `graph_context_loader.py` (Tasks #70, #71) is essentially this. Document it as a roster member so the existing capability is part of the step-3 eval surface and benefits from the same predeclared-criteria discipline. |
| 4 | **Subgraph extraction** | **V1 — include** | The retrieval glue between graph operations and any downstream LLM use. PPR / community routing return rankings; LLM synthesis needs the actual subgraph (entities + edges + supporting page text) as context. Cannot be skipped. |
| 5a | **Shortest-path pathfinding** (existing `graphdb-kdb path <from> <to> --max-hops N` — see CODEBASE_OVERVIEW §8.6) | **V0 — already exists** | A directed-shortest-path primitive ships in the CLI today (CODEBASE_OVERVIEW line 414). Treat as a regression-guardrail member of the eval surface (gates: don't regress hop-count or runtime); do NOT re-build. |
| 5b | **Scored / explanatory multi-hop workflow** (semantic-relevance ranking of path nodes; multi-path ranking; LLM-readable path explanation) | **V2 — defer** | Distinct from 5a: answers "*how* are A and B related in a way that's useful to the consumer" — requires scoring intermediate nodes for semantic relevance, ranking multiple paths, and producing consumer-shaped output. Useful but not B-claim-load-bearing. Build only if V1 results justify the extension. |

**V0** = already built and in production. **V1** = build at step 3.
**V2** = defer until V1 gate passes.

### 3.2 Rationale for the V1 cut

The V1 roster is **PPR + community routing + subgraph extraction + (V0)
typed traversal**. The cut tracks the literal B-justifying surface:

- PPR + community routing are **the two operations the Round 5 docs name as
  B-justifying** (HippoRAG / GraphRAG primitives in §6.3 + §7.3). Skipping
  either would leave the B-claim untested.
- Subgraph extraction is non-optional — it is the input contract for any
  LLM-on-graph downstream use, and PPR / community routing without it
  return numbers without text.
- Typed traversal is already in production for compile-time context
  loading; including it in the eval surface ensures we don't regress the
  capability and gives us a third reference point alongside the two new
  ops.
- The shortest-path primitive (5a) is already in production as
  `graphdb-kdb path` — including it in the eval surface protects against
  regression but adds no new build. The *scored / explanatory* multi-hop
  workflow (5b) answers a different question ("how are A and B connected
  in a consumer-useful way") than the B-claim ("does broad ingestion +
  LLM extraction + graph operations produce useful retrieval"); deferring
  it is conservative, not lazy. Note also (per Gemini review): multi-hop
  ranking assumes local-neighborhood containment is already solved by PPR
  — running it before PPR gates pass would fall into the critical-density
  hedge (paths hopping through generic structural hubs and returning
  noise). Sequence is therefore PPR-first, multi-hop-later.

### 3.3 What this roster does *not* commit to

- A specific PPR implementation library (NetworkX vs. native Kuzu vs.
  custom Cypher) — engineering decision for the implementation task.
- A specific community detection algorithm. Louvain is the current
  implementation (`graphdb_kdb/analytics.py`); Leiden adoption is a
  Task #78 implementation-scope decision. The §4.2 criteria are
  algorithm-neutral — they read off the partition, not the algorithm
  that produced it.
- A specific subgraph-extraction serialization format.
- A specific number of operations beyond the V1 four — V2 multi-hop is
  reopen-able.

---

## 4. Per-op predeclared criteria

For each V1 operation: pass test, fail test, quantitative gate. **All
thresholds are v1 proposals** — see OQ-2 for the threshold-defensibility
question.

### 4.1 PPR — Personalized PageRank

**Operation contract**
- Input: seed entity set (≥ 1 canonical-entity slug; *not* the
  `Entity.canonical_id` foreign-key column, which is the alias→canonical
  pointer and is NULL on canonical entities — see `graphdb_kdb/schema.py`
  + Task #74 D-R5-13), damping factor α (default 0.15), iteration cap
  (default 50).
- Output: ranked list of entities with PPR scores, descending.

**Pass test**
- For a seed query whose expected neighborhood we can name by inspection
  (e.g., seed = `value-investing` → expected neighborhood includes
  `margin-of-safety`, `intrinsic-value`, `buffett` — placeholder names; the
  actual probe set is OQ-3):
  - Top-5 results include **≥ 3 of the expected-neighborhood entities**
    for the seed.
  - Top-5 **changes meaningfully** when the seed changes (i.e., results
    are seed-dependent, not popularity).

**Fail test (degenerate patterns)**
- "**Popularity collapse**": top-5 results are nearly identical regardless
  of seed (operation is returning global PageRank disguised as PPR).
- "**Hub dominance**": top-5 is dominated by the highest-degree nodes
  irrespective of seed proximity.
- "**Empty neighborhood**": top-5 contains no entities matching the seed's
  human-judged neighborhood (operation is finding "nothing nearby").

**Quantitative gates**
- **Recall**: top-10 recall ≥ **0.5** against the probe set (OQ-3).
- **Seed sensitivity**: pairwise overlap of top-5 results between two
  different seeds **≤ 50%** averaged across probe pairs (proves seed
  dependence).
- **Hub guard**: highest-degree **structural / systemic hub** in the
  graph appears in top-5 results in **≤ 30%** of probe seeds (proves PPR
  is local, not popularity-biased). *Scope clarifier:* "structural /
  systemic hub" = entities representing file-type / temporal / generic
  scaffolding nodes (e.g., a generic `page` or `daily-note` concept,
  date-tag nodes). It does **NOT** apply to legitimately high-degree
  **semantic** hubs whose frequent surfacing is correct (e.g.,
  `buffett` in an investing-domain query) — those should *not* be
  guarded against. Probe set (OQ-3) names which entities are
  structural for hub-guard scoring purposes.

### 4.2 Community routing (algorithm-neutral)

**Note on current vs target algorithm.** As of 2026-05-21 the codebase
implements **Louvain** only (`graphdb_kdb/analytics.py:86` —
`raise ValueError("unsupported community algorithm")` for any non-Louvain
choice; `tests/test_analytics.py:136` enforces this contract). The
predeclared criteria below are intentionally **algorithm-neutral**:
modularity is conserved under both Louvain and Leiden, and the
community-count / max-share / domain-ratio gates are read off the
partition regardless of which algorithm produced it. Adoption of
Leiden + a SUPPORTS-projected (rather than LINKS_TO-only) graph is an
**implementation-scope decision for Task #78**, not a precondition this
blueprint commits to.

**Operation contract**
- Pre-compute: community detection over the entity-entity edge subgraph.
  - *Algorithm:* Louvain (current) or Leiden (Task #78 may swap).
  - *Edge basis:* LINKS_TO only (current) or LINKS_TO + SUPPORTS-projected
    (Task #78 may extend).
  - *Resolution parameter:* tunable; see resolution-tuning note below.
- Input (per query): free-text query OR seed entity set.
- Output: ranked list of `(community_id, routing_score)` pairs; optionally
  within-top-community retrieval results.

**Resolution-tuning note (personal-scale realism).** At personal-corpus
scale (~70 canonical entities as of 2026-05-21), out-of-the-box
community-detection parameters will almost certainly collapse the graph
into 2–3 mega-clusters — which fails the community/domain-ratio gate
trivially. Achieving the §4.2 gates **requires active resolution-parameter
tuning as part of Task #78 setup** (not as a separate research task). The
gate is the destination; tuning is the path. If after reasonable tuning
the gates still fail, HW-4 (single-blob) and HW-5 (scale) fire — that's
diagnostic information, not a tuning failure.

**Pass test**
- For a probe query with a clearly-themed answer ("What do I know about
  stoic philosophy?"), the **top-1 community is human-recognisable as
  the right theme** (i.e., its top entities + page samples match the
  query's intent).
- **Community count > distinct-domain count** — communities are *not*
  1:1 with `domain` tag values (see §6 — depends on `domain` field
  shipping).
- Within a single domain, **≥ 2 communities exist** for at least one
  domain in the corpus (proves communities split themes within domains,
  the C2 claim).

**Fail test (degenerate patterns)**
- "**Routing collapse**": top-1 community is the same regardless of
  query — routing is not actually routing.
- "**Domain re-discovery**": communities map 1:1 to `domain` tag
  values — the LLM-extracted graph hasn't learned anything that the
  domain tagging didn't already encode. This is the
  cross-domain-density hedge firing.
- "**Single-blob community**": one community contains >50% of all
  entities — resolution parameter is too coarse, or the graph is too
  dense for community structure to exist at this scale.

**Quantitative gates**
- **Human-judged routing match**: for ≥ **70%** of probe queries, the
  top-1 community matches Joseph's intuition about the query's theme.
- **Community / domain ratio**: `n_communities ≥ 1.5 × n_distinct_domains`.
- **Community size distribution**: no single community exceeds 50% of
  entity count.

### 4.3 Typed traversal (V0 — query-time neighbors / BFS)

**Scope clarifier (Codex P2.5).** §2.1 defined an "operation" as
query-time. The query-time typed-traversal surface today is the
`graphdb-kdb neighbors <slug> [--depth N] [--direction]` /
`graphdb-kdb incoming <slug>` CLI (CODEBASE_OVERVIEW §8.6 lines
411–413) — a BFS expansion with edge-direction filtering. That is the
primitive this section predeclares against.

The compile-time `graph_context_loader.py` consumer (Tasks #70 / #71)
exercises the **same underlying graph traversal** at compile time
(seed → typed-neighbor expansion with depth/cap). It is included as a
**regression guardrail** below — not as the operation under test, but as
proof that any future change to the traversal primitive does not
regress the compile-time consumer that depends on it. (Task #73 removed
manifest-as-ontology; the manifest-parity guardrail from v1 of this
blueprint no longer applies and has been dropped.)

**Operation contract**
- Input: seed entity slug + depth limit + (optional) edge-type filter +
  direction (out / in / undirected).
- Output: connected subgraph (entities + edges) reachable within depth
  under the filters.

**Pass test**
- For a probe seed with a known small neighborhood (depth=1), the
  returned entity set matches the expected neighborhood by inspection.
- For depth=2, the returned set is a superset of depth=1 and includes
  the expected second-hop entities.
- Directional filters work — `--direction in` returns only incoming
  neighbors.

**Fail test**
- Returned set is empty for a seed with known SUPPORTS / LINKS_TO edges
  (traversal broken).
- Returned set ignores `--direction` filter (filter broken).
- Edge-type filter passes through edges of disallowed types
  (filter broken).

**Quantitative gates**
- **Probe-set correctness**: for ≥ **95%** of probe seeds, depth=1
  neighbor set matches expected (exact set match).
- **Regression guardrail (compile-time consumer):** production
  `kdb-compile` continues to produce the same compile output (binary
  parity at `compile_result.json` level for unchanged sources), and
  cold-start widening (Task #71) still produces ≥ 5 seeds for new
  sources with empty SUPPORTS edges.

(Typed traversal is included in the roster as both a query-time
operation in its own right *and* a regression guardrail for the
compile-time consumer that depends on the same primitive.)

### 4.4 Subgraph extraction

**Operation contract**
- Input: seed entity set + neighborhood spec (max hops, max nodes,
  edge-type filter, max tokens).
- Output: serialized subgraph — entities (with canonical names + domain +
  page samples), edges (with type), supporting page text — sized to fit
  the requested token budget.

**Pass test**
- For a probe seed, the extracted subgraph **contains the entities and
  pages a human would expect** when asked "tell me about <seed>" — both
  presence (no obvious omissions) and absence (no obvious bloat).
- Extracted subgraph **fits the requested token budget**.

**Fail test**
- "**Under-extraction**": extraction misses obviously-related connected
  pages (probe-set false negatives).
- "**Over-extraction**": extraction overflows the token budget on the
  canonical 5-source corpus (neighborhood spec too loose).
- "**Empty extraction**": seed yields zero pages despite having SUPPORTS
  edges (operation broken).

**Quantitative gates**
- **Token-budget hit rate**: ≥ **95%** of probe extractions stay within
  the requested budget (allowing a small over-shoot tail for
  hard-to-trim cases).
- **Qualitative completeness**: Joseph judges ≥ **80%** of probe-seed
  extractions as "complete and not bloated."
- **Empty-output rate**: 0% for seeds with ≥ 1 SUPPORTS edge.

---

## 5. Hedge-watch rules

§8.3 says the three empirical hedges (scale, cross-domain density,
critical density) are diagnostic-only. This section is the symptom →
suspect-hedge mapping.

| # | Symptom observed at step 3 | Suspect hedge | Disposition |
|---|---|---|---|
| HW-1 | PPR top-N is ~identical across seeds (popularity collapse, §4.1 fail test) | **Critical density** | Investigate graph density metrics (avg degree, max degree, clustering coefficient). If confirmed: consider PPR with degree-normalised damping, or sub-domain partitioning. Do not redesign the graph schema. |
| HW-2 | PPR top-N dominated by hub nodes irrespective of seed (hub dominance, §4.1 fail test) | **Critical density** | Same as HW-1; specifically points at hub-node remediation (degree-cap on walk transitions). |
| HW-3 | Community count = distinct-`domain` count, or communities map 1:1 to domains (domain re-discovery, §4.2 fail test) | **Cross-domain density** | Communities are rediscovering the (C2) `domain` attribute, not extracting themes. Tune resolution parameter downward (more, smaller communities). If still degenerate after tuning: domain-stratified community detection (separate run per domain). |
| HW-4 | One community contains > 50% of entities (single-blob community, §4.2 fail test) | **Critical density** | Same intuition as HW-1/HW-2 — graph is too connected for community structure to crystallise at this resolution. Tune resolution parameter upward first. |
| HW-5 | Probe queries return low recall (top-10 < 0.3) across multiple operations | **Scale** | Corpus is too small for the B-claim to hold yet. This is **not** a B-claim refutation — it is an n-too-low signal. Continue corpus growth; revisit gates after the next significant ingestion increment. |
| HW-6 | PPR gate passes but downstream LLM synthesis from subgraph extraction is incoherent | **Not a hedge — different failure mode** | Investigate subgraph-extraction completeness (§4.4) OR downstream prompt OR LLM choice. Do not attribute to hedges. |
| HW-7 | Per-op gates pass individually but composed query results (PPR → subgraph → LLM) are subjectively unhelpful | **Possible scale OR composition issue** | Trigger probe-set expansion (OQ-3) and / or compose-level criteria conversation (OQ-6). |

**Disposition philosophy** (per §8.3): rules describe how to *read* failure,
not how to *prevent* failure. When a hedge fires, the response is **named
investigation**, not panic redesign.

---

## 6. Step-3 preconditions surfaced by this blueprint

Writing the predeclared criteria surfaced two **preconditions that must
ship before step-3 implementation starts** (not the predeclared-criteria
gate itself — these are separate):

### 6.1 `domain` field on Page nodes (Round 5 §7.3 "compilation contract amendment")

Round 5 §7.3 named "compilation contract amendment — pages gain
LLM-extracted `domain` (and optional `sub_domain`) field. … Graph schema
picks up a `Domain` node and `BELONGS_TO` edge (or equivalent — to be
decided in implementation)."

This was named as a Round-5 unblock but **has not shipped**. Grep
confirms: no `domain` field in `kdb_compiler/schemas/`, no `Domain` node
or `BELONGS_TO` in `graphdb_kdb/schema.py` (as of 2026-05-21).

**Scope of blocker (Codex P1.1 — narrowed from v1).** Only the
**community/domain-ratio gate** in §4.2 (`n_communities ≥ 1.5 ×
n_distinct_domains`) and §5 hedge-watch rule **HW-3** (domain
re-discovery) require the `domain` field. The other Step-3 work
streams can proceed **in parallel**:

- **PPR (§4.1)** — depends only on entities + LINKS_TO / SUPPORTS edges,
  which exist. No dependency on `domain`.
- **Subgraph extraction (§4.4)** — depends on entities + edges + page
  text. No dependency on `domain`.
- **Typed traversal V0 regression (§4.3)** — depends on existing
  primitive. No dependency on `domain`.
- **Probe-set curation (§6.2 / OQ-3 / Task #77)** — can start
  independently. The probe set itself may reference `domain` once that
  ships, but its curation does not block on it.

The narrowed claim: **the community/domain-ratio acceptance gate
cannot close until the `domain` field ships.** Step-3 implementation
as a whole is not blocked.

**Action:** file as a successor task (likely Task #76 — "Implement
Round 5 `domain` field + `Domain` node + `BELONGS_TO` edge"). Out of
scope for #75; required before the community/domain-ratio gate can be
declared green.

### 6.2 Probe set (OQ-3)

The §4 criteria assume a probe set of `(seed, expected-neighborhood)`
mappings exists. Without it, the recall / sensitivity / human-judged-match
gates are not measurable.

**Action:** file as a successor task (likely Task #77 — "Curate step-3
probe set"). The size, scope, and curation method are OQ-3 below.

---

## 7. Open Questions for external review (Codex + Gemini)

External reviewer note: the goal is to pressure-test the criteria, not the
roster's overall direction (which is locked by §8.5/§8.6 + the user's call
to proceed with (i)). Codex review-only guardrail applies; Gemini should
stay in review mode and not propose implementations.

**OQ-1. Roster completeness.** Is the V1 roster (PPR + community routing +
typed traversal V0 + subgraph extraction) sufficient to test the B-claim
at personal-corpus scale? What's missing? Should multi-hop pathfinding be
promoted from V2 to V1, given that "how are A and B related" might be a
core personal-corpus question?

**OQ-2. Gate-threshold defensibility.** Are the proposed numeric
thresholds (top-10 recall ≥ 0.5, top-5 seed sensitivity ≤ 50% overlap,
community routing match ≥ 70%, community / domain ratio ≥ 1.5,
extraction qualitative ≥ 80%) defensible for personal-scale (~70-entity)
corpora? Or should every threshold be qualitative ("Joseph judges
acceptable") until a baseline run establishes what numbers are achievable
on this corpus?

**OQ-3. Probe set scoping.** This blueprint assumes a curated probe set
exists.
- How many `(seed, expected-neighborhood)` mappings? (Task #19 had 5
  source documents; what's the right N here?)
- Who curates — Joseph alone, Joseph + LLM-assisted, or some triangulation?
- When — before step-3 implementation starts (blocking), or in parallel
  (non-blocking)?
- Is the probe set itself versioned and committed under `benchmark/`
  alongside the existing 5-source corpus?

**OQ-4. Hedge-watch playbooks.** The §5 table is symptom → suspect-hedge.
Each rule's "disposition" column gestures at remediation but does not
specify a full playbook. Should each watch rule include explicit "if
symptom fires, run *this* diagnostic test next" guidance? Or does
§8.3-spirit ("name it and watch for it; don't design against it") mean
the disposition column is intentionally light?

**OQ-5. Sequencing (revised v2 — Codex P1.1 narrowing).** With the
domain-blocker scope narrowed (§6.1), the proposed flow becomes
**fully parallel** rather than serial:

```
#75 (this blueprint, landed)
   ↓
   ┌─────────────────────────────────────────────────────────┐
   │ #76 (domain field)         all parallel                 │
   │ #77 (probe set)            no blocking dependency       │
   │ #78 (PPR impl)             between any pair             │
   │ #78b (subgraph extr impl)                               │
   │ #78c (typed traversal V0 regression suite formalised)   │
   └─────────────────────────────────────────────────────────┘
       ↓
   Community/domain-ratio acceptance gate (§4.2) closes
   only after #76 + #78 are both in.
```

Open: should #76 (domain field) actually have been a step-2
(compile-pipeline) follow-up that should have shipped already and
unblock step 3 mechanically, rather than being treated as a step-3
sibling?

**OQ-6. Composition criteria.** Each operation has individual criteria but
step 3 in practice composes them (e.g., PPR seeds → subgraph extraction →
LLM synthesis). Do we need explicit composition-level criteria, or do
per-op gates plus a downstream "useful answer" subjective check suffice?
The Task #19 / kdb-benchmark precedent is "score primitives + a final
weighted score" — should we mirror that here, or is step 3 too
conceptual-output-shaped for a weighted-final-score?

**OQ-7. Re-baseline policy.** The Task #19 precedent (D29.9): when the
underlying measure definition changes, cross-generation final scores
become incomparable. Step 3 will likely refine its criteria as evidence
accumulates. Should this blueprint pre-commit to a re-baseline policy —
e.g., "each criterion-definition change invalidates prior probe-set
results and a fresh probe-set run is required"?

**OQ-8. Failure-to-pass disposition.** If the §4 gates fail after
implementation, the project response is the **bounded (a)→(b)→(c)
ladder** below. Codex flagged this exact risk in Q6 ("implementation
momentum disguised as empiricism") — naming the ladder up-front, with
explicit stop conditions, is part of avoiding it.

**The ladder:**

- (a) **Iterate on the operation** (tune parameters, change library, try
  alternate algorithm) until gates pass.
- (b) **Iterate on the corpus** (grow it, partition it, re-canonicalise
  it) until gates pass.
- (c) **Revisit the B-claim** — if gates persistently fail despite (a)
  and (b), the B-claim is empirically refuted and the project pivots
  to an A-flavoured variant (per §8.5 narrowing of [8]).

**Stop conditions (Codex + Gemini v2 additions):**

1. **HW-5 (scale hedge) lock.** If HW-5 fires — i.e., low recall is
   diagnosed as an n-too-low signal — the ladder is **locked at state
   (b)**: continue corpus growth. State **(c) is forbidden while HW-5
   is active.** Philosophy B is a statistical claim about a sufficiently
   dense corpus; it cannot be refuted on an N too low to support
   density. (Concretely: if `n_canonical_entities < some-threshold`, (c)
   is off the table — the threshold itself is OQ-9.)
2. **Iteration ceiling.** To prevent infinite parameter tuning (a) or
   infinite corpus reshaping (b), pre-commit to a hard ceiling:
   - **State (a) ceiling:** ≤ **2** parameter-tuning cycles per
     operation (e.g., resolution scaling, damping factors, transition
     weights).
   - **State (b) ceiling:** ≤ **1** corpus ingestion / canonicalisation
     expansion cycle.
   - If gates remain red after these ceilings, the transition to (c) is
     triggered automatically (subject to the HW-5 lock above).
   - **These specific numbers are provisional — see OQ-9.**
3. **Post-pivot preservation clause (state (c) reality).** If (c)
   triggers and the B-claim is refuted, the work in **Step 1
   (Harvesters)** and **Step 2 (Canonicalization Engine)** is
   *preserved*, not discarded. The pivot affects only **query-time
   context assembly** — replacing stochastic graph operations with
   schema-constrained, human-approved retrieval paths (the A-flavoured
   variant per §8.5). The ingestion and canonicalisation infrastructure
   is the same under either philosophy; only the consumer of the
   resulting graph changes.

**Project commitment:** the project commits to the ladder above with
its stop conditions. (a) is tried first per operation, (b) follows if
(a) ceiling hits and HW-5 is *not* active, (c) follows if both ceilings
hit and HW-5 is *not* active. HW-5 active ⇒ stay in (b).

**OQ-9. Iteration-ceiling values and HW-5 lock threshold.** The
ceilings in OQ-8 ((a) ≤ 2 cycles, (b) ≤ 1 cycle) and the HW-5 lock
threshold ("if `n_canonical_entities < X`, state (c) is forbidden")
are **provisional** — defensible but not derived from prior data. Plan
to revisit after the first step-3 run produces evidence on how many
tuning cycles actually move the needle for each operation, and what
corpus size starts to make recall gates achievable. **Disposition:**
adopt the v2 provisional values; on Task #78's post-run debrief,
re-evaluate and either confirm or revise. Do not block #75 closure on
this.

---

## 8. References

- `docs/what-is-the-ontology-for.md` — §7.3 (Round 5 position), §8.1
  (path forward = B), §8.3 (hedge disposition), §8.4 (5-layer selection
  vocabulary), **§8.5 (final position summary)**, **§8.6 (consultation
  concluded — predeclared eval criteria adopted as path-forward
  precondition)**.
- `docs/CODEBASE_OVERVIEW.md` §7 — Task #19 KPI predeclaration (the
  pattern this doc mirrors).
- `docs/task74-canonicalization-blueprint.md` — Task #74 blueprint
  format precedent (Codex 2-round + Gemini 2-round review pattern).
- `docs/TASKS.md` — canonical project task ledger; Task #75 entry to be
  added on landing.
- HippoRAG paper — PPR primitive reference.
- GraphRAG paper — community-routing primitive reference.

---

## 9. Change log

- **v1 (2026-05-21):** initial draft. Roster, per-op criteria, hedge-watch
  rules, preconditions, OQs. Awaiting Codex + Gemini external review.
- **v2 (2026-05-21):** Codex + Gemini external review applied. Eight
  revisions:
  - **R1** (Codex P1.2): §4.2 community-routing criteria made
    **algorithm-neutral**. Current code is Louvain only
    (`graphdb_kdb/analytics.py:86` rejects non-Louvain); blueprint v1's
    Leiden + SUPPORTS-projection assumptions were unimplementable. Leiden
    adoption + SUPPORTS-projection moved to Task #78 implementation
    scope. §3.1 roster entry, §3.3 non-commitments, §4.2 heading +
    contract, HW-3 / HW-4 dispositions all reworded.
  - **R2** (Codex P1.1): §6.1 `domain` blocker **narrowed**. Only the
    community/domain-ratio gate (§4.2) and HW-3 (§5) require `domain`.
    PPR (§4.1), subgraph extraction (§4.4), typed traversal regression
    (§4.3), and probe-set curation can proceed in parallel. OQ-5
    sequencing diagram updated to a fully parallel flow.
  - **R3** (Codex P2.3): §4.1 PPR contract changed "canonical_id" →
    "canonical entity slug". `Entity.canonical_id` is the alias→canonical
    foreign-key pointer (NULL on canonicals); the PPR seed identifier is
    the canonical entity's `slug` (per `graphdb_kdb/schema.py` + Task
    #74 D-R5-13).
  - **R4** (Codex P2.4): §3.1 multi-hop entry **split**. Row 5a =
    shortest-path V0 (already exists as `graphdb-kdb path`, treated as
    regression guardrail). Row 5b = scored / explanatory multi-hop
    workflow V2 (defer). §3.2 rationale and OQ-1 framing adjusted.
  - **R5** (Codex P2.5): §4.3 typed traversal **recast as query-time
    primitive** (`graphdb-kdb neighbors` / `incoming` BFS). Manifest-parity
    fail test dropped (Task #73 removed manifest-as-ontology). Compile-time
    consumer (`graph_context_loader.py`, Tasks #70 / #71) retained as a
    regression guardrail, not as the operation under test.
  - **R6** (Codex + Gemini): OQ-8 (a)→(b)→(c) ladder gained three
    explicit stop conditions: HW-5 (scale hedge) lock, iteration ceiling
    ((a) ≤ 2, (b) ≤ 1), post-pivot preservation clause (Step 1 + Step 2
    survive a pivot; only query-time context assembly changes). Project
    commitment statement added.
  - **R7** (Gemini): §4.1 Hub Guard scope clarified — applies to
    structural / systemic hubs (file-type, temporal, generic-concept
    nodes), NOT legitimate semantic hubs (e.g., `buffett` in an
    investing query).
  - **R8** (Gemini): §4.2 resolution-tuning realism note added — at
    ~70-entity personal scale, out-of-the-box community-detection
    parameters will collapse to 2–3 mega-clusters; active resolution
    tuning is required as part of Task #78 setup, not as a separate
    research task.
  - **OQ-9 (new):** iteration-ceiling values (2 / 1) and HW-5 lock
    threshold flagged as provisional; revisit after Task #78 post-run
    debrief. Does not block #75 closure.
  - **Status:** Codex + Gemini review cycle complete. Pending final
    user sign-off before Task #75 closure.
