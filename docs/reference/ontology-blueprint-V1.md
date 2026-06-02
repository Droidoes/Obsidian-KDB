# Ontology Blueprint V1 — GraphDB-KDB Meaning Layer

**Status:** **v0.2 — RATIFIED** (5-model panel reviewed + Joseph ratified 2026-05-31).
The three decisions are resolved; see § Ratification. §5–7 retain the original
briefs as the rationale/audit trail.
**Date:** 2026-05-31
**Role in the doc stack:** the **MEANING layer** — what the graph's nodes and
edges *mean*, why each exists, and which objective each serves. Companion to:

| Layer | Doc | Question |
|---|---|---|
| WHY | [`what-is-ontology-for-V1.md`](what-is-ontology-for-V1.md) (+ V1.1 ladder) | What is the ontology *for*? |
| **MEANING** | **this doc** | What does the graph *mean*? |
| HOW | [`reference/task-graphdb-kdb-blueprint.md`](reference/task-graphdb-kdb-blueprint.md) + Pass-2 schema + T2/T3 | How is it built? |

`what-is-ontology-for-V1.md` and this blueprint are the two **foundational
documents** of the project. This doc does **not** re-open the settled philosophy
(Philosophy B; domain-as-coordinate-not-gate; the capability verdict) — it
applies it to a concrete node/edge inventory and surfaces three decisions
(ratified in v0.2 below).

---

## Ratification (v0.2 — 2026-05-31)

Reviewed by a 5-model chat-app panel (Codex, DeepSeek, Gemini, Grok, Qwen;
responses in `docs/ontology-blueprint-V1-review-<model>.md`), synthesized, and
ratified by Joseph. Convergence tally and outcomes:

**D1 — Domain model → A (5/5 unanimous, high confidence). RATIFIED.**
Derive `Entity BELONGS_TO Domain` from `Source.domain` + `SUPPORTS`; drop the
Pass-2 per-page LLM `domain`. Folded refinements:
- **`support_count`** stored on each derived edge (recomputable aggregate, *not* a
  denormalized source-id ledger — recover the "which sources" list via the
  `SUPPORTS` join). Powers D3 weighting + hub filtering. (`via_source` sub-Q → count only.)
