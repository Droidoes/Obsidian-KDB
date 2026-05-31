# Round 6 Research Synthesis — Opus 4.7

**Role:** Research synthesist. Literature survey + stress-test of the
working hypothesis in `docs/what-is-ontology-for-V1.md` §9.1.1. No
implementation, no task plans, no schema diffs.
**Filed:** 2026-05-22

---

## Executive summary

The literature does not provide a single canonical definition of "learning"
for a knowledge graph. It provides at least four, drawn from disjoint
research traditions: the AGM belief-revision tradition treats learning as
*expansion / revision / contraction* of a deductively closed belief set
(Alchourrón, Gärdenfors & Makinson, *J. Symbolic Logic* 50, 1985); the KG
embedding tradition treats learning as parameter updates on entity/relation
vectors via gradient descent (Bordes et al., NIPS 2013 — TransE); the
continual / incremental learning tradition treats learning as integrating
streaming updates while avoiding catastrophic forgetting (Wu et al. 2021;
BAKE — Liu et al. arXiv:2508.02426); and the symbolic / inductive tradition
treats learning as rule extraction from instances (AMIE — Galárraga et al.,
WWW 2013; AnyBURL — Meilicke et al. 2020). These camps rarely cite each
other.

The most useful organizing question across the literature is **what state
changes when the system "learns"?** Four answers are well-attested:
embedding/parameter state, graph topology, edge/assertion weight state, and
induced symbolic abstractions. An operation that runs against frozen state
and does not persist any change is, by the literature's own usage,
*analysis* or *inference* — not learning.

Under that frame the working hypothesis survives partially. **Mechanism 1
(belief tracking)** is the strongest learning candidate the literature
supports — closest to AGM's contraction/revision operators and to the
continual-KGE subfield. **Mechanism 4 (concept refinement)** survives in a
narrower form: the *temporal/contextual split* sub-operation is state-changing;
the *canonicalization* sub-operation is preprocessing. **Mechanisms 2 (link
prediction) and 3 (community detection)** die under the working hypothesis's
own "Learn = state evolution" definition: the literature classifies both as
operations against frozen snapshots — community detection unambiguously, link
prediction at the inference step. The genuine *learning* in link prediction
lives in the offline training of the embedding model, which is intractable
at personal scale (TransE was trained on FB1M = 1M entities). The working
hypothesis also misses a fifth mechanism the literature endorses:
**compression / principle induction** — rule mining and LLM-driven
abstraction-with-commit-back.

T2 (anti-goal sharpens the cut) is partially supported. The literature does
not validate a strict "only belief revision counts as learning" cut —
GraphRAG and Leiden community detection are treated as legitimate
*sensemaking* operations. But the user-facing claim — *vanity surfacing
without behavioral change is not learning for a second brain* — aligns
with the operational distinction the literature *does* draw between
graph-state-changing operations (which persist) and graph-analysis
operations (which produce one-shot output).

---

## Working-hypothesis adjudication

### T1 — Are Mechanisms 2 and 3 Learn or Remember?

**Mostly Analysis. Some literature treats them as learning, but only
loosely.**

**Community detection.** The canonical references — Blondel et al.
(*J. Stat. Mech.* 2008) for Louvain; Traag, Waltman & Van Eck (*Sci. Rep.*
9:5233, 2019) for Leiden — frame the operation as *graph clustering* or
*modularity optimization* on a fixed graph. Some venues label this
"unsupervised learning" (e.g., the GNN-Louvain hybrid literature, arXiv
2509.23411) because no labels are supplied, but no canonical community
detection paper claims the operation *changes the graph*. It produces a
partition; the partition is an artifact, not a state update. Under the
working hypothesis's own definition ("Learn = how the graph state evolves
as the corpus grows"), community detection is Analysis. It is what
GraphRAG (Edge et al., arXiv:2404.16130) uses as a *retrieval / query
focused summarization* substrate — and Edge et al. explicitly position
GraphRAG as a *retrieval-augmented generation* method, not a learning
method.

