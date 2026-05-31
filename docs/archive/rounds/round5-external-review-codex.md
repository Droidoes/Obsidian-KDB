# Round 5 External Review — Codex

**Overall Position:** B-viable, not B-strong. Joseph is right to resist human
pre-curation as the default, but "LLM + graph turns chaos into order" is still
an empirical claim, not an architectural axiom.

## 1. Latent A Diagnosis

Mostly correct. The Round 4 claim that power comes from "typed entities" and a
"controlled relationship vocabulary" does reintroduce pre-decided meaning at
the schema layer (`docs/what-is-ontology-for-V1.md` §6.3, line 419). But the
cleaner distinction is: structured representation is not A; human-defined
controlled schema as a precondition is A.

## 2. C1/C2

C1 is B-compatible, but not "schemaless" in the pure sense. The LLM still
performs compression and salience selection; it is not neutral. It stays B only
if outputs are auditable, revisable, provenance-linked, and not treated as
canonical truth.

C2 holds if domain is post-ingest metadata and query-time partitioning
(`docs/what-is-ontology-for-V1.md` §7.2, lines 573-583). If domain affects
ingestion, prompts, extraction policy, storage paths, or acceptance, it becomes
a gate.

## 3. Schema Reframe

Sound but slightly underdeveloped. Claude is right that HippoRAG/PPR and
GraphRAG-style community detection do not require a typed domain schema
(`docs/what-is-ontology-for-V1.md` §7.2, lines 552-565). The missing nuance:
schemaless graphs can still support richer operations through induced types,
embeddings, clustering, and runtime projections. Typed schema buys domain
algorithms, but domain algorithms do not have to be human-authored upfront.

## 4. 10x Recalibration

Correct. Treating 10x as a finished answer was too strong; Joseph's correction
that it is another deliberation-stage attempt is persuasive
(`docs/what-is-ontology-for-V1.md` §7.1, lines 459-469). Reframing it as a
parallel domain-first experiment is the right move
(`docs/what-is-ontology-for-V1.md` §7.2, lines 528-535).

## 5. Empirical Hedges

The two named hedges are real: scale and cross-domain density
(`docs/what-is-ontology-for-V1.md` §7.3, lines 684-692). Missing hedges:
extraction consistency, entity resolution/canonicalization, relation drift,
provenance quality, evaluation metrics, query workload definition,
contradiction handling, stale-source revision, and cost/latency at repeated
compile time.

## 6. Path Forward

Mostly sound, but only if paired with predeclared evaluation criteria. "Build
harvesters, run operations, revisit if degenerate" is pragmatic
(`docs/what-is-ontology-for-V1.md` §7.2, lines 622-635). But without
success/failure tests, it risks becoming implementation momentum disguised as
empiricism.

## 7. Joseph's [8]

Load-bearing, but overstated. If A means "humans must confer all meaning before
storage," then yes, KDB's novelty collapses
(`docs/what-is-ontology-for-V1.md` §7.2, lines 507-512). But A-flavored
systems can still be worth building: automated curation, high-recall personal
search, contradiction tracking, source-grounded synthesis, and maintenance of a
human-approved knowledge base. They are less novel than B, not worthless.

## 8. Major Blind Spot

The deliberation treats "selection" too coarsely. There is ingestion selection,
extraction selection, canonicalization selection, query-time selection, and
human interpretation selection. B only rejects the first kind. It still depends
heavily on the others. The next round should separate those layers explicitly
before changing architecture.