- **`sub_domain` retired** (5/5 — no producer under D1-A).
- **`BELONGS_TO` documented as *attested* membership** ("evidenced by ≥1 source whose
  domain is D"), not intrinsic taxonomy. Inheritance is a feature.
- **Hub-pollution** (3/5 — hubs inherit many domains → coordinate dilution) is
  mitigated by `support_count` as a filterable strength signal; **no hard threshold**.
- Pass-2 **stops emitting** `domain` (removed from the prompt, not merely ignored).
- **Release: 0.5.0.**

**D2 — Claim layer → DEFERRED to Release 2.0. RATIFIED.**
The major-version boundary is the ¶419 / Learn line. The whole Claim apparatus —
`Claim` + `EVIDENCES` + `ABOUT`, the offline extraction pilot, *and* the panel's
load-bearing requirement of a controlled small (~5–10) **domain-general
`PredicateClass` registry**, plus the schema trims (drop `predicate_scope_slugs`,
`confidence_spread`; add `ABOUT` role) — all move to **2.0**. `Claim` + its 5 edges
stay in the schema as designed-but-unwired. The live pipeline (0.5–1.0) stays
Remember+Relate. *(Panel leaned 4×C / 1×B; deferring to a named major release is
the cleaner expression of "earn the ¶419 bet with evidence first.")*

**D3 — T2/T3 domain-scoping → C stance + refined variant D. RATIFIED.**
Domain is a retrieval **coordinate, not a gate** (5/5 reject hard gate). Implementation:
- **T3 neighbor-expansion stays OPEN** (4/5 — where cross-domain Discover lives).
- **T2:** same-domain weighted, **but exact `entity_search_key` matches search
  globally** (legit cross-domain bridges); only *fuzzy* matches are same-domain-heavy.
- **~70/30** same/cross-domain budget; **instrument** same/cross-domain context share.
- **Hub-suppression** (degree-based) noted as an orthogonal companion axis (deferred).
- Stance ratified here; exact weighting **algorithm → the consumer (T2/T3) sub-project**.
- **Release: 0.5.0** (stance) → tuned in 0.5–1.x.

> **OVERRIDE 2026-05-31 (Joseph) — C → hard same-domain gate.** During the consumer
> sub-project, Joseph overrode C to a **hard same-domain gate**: T2 + T3 pull existing
> entities **only** from the source's Pass-1 domain; no cross-domain in the compile
> context; no ~70/30 budget, no cross-domain weighting, no exact-T2-global. Rationale:
> the panel conflated **context-scoping** (anti-entropy — should be same-domain) with
> **link-creation** (unconstrained, still the LLM's call) and **Discover** (future,
> query-time, whole-graph). The gate touches only context-scoping, so the panel's
> Discover objection does not bite. Priority: full same-domain context > short/empty
> same-domain context > off-domain-padded context. Spec:
> `docs/superpowers/specs/2026-05-31-t2-t3-domain-scoping-design.md`.

**Downstream sequence (→ 0.5.0):** producer (Pass-2) rebuild implementing D1 →
consumer (T2/T3) implementing D3 → stdout messaging → **run-4** (the 0.5.0 gate).
Releases per `docs/ROADMAP.md`.

---

## 0. How to review this document (panel instructions)

You are one of several independent reviewers (chat apps — Codex, DeepSeek, Qwen,
Gemini, Grok). You have **no repo access**; everything you need is inline,
including the current schema DDL (Appendix A) and the load-bearing source
excerpts (Appendix B). The settled frame in §1 is **not up for debate** — treat
it as ground truth and reason *within* it.

We ask for your take on the **three decisions** (§5 D1 · §6 D2 · §7 D3). For
each: which option, why, what we missed, and any failure mode our framing
under-weights. The assistant's lean is stated in each brief — challenge it.

**Guardrail:** produce your review as text only. Do not assume or request
filesystem/repo access; do not propose edits to any file. This is a reasoning
task, not a coding task.

---

## 1. The settled frame (ground truth — do not re-open)

KDB compiles raw text into a **knowledge graph** (Kuzu). The graph — not the
Obsidian wiki rendering — is the durable, queryable system.

**Philosophy B** (resolved across Rounds 4–6 of `what-is-ontology-for-V1.md`):
ingest broadly (the human's act of saving to the vault is a sufficient filter);
extract entities/relations/domains with an LLM, not a human-declared schema;
let the graph's own operations partition signal from noise at query time. No
value/relevance gate at ingestion.

**The five-rung objective ladder (V1.1, 2026-05-31)** — KDB as a second brain,
by expanding epistemic boundary:

| Rung | Capability | Verdict |
|---|---|---|
| **Remember** | recall what KDB holds | solid |
| **Relate** | traverse the explicit edges connecting what KDB holds | solid; quality bounded by edge-vocabulary richness (¶419) |
| **Learn** | KDB's own state evolves as evidence arrives | solid, designed (Round 6: #83/#84/#85/#86) |
| **Discover** | surface knowledge that *exists* but is *not yet in KDB* | aspirational, scale-bounded (¶407) |
| **Create** | invent knowledge that exists *nowhere* | aspirational frontier (¶413; collaborative) |

**Two ratified constraints this blueprint must honor:**

- **(C2) Domain = coordinate, not gate.** Domain may filter/partition *at query
  time*; it must never gate what is ingested.
- **¶419 — the live tension.** "Everything powerful draws its power from
  **typed** entities + a **controlled relationship vocabulary**." A
  domain-general, single-edge-type graph risks being one you can *traverse but
  not reason over.* (Full quote: Appendix B.)

---

## 2. Why this blueprint exists now — run-3 evidence

Run-3 (2026-05-30, first clean end-to-end run): 36 sources scanned · 29
compiled · 7 noise. Resulting graph: **178 Entity · 29 Source · 4 Domain ·
0 Claim**; **439 LINKS_TO · 185 SUPPORTS · 29 BELONGS_TO · 0 of the 5 Claim
edges.**

A load-bearing fact for D1, **verified directly against the run-3 graph**: all
**29/29 Source nodes already carry a `domain` property** spanning the full
11-value Pass-1 distribution (`value-investing` 9, `software` 7, `ai-ml` 4, …).
The reliable per-source classification is *present in the graph today*; it is
simply never propagated to entities. Two facts triggered this review:

1. **Domain coverage failure.** Only **24 of 147 concept pages (16%)** carry any
   domain, and across the whole run Pass-2 emitted just **4 distinct domain
   values** (`software`, `personal-finance`, `math-statistics-logic`, `ai-ml`).
   Pass-1, by contrast, classified the same corpus into **11 domains** —
   including **`value-investing` (9 sources, its largest bucket)**, which Pass-2
   **never emitted**, so the entire investing cluster floats with no Domain
   node. Root cause: domain is emitted per-page by the Pass-2 LLM (a leftover of
   the original one-pass compiler), which under-emits; the reliable per-source
   Pass-1 classification is not propagated. → **D1.**
2. **100% generic edges.** Every edge in the graph is `LINKS_TO`/`SUPPORTS`. The
   typed `Claim` layer (schema v2.2) is defined but never produced. The graph
   can be traversed but not reasoned over — ¶419, observed. → **D2.**

---

## 3. Node inventory

| Node | Definition (one line) | Serves | Status |
|---|---|---|---|
| **Source** | an ingested document; the provenance root | Remember | keep |
| **Entity** | a canonical concept/article/summary page; recall unit + traversal hub | Remember, Relate | keep |
| **Domain** | a knowledge domain (Pass-1 controlled vocab) | Relate (coordinate) | **D1** |
| **Claim** | a typed assertion (subject·predicate·object·polarity·modality·state) | Relate, Learn | **D2** |

**Source** — *Definition:* one row per ingested document (PK `source_id`), with
intrinsic metadata (`source_type`, `domain`, `summary`, `author`, `hash`,
`ingest_state`). *Rationale:* every claim/entity must trace to where it came
from — provenance and auditability are load-bearing under B (the LLM is not a
neutral extractor; its output must be revisable and source-linked — Codex's C1
caveat). *Exploit:* "what sources discuss X"; trust/recency weighting;
re-compile on `hash` change; **the carrier of the authoritative Pass-1
`domain`.** *Status:* keep unchanged.

**Entity** — *Definition:* a canonical page (PK `slug`), `page_type ∈ {summary,
concept, article}`, with `canonical_id` pointing alias forms to their canonical
node. *Rationale:* knowledge decomposed into addressable concepts that many
sources co-reference; canonicalization prevents the "word-soup" failure mode
(`Apple Inc.` ≠ `AAPL` — Antigravity's central concern). *Exploit:* associative
recall (PPR); neighbor traversal; the Obsidian wiki rendering. *Status:* keep.

**Domain** — *Definition:* a knowledge domain (PK `name`) drawn from the Pass-1
controlled vocabulary (`config/domains.json`, 21 values). *Rationale:* a
**coordinate** to partition and navigate the graph (never an ingestion gate).
*Exploit:* "everything in value-investing"; domain-scoped Discover; D3 retrieval
weighting. *Status:* **D1** — how it is populated and what `BELONGS_TO` means.

**Claim** — *Definition:* a typed assertion: `subject_slug`,
`predicate_class`, `object_slugs[]`, `polarity`, `modality`, `condition_text`,
`assertion_text`, `confidence`, `state`, `version` (full DDL Appendix A).
*Rationale:* the **typed relationship vocabulary** that moves Relate from
traverse → *reason*, and the substrate for **Learn** (belief revision). The
direct answer to ¶419. *Exploit:* "what does source S assert about entity E";
contradiction detection; belief versioning. *Status:* **D2** — wire into the
live pipeline, or keep deferred.

---

## 4. Edge inventory

| Edge | Endpoints | Serves | Status |
|---|---|---|---|
| **SUPPORTS** | Source → Entity | Remember (provenance), Relate | keep |
| **LINKS_TO** | Entity → Entity | Relate | keep — but *generic* (¶419) |
| **ALIAS_OF** | Entity → Entity | Remember (canonicalization) | keep |
| **BELONGS_TO** | Entity → Domain | Relate (coordinate) | **D1** |
| **EVIDENCES** | Source → Claim | Relate, Learn | **D2** |
| **ABOUT** | Claim → Entity | Relate, Learn | **D2** |
| **SUPERSEDES** | Claim → Claim | Learn (belief revision) | **D2** |
| **CONTRADICTS** | Claim → Claim | Learn, Discover (tensions) | **D2** |
| **QUALIFIES** | Claim → Claim | Learn, Relate | **D2** |

- **SUPPORTS** — a source provides evidence/content for an entity (`role` attr).
  *Exploit:* provenance; T1 context seeding; **the basis for deriving entity
  domain in D1-A.** Keep.
- **LINKS_TO** — a conceptual association between two entities (the wiki link).
  *Exploit:* traversal; T3 neighbor context; the Obsidian graph view. Keep — but
  this single generic type is exactly the ¶419 degeneration; D2 decides whether
  typed claims supplement it.
- **ALIAS_OF** — surface form → canonical entity. *Exploit:* dedup; canonical
  resolution during T2 lookup. Keep.
- **BELONGS_TO** — entity classified into a domain. *Exploit:* domain
  navigation; D3 scoping. **D1** (currently produced from the broken Pass-2
  page-domain).
- **EVIDENCES / ABOUT / SUPERSEDES / CONTRADICTS / QUALIFIES** — the Claim layer
  (Appendix A). Grounding, aboutness, and the three belief-revision relations.
  All **D2**.

---

## 5. Decision D1 — Domain model

**The reframe:** a **Source has exactly one domain** (Pass-1 picks its primary
subject); an **Entity has many** (sources across domains discuss it). That
asymmetry dictates representation: Source-domain fits a **property**
(`Source.domain`, already set by Pass-1); Entity-domain needs **edges**
(`BELONGS_TO`). The only real question is **how the `BELONGS_TO` edges are
created.**

**A — Derive from `SUPPORTS` + `Source.domain` (assistant's lean).**
> *Entity E `BELONGS_TO` Domain D ⟺ ∃ Source S where `S.domain = D` and
> `(S)-[:SUPPORTS]->(E)`.*
- An entity belongs to the domains of the sources that evidence it. Computed
  deterministically at ingest; no LLM at the entity level. Drops the broken
  Pass-2 page-`domain`.
- **For:** 100% coverage; uses the reliable 21-value Pass-1 classification
  (so `value-investing` becomes a real Domain node); multi-domain is natural;
  fully recomputable → run-3 can be **backfilled with no LLM cost** to validate
  before run-4; B-aligned (a coordinate computed from structure); provenance is
  one `SUPPORTS` hop away.
- **Against:** domain is *inherited, not intrinsic* — an entity gets only its
  sources' **primary** domains; a value-investing source mentioning one AI tool
  confers `value-investing` on that AI entity unless an ai-ml source also
  supports it.

**B — Re-assert at the entity level (LLM).** Fix the producer (Pass-1 emits
entity domains, or a new classifier pass) rather than deriving.
- **Against:** this is the approach that just failed (coverage/diversity
  collapse); costs tokens; contradicts the rationale for moving domain to Pass-1
  ("domain relies on source info, not the graph"). An entity in isolation has
  little to classify on. *Assistant ranks this lowest — but the panel should
  judge whether entity-intrinsic domain (independent of source domain) ever buys
  enough precision to justify re-introducing the LLM here.*

**C — No `BELONGS_TO` edge; compute domain at query time** from
`SUPPORTS` + `Source.domain`.
- **For:** zero redundant storage; single source of truth.
- **Against:** no Domain node / materialized edge breaks the viewer, domain
  analytics, and D3's per-compile domain reads; derived-at-read is fine for
  ad-hoc queries, not for a coordinate the pipeline uses every compile.

**Assistant's lean: A** — a materialized *derived view* (recomputed from
authority at each ingest/rebuild, so it cannot drift; not a parallel store).
Domain nodes `MERGE` from the set of `Source.domain` values.

**Open questions (sub-decisions):**
1. Should each derived `BELONGS_TO` edge **record the conferring source(s)** (a
   `via_source` attr / count — useful for "why is this entity in
   value-investing?" and for D3 weighting), or stay bare and recover provenance
   by joining back through `SUPPORTS`?
2. **`sub_domain` retirement.** `BELONGS_TO` carries a `sub_domain` attribute
   today, populated from the Pass-2 page domain. Under D1-A there is no
   per-entity sub-domain source (Pass-1 emits one domain per source, no
   sub-domain). Default: retire `sub_domain` (drop the attribute) unless the
   panel sees a use that justifies keeping it.

---

## 6. Decision D2 — Claim layer (the ¶419 call)

**At stake:** run-3 is 100% generic edges — traverse, don't reason. The `Claim`
layer is the typed vocabulary ¶419 says the power comes from, and the gateway to
**Learn**. It exists in schema v2.2 with `belief_classifier.py` and
`op_1_promote.py` already written (for #83/#84), but the live pipeline produces
zero claims.

**How a Claim answers ¶419 (the bridge a fresh reviewer needs).** ¶419 asks for
*typed entity-to-entity relations* with a *controlled vocabulary*
(`supplies`, `competes_with`). A `Claim` delivers exactly that, as a **reified
typed relation**: `subject_slug --(predicate_class_canonical)--> object_slugs`,
where **`predicate_class_canonical` is the controlled relationship vocabulary**.
It is *reified* (a node, not a bare edge) so the relation can also carry
`polarity`, `modality`, `condition_text`, `confidence`, provenance
(`EVIDENCES`), and version/`state` — the things a plain typed edge cannot hold
and that **Learn** (belief revision) requires.

**Division of labor with `LINKS_TO` (the first question a sharp reviewer asks).**
Claims do **not** replace `LINKS_TO`. The two coexist with distinct jobs:
`LINKS_TO` = cheap, untyped **associative** adjacency (the wiki graph; fuels
proximity traversal and PPR recall — *Relate-by-association*). `Claim` = typed,
grounded, polarized **assertion** (*Relate-by-reasoning* + Learn). So adding
Claims is **not** bolting a parallel structure onto the generic-edge problem —
it adds the reasoning layer the generic layer structurally cannot provide, while
`LINKS_TO` keeps doing the cheap-traversal job it is good at.

**A — Wire the full Claim layer into Pass-2 now** (claims + all five edges).
- **For:** maximal ¶419 payoff; unlocks Relate-as-reasoning *and* Learn at once.
- **Against:** large scope; claim extraction (16-field schema) from arbitrary
  personal notes is hard; cross-run `CONTRADICTS`/`SUPERSEDES` is
  research-adjacent belief revision (#84). High risk of a half-working layer.

**B — Keep `Claim` deferred.** Document it as designed-but-unwired; live pipeline
stays Source/Entity/Domain.
- **For:** honest about scope; zero risk; ships the D1 fix and run-4 fast.
- **Against:** graph stays at "traverse only" permanently; **Learn unreachable**;
  ¶419 keeps biting; punts the project's central question.

**C — Split along the rung it serves (assistant's lean).**
- **Now (Relate→reason):** `Claim` node + `EVIDENCES` (Source→Claim) + `ABOUT`
  (Claim→Entity). Query *"what does this source assert about Buffett?"* — typed,
  grounded, about an entity.
- **Later (Learn):** `SUPERSEDES`/`CONTRADICTS`/`QUALIFIES` (Claim→Claim) stay in
  the #83/#84 arc, gated by the Hypothesis Promotion contract (Round 6 — no
  belief mutation except through #83).
- **For:** concrete-first — land typed claims, prove extraction works at personal
  scale (tests ¶419/¶407), *then* build belief-revision on a working substrate;
  bounded Pass-2 expansion; respects Round 6 gating.
- **Against:** still a real Pass-2 prompt/schema expansion; wasted if claim
  extraction proves low-yield at personal scale (the ¶407 risk).

**Open question for the panel:** *at personal corpus scale (~30 sources, ~180
entities), does typed-claim extraction deliver enough reasoning/Learn value to
justify the Pass-2 complexity — or does it degrade to noisy, low-yield assertions
(¶407's "prompt-not-engine")?* This is the empirical heart of ¶419.

---

## 7. Decision D3 — T2/T3 domain-scoping

**Mechanism:** context for each compile is tiered — **T1** = source-supported
entities (`SUPPORTS`); **T2** = entities seeded from the source's Pass-1
`entity_search_keys`; **T3** = 1-hop neighbors of T1∪T2. The proposal: scope
T2's lookup and T3's expansion to the **same domain**. *(Depends on D1 — needs
reliable per-entity domains, i.e. D1-A.)*

**The tension:** a hard domain gate sharpens **Relate** precision, but
**cross-domain links are exactly what Discover is** (Swanson-style: value-
investing ↔ psychology via "Mr. Market"/behavioral bias). Gating T2/T3 to
same-domain means the compile LLM never sees cross-domain context, so it never
proposes those edges — the graph could never surface them. A hard gate optimizes
rung 2 at the cost of rung 4, and applying domain as a *mandatory* compile-time
filter drifts toward "gate" rather than "coordinate" (C2).

**A — Hard domain gate.** T2 same-domain only; T3 same-domain neighbors only.
- **For:** maximum disambiguation (kills same-slug cross-domain false matches);
  the real critical-density mitigation (Appendix B, §7.4b) at scale.
- **Against:** suppresses cross-domain Discover; brittle to D1 inheritance
  errors; coordinate→gate drift.

**B — No scoping (status quo).** Full-graph T2/T3.
- **For:** preserves all emergent cross-domain links; pure-B.
- **Against:** the precision problem; at scale, critical density floods context.

**C — Domain as a ranking + budget coordinate, not a gate (assistant's lean).**
T2/T3 still search the full graph, but same-domain candidates are **prioritized**
in the context budget; cross-domain candidates are **allowed but down-weighted /
capped**. Domain shapes order and share, not membership.
- **For:** same-domain dominates context (the precision) **without** silencing a
  strong cross-domain match (Discover survives); honors coordinate-not-gate;
  degrades gracefully on D1 errors; the weight is a **tunable that tightens as
  the corpus approaches critical density** — the "watch and intervene" path the
  kernel doc prescribes.
- **Against:** more complex than a filter; needs a weighting/budget policy.

**Variant D — tiered:** gate the T2 seeds (anchor precision) but leave T3
neighbor-expansion open (discovery still reaches one hop across domains).

**Open question for the panel:** *how to get domain precision in retrieval
without sacrificing cross-domain Discover* — and if soft, how aggressive the
same-domain weighting should be, and whether to gate-seeds-but-open-neighbors.
This blueprint settles the **stance** (gate vs coordinate); the exact algorithm
belongs to the consumer sub-project.

---

## 8. Summary — settled vs open

**Settled (not for panel debate):** Philosophy B; the five-rung ladder;
coordinate-not-gate; Source/Entity nodes and SUPPORTS/LINKS_TO/ALIAS_OF edges
kept as-is; the broken Pass-2 page-`domain` is dropped regardless of D1's
outcome.

**Ratified (v0.2 — see § Ratification):** D1 → **A** (0.5.0) · D2 → **deferred to
Release 2.0** · D3 → **C + refined variant D** (0.5.0, algorithm to consumer
sub-project).

**Downstream sequence (→ 0.5.0):** Pass-2 producer rebuild (implements **D1** only —
no claims) → T2/T3 rebuild (implements **D3**) → stdout messaging → **run-4** (the
0.5.0 gate). Releases per `docs/ROADMAP.md`; Claim/Learn layer is 2.0.

---

## Appendix A — Current schema DDL (Kuzu, schema v2.2, verbatim)

```
CREATE NODE TABLE Entity (
    slug STRING PRIMARY KEY, title STRING, page_type STRING, status STRING,
    confidence STRING, canonical_id STRING, created_at STRING, updated_at STRING,
    first_run_id STRING, last_run_id STRING
)
CREATE NODE TABLE Source (
    source_id STRING PRIMARY KEY, source_type STRING, canonical_path STRING,
    status STRING, file_type STRING, hash STRING, size_bytes INT64,
    first_seen_at STRING, last_seen_at STRING, last_ingested_at STRING,
    ingest_state STRING, ingest_count INT64, last_run_id STRING, moved_to STRING,
    summary STRING, author STRING, domain STRING
)
CREATE NODE TABLE Domain ( name STRING PRIMARY KEY, created_at STRING, first_run_id STRING )
CREATE NODE TABLE Claim (
    claim_id STRING PRIMARY KEY, claim_family_id STRING, subject_slug STRING,
    predicate_class_canonical STRING, predicate_class_raw STRING,
    predicate_scope_slugs STRING[], object_slugs STRING[], polarity STRING,
    modality STRING, condition_text STRING, assertion_text STRING,
    confidence DOUBLE, confidence_spread DOUBLE, state STRING, version INT64,
    created_at STRING, last_revised_at STRING
)

CREATE REL TABLE LINKS_TO   ( FROM Entity TO Entity, run_id STRING, created_at STRING )
CREATE REL TABLE SUPPORTS   ( FROM Source TO Entity, role STRING, hash_at_time STRING, run_id STRING, created_at STRING )
CREATE REL TABLE ALIAS_OF   ( FROM Entity TO Entity, run_id STRING, created_at STRING, algorithm STRING )
CREATE REL TABLE BELONGS_TO ( FROM Entity TO Domain, run_id STRING, created_at STRING, sub_domain STRING )
CREATE REL TABLE EVIDENCES  ( FROM Source TO Claim, quoted_text STRING, score DOUBLE, provenance_type STRING, run_id STRING, created_at STRING )
CREATE REL TABLE ABOUT      ( FROM Claim TO Entity, run_id STRING, created_at STRING )
CREATE REL TABLE SUPERSEDES ( FROM Claim TO Claim, run_id STRING, created_at STRING )
CREATE REL TABLE CONTRADICTS( FROM Claim TO Claim, contradiction_kind STRING, run_id STRING, created_at STRING )
CREATE REL TABLE QUALIFIES  ( FROM Claim TO Claim, run_id STRING, created_at STRING )
```

---

## Appendix B — Load-bearing excerpts from `what-is-ontology-for-V1.md`

**¶407 — the honesty on Discover/Create at personal scale:**
> "One honest negative: automated 'knowledge creation' / gap-detection is largely
> oversold at personal scale. Link prediction is real in dense biomedical graphs
> with ground truth; on a few thousand personal notes it degrades to heuristic
> 'these two notes share entities but aren't linked.' Useful as a *prompt*, not a
> discovery engine."

**¶413 — Create, mapped to what's real:**
> "Create — the honest frontier. The grand version ('the system creates knowledge
> by itself') is still dream. The real version: the graph's operations make
> latent structure visible — community detection surfaces a theme you never
> named; traversal surfaces a connection you never drew. The graph doesn't create
> the knowledge; it surfaces the raw material and provokes you (or the LLM) to.
> Creation stays a collaboration."

**¶419 — the typed-vocabulary tension (central to D2):**
> "Everything powerful in the research — and in your own 10x engine — draws its
> power from structured extraction: *typed* entities, a *controlled* relationship
> vocabulary (supplies, is_bottleneck_for, competes_with), typed judgments (moat,
> margin_of_safety). 10x is potent precisely because it is *not* domain-general —
> its schema encodes investing. A domain-general KDB — 'compile anything from
> anywhere' — risks giving that up: a schemaless topology spanning value-investing
> + Chinese history + AI/ML + dev logs may be a graph you can *traverse* but not
> *reason* over, because the relationship types degenerate to relates_to."

**§7.4b — critical density (relevant to D3):**
> "As you ingest heterogeneous data, the graph will eventually hit a Critical
> Density where everything connects to everything. At that point PPR/PageRank
> might stop providing useful local activation and instead just return the most
> 'popular' nodes." — Resolution: a third empirical hedge; the only mitigations
> are *structural* (domain-aware operations), not labeling-based.

**Round 6 — Learn taxonomy (relevant to D2):** Learn = persistent graph-state
evolution, via three mechanisms — Belief Revision (#84), Identity Refinement
(#85), Abstraction (#86) — each gated by the **Hypothesis Promotion contract
(#83)**: no Analysis output may mutate graph state except through it.

---

## Appendix C — Run-3 evidence (per-source dumps available in repo)

- Pass-1 source domains (signal sources): `value-investing` 9 · `software` 7 ·
  `ai-ml` 4 · `health-wellbeing` 2 · `math-statistics-logic` 1 · `psychology` 1
  · `neuroscience-cognition` 1 · `geopolitics` 1 · `quotes` 1 · `history` 1 ·
  `personal-finance` 1. (**11 domains.**)
- Pass-2 page domains (what drives `BELONGS_TO` today): only `software` 18 ·
  `personal-finance` 6 · `math-statistics-logic` 4 · `ai-ml` 1; **None on 156 of
  185 pages.** (**4 domains; `value-investing` never emitted.**)
- Concept pages with a domain: **24 / 147 (16%).**
- **Verified against the run-3 Kuzu graph (2026-05-31):** `Source` 29/29 carry a
  `domain` property — `value-investing` 9 · `software` 7 · `ai-ml` 4 ·
  `health-wellbeing` 2 · `neuroscience-cognition` 1 · `math-statistics-logic` 1 ·
  `personal-finance` 1 · `psychology` 1 · `geopolitics` 1 · `quotes` 1 ·
  `history` 1 (the full 11-domain Pass-1 distribution). Entities with a
  `BELONGS_TO` edge: **29** (of 178). `Domain` nodes: **4**. This confirms the
  reliable classification lives on `Source.domain` today and is simply not
  propagated to entities — the factual basis for D1-A.