**Link prediction.** Here the split is sharper but more interesting. The
TransE paper (Bordes et al., NIPS 2013) and successors (ComplEx — Trouillon
et al., ICML 2016; RotatE — Sun et al., ICLR 2019; R-GCN — Schlichtkrull et
al., ESWC 2018; CompGCN — Vashishth et al., ICLR 2020) describe two
phases: (a) *training* — gradient descent updates entity/relation
embeddings on observed triples; (b) *inference / scoring* — using fixed
embeddings to rank candidate triples. Phase (a) is learning in the
representation-learning sense (parameter state changes); phase (b) is
inference (parameter state does not change; the graph does not change
unless predictions are committed). Rule-based link prediction (AnyBURL —
Meilicke et al. 2020; Neural LP — Yang, Yang & Cohen, NeurIPS 2017) has
the same split: rule mining is learning, rule application is inference.

The KG-completion literature is explicit that the predicted links *complete*
the graph — i.e., they are absent from the structure until materialized.
If predictions are not persisted, no graph state evolves; one has only
ranked candidates. So link prediction *can* serve as a Learn operation,
but only via the commit-back step; in default form it is closer to
Remember-with-novelty.

**Recommendation:** Reclassify both as **Analysis**, with a footnote that
link prediction becomes Learn at the moment its predictions are persisted
to the graph. Pure "the graph learns latent structure" framings appear in
loose secondary literature but are not the way the primary methods papers
describe themselves.

### T2 — Does the anti-goal sharpen the cut?

**Partially. It sharpens the *user-facing* cut but not the *literature's*
cut.**

The literature does not draw a hard line at belief-revision-as-only-true-
learning. Community detection in GraphRAG, PageRank diffusion in HippoRAG
(Gutiérrez et al., NeurIPS 2024 — arXiv:2405.14831), and link prediction in
biomedical KGs are all treated as legitimate operations that *deliver
value* without revising any explicit belief. Specifically, HippoRAG frames
itself as a *long-term memory* architecture (the paper's title is
"Neurobiologically Inspired Long-Term Memory for Large Language Models")
and motivates its design by the hippocampal-indexing theory of memory —
not by any learning-theoretic claim. PPR-based recall is positioned as
*memory*, not learning.

But the anti-goal's force comes from a different argument: *what makes a
second brain a second brain is not surface area but capacity-change*. The
continual KGE literature (BAKE; Streaming GNNs — Wang et al. arXiv:2009.10951;
CGKGC — Springer 2026) is unified on this point: the central engineering
question is *how acquiring new information without losing old information
changes what the model can do next*. Analysis operations don't change
what the model can do; learning operations do. To that extent, the anti-
goal aligns with the literature's deepest framing of learning, even if it
overreaches by excluding analysis from the toolbox.

**Recommendation:** Treat the anti-goal as a *value-alignment criterion*
for selecting which operations are most worth building first, not as a
philosophical disqualifier of analysis operations. The literature endorses
both classes, but the operations whose effects *persist* (and therefore
change future answers) are the ones that earn the "Learn" label cleanly.

### Mechanism 1 (Belief tracking) — verdict

**KEEP.** This is the cleanest match between the working hypothesis and
the deepest learning frame in the literature.

The philosophical grounding is AGM (Alchourrón, Gärdenfors & Makinson,
1985). AGM decomposes belief change into three operators:

- **Expansion**: adding a sentence consistent with the current belief set
  (corresponds to the working hypothesis's "genuinely-new" / "reinforces").
- **Revision**: adding a sentence inconsistent with the current belief
  set, requiring withdrawal of conflicting beliefs (corresponds to
  "contradicts-prior").
- **Contraction**: withdrawing a belief without adding a replacement
  (corresponds to "decay stale ones").

The working hypothesis's delta protocol is, *at the operator level*, an
AGM instantiation — without the deductive-closure machinery AGM uses to
define which other beliefs must change consequentially. That omission
matters: classical AGM presupposes deductive closure, which is undecidable
for sufficiently expressive logics (Falakh, Rudolph & Sauerwald,
arXiv:2112.13557) and intractable in practice. Engineered AGM-style
systems (SNePS / SNeBR — Shapiro & Johnson 2000) handle this by user-
mediated contradiction resolution. The continual-KGE literature side-steps
the closure problem entirely by working at the level of edge weights and
embeddings (BAKE; LKGE; EWC-based methods), which is the more tractable
operationalization at scale.

For a personal KG, the AGM frame is the right *philosophical anchor*; the
continual-KGE frame is the right *engineering anchor*. Mechanism 1
survives — but should be understood as "belief weight + version
management on assertions," not as classical AGM.

### Mechanism 2 (Connection discovery) — verdict

**RECLASSIFY as Analysis** (sub-case: becomes Learn if commit-back is
added).

Literature basis: TransE (Bordes et al. 2013); ComplEx (Trouillon et al.
2016); RotatE (Sun et al. 2019); R-GCN (Schlichtkrull et al. 2018);
CompGCN (Vashishth et al. 2020); AnyBURL (Meilicke et al. 2020). All
describe link prediction as *inference at scoring time* over learned
representations. Structural-hole detection (Burt, *Structural Holes*, 1992,
adapted to KGs) is purely topological analysis.

The mechanism is valuable but does not satisfy the working hypothesis's
own "Learn = state evolution" criterion in default form.

### Mechanism 3 (Pattern emergence) — verdict

**RECLASSIFY as Analysis.**

Literature basis: Blondel et al. 2008 (Louvain); Traag et al. 2019
(Leiden); Rosvall & Bergstrom (Infomap, PNAS 2008); Karrer & Newman
(stochastic block models, *Phys. Rev. E* 2011); Edge et al. 2024
(GraphRAG community summarization). Across this literature, community
detection is consistently treated as graph *clustering* or *partitioning*
of a frozen graph. The output (a partition) is a derived artifact, not a
state update on the graph.

Sub-finding to flag: at personal scale, community detection has a known
**resolution limit** (Fortunato & Barthélemy, *PNAS* 2007). Modularity
optimization cannot resolve communities smaller than a scale that depends
on the graph's total edge count, and tends to merge small communities
even when they are clearly distinct. At ~1K–10K entities this is a real
constraint, separate from the Learn/Remember question.

### Mechanism 4 (Concept refinement) — verdict

**REFINE.** Two distinct operations are conflated.

(a) **Canonicalization / entity resolution.** The literature treats this
as a *preprocessing / data-quality* operation (Galárraga et al. 2014 on
canonicalization for open KBs; Vashishth et al. 2018 — CESI). It is
necessary for everything else to work, but it does not change the
*epistemic* state of the graph — it changes the *identity* state. Closer
to graph hygiene than learning.

(b) **Temporal / contextual splits** (e.g., "Buffett-1990s" vs.
"Buffett-2020s" as distinct entities). This is a genuine epistemic
update — the graph now commits to the claim that two contexts host
distinguishable identities. The temporal KG literature (Know-Evolve —
Trivedi et al., ICML 2017; HyTE — Dasgupta et al., EMNLP 2018; RE-NET —
Jin et al., EMNLP 2019; TLogic — Liu et al., AAAI 2022) is the closest
analog, though those systems handle time-annotated facts rather than
context-driven entity disambiguation per se. Entity-linking work on NIL
clustering (Lin et al. 2012; Kobren et al. 2019) is closer to the
operation as described.

**Recommendation:** Split the mechanism. Keep (a) as a compile-stage
hygiene operation. Promote (b) to a Learn operation in its own right.

---

## Additional mechanisms the literature supports

### Compression / abstraction (instance → principle)

This is the mechanism the working hypothesis most clearly misses.

**Rule mining.** AMIE (Galárraga, Teflioudi, Hose & Suchanek, WWW 2013)
and AnyBURL (Meilicke et al. 2020) mine first-order Horn-clause rules
from instance triples — e.g., from many (X, livesIn, Y) and (Y, locatedIn,
Z), induce "livesIn ∘ locatedIn → livesIn". Symbolic rule mining is
explicitly *induction* in the inductive-logic-programming sense:
extracting a general principle that holds across many instances. The
mined rule is itself a graph artifact (often stored as a rule node or
schema axiom) that can be applied later — that's the commit-back step
that makes this genuine state evolution.

**Schema induction.** Work on inducing description-logic axioms from KGs
(Bühmann & Lehmann 2013, DL-Learner; Bühmann, Lehmann & Westphal 2016) is
the deductive-logic analog. Less prevalent in the modern literature; more
brittle than statistical rule mining.

**LLM-driven summarization-with-commit.** A modern variant: have an LLM
read the contents of a community or sub-graph and produce a *principle*
that is then materialized as a new node/edge in the graph. GraphRAG's
community summaries are the *non-committing* version (the summaries are
indexed, not added as graph nodes). The variant where summaries become
first-class graph elements is increasingly common but lacks a single
canonical reference yet.

**Why this matters:** without an abstraction mechanism, the graph
accumulates instances forever and never produces principles. That is
exactly the failure mode the anti-goal warns against — the graph grows in
surface area but not in the *kinds* of things it knows. AMIE and
AnyBURL-style rules are the literature's principled answer.

### Forgetting / decay / contraction as a first-class operation

Worth flagging as a sub-component of Mechanism 1 rather than a separate
slot. The continual-KGE literature (BAKE; LKGE; CGKGC; Wu et al. 2021 on
experience replay) frames forgetting as the central engineering risk of
learning. AGM contraction and reason-maintenance systems (Doyle 1979 —
TMS; SNeBR — Johnson & Shapiro 2000) frame it as a deliberate operator.
The literature draws a useful distinction between "the system forgets"
(weights decay, beliefs are withdrawn) and "the system never knew" (the
assertion was never stored) — a personal KG should be able to do the
former without losing provenance of the latter. For a personal corpus,
the heavyweight continual-KGE machinery is disproportionate; weighted-
evidence with recency-decay on edges (the GraphMem-class approach) is
the proportional operationalization.

---

## Empirical viability at personal scale (1K–10K entities)

| Mechanism | Tractable at personal scale? | Literature basis for scale claim |
|---|---|---|
| Belief tracking (weight + version on assertions) | **Yes.** Bookkeeping operation, no statistical mass required. | Continual KGE works at any scale; AGM is scale-agnostic in principle (intractable only for full deductive closure). |
| Connection discovery via embedding-based link prediction | **No, in default form.** TransE original training: 1M entities, 17M triples (Bordes et al. 2013). At ~70–10K entities, embedding models are severely under-determined. | Direct from primary sources. |
| Connection discovery via simple co-occurrence / structural-hole detection | **Yes**, but degrades to "these two notes share an entity but aren't linked" — useful as a prompt, not as discovery. | Document §6.3 ¶407 already concedes this. |
| Pattern emergence (community detection) | **Marginal.** Modularity resolution limit (Fortunato & Barthélemy, PNAS 2007) bites hard below ~10K edges; communities often degenerate to "the obvious clusters." Leiden is somewhat more robust than Louvain at small scale. | Fortunato & Barthélemy 2007; Traag et al. 2019. |
| Concept refinement — canonicalization | **Yes.** A solved engineering problem at any scale (CESI; recent LLM-aided entity resolution). | Vashishth et al. 2018; modern LLM-resolution literature. |
| Concept refinement — temporal/contextual splits | **Yes**, but requires deliberate operationalization. The temporal-KG literature works at larger scales (ICEWS, GDELT) but the mechanism transfers downward. | Trivedi et al. 2017; Jin et al. 2019. |
| Rule mining (AMIE / AnyBURL) | **Marginal-to-yes**, with caveats. AMIE was designed for YAGO/Freebase (millions of triples). At personal scale, classical statistical rule mining will mine few rules with high confidence — but LLM-assisted variants are tractable. | Galárraga et al. 2013; Meilicke et al. 2020. |
| LLM-driven principle extraction with commit-back | **Yes**, and the literature is rapidly accumulating examples (GraphRAG community summarization; GraphMem decay-driven importance scoring). | Edge et al. 2024; recent GraphMem-class systems. |
| Continual KGE (BAKE-style) | **Overkill for personal scale.** The machinery is designed for tens of snapshots over millions of entities. | BAKE — arXiv:2508.02426. |

**Synthesis on scale:** Mechanisms that depend on *statistical mass*
(embedding-based link prediction; classical community detection at fine
granularity; classical rule mining) need ≥100K entities to behave
non-degenerately. Mechanisms that depend on *bookkeeping* or *LLM-driven
extraction* (belief tracking; canonicalization; LLM-driven abstraction;
recency-weighted decay) are tractable at personal scale, possibly even
*more* effective at personal scale than at web scale where LLM-context-
window constraints bite harder.

---

## Recommended decomposition for Round 6 to ratify

**Definition of Learn:** An operation is a Learn operation if, when it
runs, it changes the graph's epistemic state in a way that persists across
queries — i.e., it changes what the system *takes to be the case*, not
just what it *shows to the user*. Operations whose output is consumed once
and discarded are Remember (one-shot retrieval) or Analysis (decomposition
of a frozen snapshot). The Learn / Remember / Analysis trichotomy is
sharper than the original Learn / Remember binary.

**Three mechanisms** — distilled from the four-mechanism draft plus the
missing abstraction slot:

1. **Belief revision** — versioning claims; reinforcement, contradiction
   handling, decay/contraction. AGM-flavored at the philosophical level;
   continual-KGE-flavored at the engineering level. Operates on edge /
   assertion weight state.
2. **Abstraction / principle induction** — extracting general statements
   from N concrete instances, *committed back to the graph* as
   first-class nodes/edges. Three sub-paths in the literature: rule
   mining (AMIE / AnyBURL), schema induction (DL-Learner-style), and
   LLM-driven summarization-with-commit. Operates on the graph's
   symbolic-abstraction state.
3. **Identity refinement** — canonicalization-as-hygiene plus
   temporal/contextual splits as state evolution. Operates on the
   graph's identity state.

**Connection discovery and pattern emergence are reclassified as
Analysis**, not Learn. They remain valuable second-brain operations —
they are the mechanisms most directly responsible for the project's
[C] Create goal, by surfacing latent structure the human or LLM can act
on. But they should not be counted toward [B] Learn under the working
hypothesis's own state-evolution definition. Calling them Learn dilutes
the term and weakens the project's ability to argue that it is doing
something Obsidian's existing graph view does not.

**One disagreement with the working hypothesis worth flagging.** The
working hypothesis's second reframe — *"Create is the same engine seen
one step further. Mechanisms 2 + 3 provoke creation when surfaced"* — is
*strengthened* by the reclassification, not weakened. Connection
discovery and pattern emergence are *exactly* the mechanisms that
provoke Create. Calling them Analysis acknowledges what they actually do
(decompose the frozen graph to surface novel structure) and clarifies
their role in the architecture (input to Create, not constituent of
Learn).

---

## References

Alchourrón, C.E., Gärdenfors, P., & Makinson, D. (1985). On the Logic of
Theory Change: Partial Meet Contraction and Revision Functions. *Journal
of Symbolic Logic*, 50(2), 510–530.

Blondel, V.D., Guillaume, J.-L., Lambiotte, R., & Lefebvre, E. (2008).
Fast unfolding of communities in large networks. *Journal of Statistical
Mechanics: Theory and Experiment*, 2008(10), P10008.

Bordes, A., Usunier, N., Garcia-Duran, A., Weston, J., & Yakhnenko, O.
(2013). Translating Embeddings for Modeling Multi-relational Data.
*Advances in Neural Information Processing Systems* (NIPS), 26,
2787–2795.

Bühmann, L., & Lehmann, J. (2013). Pattern based knowledge base
enrichment. *International Semantic Web Conference (ISWC)*.

Burt, R.S. (1992). *Structural Holes: The Social Structure of
Competition*. Harvard University Press.

Doyle, J. (1979). A Truth Maintenance System. *Artificial Intelligence*,
12(3), 231–272.

Edge, D., et al. (2024). From Local to Global: A Graph RAG Approach to
Query-Focused Summarization. arXiv:2404.16130.

Falakh, F.M., Rudolph, S., & Sauerwald, K. (2021). Semantic
Characterizations of General Belief Base Revision. arXiv:2112.13557.

Fortunato, S., & Barthélemy, M. (2007). Resolution limit in community
detection. *Proceedings of the National Academy of Sciences*, 104(1),
36–41.

Galárraga, L.A., Teflioudi, C., Hose, K., & Suchanek, F.M. (2013).
AMIE: Association Rule Mining under Incomplete Evidence in Ontological
Knowledge Bases. *Proceedings of the 22nd International Conference on
World Wide Web (WWW)*, 413–422.

Galárraga, L.A., Heitz, G., Murphy, K., & Suchanek, F.M. (2014).
Canonicalizing Open Knowledge Bases. *CIKM 2014*.

Gutiérrez, B.J., Shu, Y., Gu, Y., Yasunaga, M., & Su, Y. (2024).
HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language
Models. *Advances in Neural Information Processing Systems* (NeurIPS).
arXiv:2405.14831.

Jin, W., Qu, M., Jin, X., & Ren, X. (2019). Recurrent Event Network:
Autoregressive Structure Inference over Temporal Knowledge Graphs.
*EMNLP*. arXiv:1904.05530.

Johnson, F.L., & Shapiro, S.C. (2000). Implementing Integrity Constraints
in an Existing Belief Revision System. *Frontiers in Belief Revision*,
also as Tech Report 2000-03, SUNY Buffalo.

Karrer, B., & Newman, M.E.J. (2011). Stochastic blockmodels and community
structure in networks. *Physical Review E*, 83(1), 016107.

Liu, J., et al. (2025/2026). BAKE: Learning to Evolve — Bayesian-Guided
Continual Knowledge Graph Embedding. arXiv:2508.02426 / WWW '26.

Meilicke, C., Chekol, M.W., Ruffinelli, D., & Stuckenschmidt, H. (2020).
Reinforced Anytime Bottom Up Rule Learning for Knowledge Graph
Completion (AnyBURL). arXiv:2004.04412.

Rosvall, M., & Bergstrom, C.T. (2008). Maps of random walks on complex
networks reveal community structure (Infomap). *Proceedings of the
National Academy of Sciences*, 105(4), 1118–1123.

Schlichtkrull, M., et al. (2018). Modeling Relational Data with Graph
Convolutional Networks (R-GCN). *ESWC*.

Sun, Z., Deng, Z.-H., Nie, J.-Y., & Tang, J. (2019). RotatE: Knowledge
Graph Embedding by Relational Rotation in Complex Space. *ICLR*.

Trivedi, R., Dai, H., Wang, Y., & Song, L. (2017). Know-Evolve: Deep
Temporal Reasoning for Dynamic Knowledge Graphs. *ICML*.

Trouillon, T., Welbl, J., Riedel, S., Gaussier, É., & Bouchard, G.
(2016). Complex Embeddings for Simple Link Prediction (ComplEx). *ICML*.

Traag, V.A., Waltman, L., & Van Eck, N.J. (2019). From Louvain to Leiden:
guaranteeing well-connected communities. *Scientific Reports*, 9, 5233.

Vashishth, S., Jain, P., & Talukdar, P. (2018). CESI: Canonicalizing Open
Knowledge Bases using Embeddings and Side Information. *WWW 2018*.

Vashishth, S., Sanyal, S., Nitin, V., & Talukdar, P. (2020).
Composition-based Multi-Relational Graph Convolutional Networks
(CompGCN). *ICLR*.

Wang, J., Song, G., Wu, Y., & Wang, L. (2020). Streaming Graph Neural
Networks via Continual Learning. arXiv:2009.10951.

Yang, F., Yang, Z., & Cohen, W.W. (2017). Differentiable Learning of
Logical Rules for Knowledge Base Reasoning (Neural LP). *NeurIPS*.

---

**Inferences and judgments not directly cited:** the claim that the four
"learning" traditions rarely cite each other is the author's own
literature-survey observation. The mapping of the working hypothesis's
delta-protocol terminology ("genuinely-new / contradicts-prior /
reinforces-consensus") onto AGM's expansion/revision/contraction
operators is the author's own correspondence; AGM does not use these
terms. The reclassification of Mechanisms 2 and 3 as Analysis is grounded
in the source literature's own framing but is not itself a literature
finding — it is a deduction from the working hypothesis's stated
definition.
