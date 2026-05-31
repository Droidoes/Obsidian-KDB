# Ontology Blueprint V1 - Codex Review

## Summary

The blueprint is directionally right: it correctly identifies that run-3's two
visible ontology failures are not generic graph failures, but meaning-layer
failures: domain is authoritative on `Source` but not propagated to `Entity`,
and the live graph has no typed assertion layer. My verdict is D1 = A with one
important semantic clarification; D2 = modified C, shipped as a constrained
claim pilot rather than full arbitrary assertion extraction; D3 = C, with
separate budget rules for T2 and T3 but no hard same-domain gate.

The biggest thing the blueprint under-weights is not whether these structures
are useful. They are. The risk is that their names overclaim their semantics:
`BELONGS_TO` under D1-A means "attested in a domain through source support", not
"intrinsically part of this domain"; `Claim` means "grounded extracted
assertion", not "truth"; and domain-scoped retrieval means "budget shaping", not
"membership exclusion." If the implementation preserves those distinctions, the
design remains aligned with the settled frame.

## D1 - Domain model

- Pick: A, materialized derived `BELONGS_TO` from `SUPPORTS` + `Source.domain`.
  Confidence: high.

Reasoning: D1-A is the right fix because it uses the only domain signal run-3
proved reliable. `Source.domain` has full coverage and the richer Pass-1
distribution; Pass-2 page-domain has poor coverage and collapsed diversity.
The system already has the provenance structure needed to project domain from
source to entity. Reintroducing an LLM at entity-domain level would duplicate
the failed surface and make domain coverage costlier and less reproducible.

This also fits the five-rung ladder. For Remember, source provenance stays the
authority. For Relate, materialized Domain nodes and `BELONGS_TO` edges give
the graph a navigable coordinate. For Discover, multi-domain entity membership
is useful because it preserves cross-domain contact surfaces: an entity can be
seen through value-investing and psychology without choosing one intrinsic
bucket. For Learn/Create, D1 is mostly enabling infrastructure, not the
reasoning layer itself.

The main semantic caveat: under A, `BELONGS_TO` is not an intrinsic taxonomy
edge. It means "this entity is evidenced by at least one source whose primary
domain is D." That is a good coordinate, but if the UI/query layer presents it
as an essence claim, it will mislead. The blueprint should define this
explicitly, possibly as "domain attestation" language even if the edge name
stays `BELONGS_TO`.

What we missed: incidental domain inheritance is the real failure mode. A
value-investing source can mention an AI tool, and that AI entity will inherit
`value-investing`. I would not fix that with a hard threshold because rare
cross-domain mentions are often exactly the interesting signal. Instead,
materialize the edge but make strength visible to consumers: number of
conferring sources, maybe distinct source types, and maybe recency. Treat
single-source domain membership as weak but still queryable.

Sub-questions:

`via_source`: do not store a `via_source` list as the primary provenance
authority. Recover exact provenance by joining:
`Entity <- SUPPORTS - Source {domain}`. That is the canonical model and avoids
duplicating a list of source IDs on every domain edge. If the viewer or T2/T3
ranking needs a cheap sort key, store derived aggregate attributes such as
`support_count` and `first_run_id`/`last_run_id`, but keep them explicitly
recomputable. The edge should not become a second provenance ledger.

`sub_domain`: retire it for V1. Under A there is no producer for sub-domain, and
keeping the property invites consumers to rely on null/legacy noise. If later
Pass-1 grows a controlled secondary coordinate, add it deliberately as a new
field or edge with a clear producer and migration. Do not preserve a stale
attribute because it exists.

Recommendation: implement D1-A as a deterministic rebuildable projection. On
every graph sync/rebuild, derive Domain nodes from `Source.domain`, derive
`BELONGS_TO` from the `SUPPORTS` join, and remove Pass-2 page-domain as an
input. Add tests for multi-domain entities, single-source weak membership, and
full run-3 backfill producing the 11 Pass-1 domains.

## D2 - Claim layer

- Pick: Modified C. Wire `Claim` + `EVIDENCES` + `ABOUT` now, but constrain the
  extraction problem sharply and leave belief-revision edges gated. Confidence:
  medium-high.

Reasoning: C is the right architectural split. `SUPERSEDES`, `CONTRADICTS`, and
`QUALIFIES` are state-changing Learn machinery and should remain behind the
#83/#84 promotion contract. But the graph cannot keep postponing all typed
assertions and still claim to address paragraph 419. A generic `LINKS_TO` graph
is useful for associative recall, but it cannot answer "what relation is being
asserted, by whom, under what modality, and with what evidence?"

The key is to avoid making "Claim extraction" mean "turn every sentence into a
claim." At personal corpus scale, unconstrained claim extraction will probably
produce noisy, low-yield summary bullets. A constrained claim layer can be
valuable now if it obeys four rules:

1. Evidence-required: every claim must have a quoted span or equivalent source
   anchor through `EVIDENCES`. No quote, no claim.
2. Entity-grounded: subject/object/about entities must resolve to existing or
   same-compile entities. Claims should not become a shadow entity extractor.
3. Budgeted: cap claims per source, perhaps 3-7 high-signal assertions, rather
   than exhaustive extraction.
4. Predicate-controlled: `predicate_class_canonical` needs a small registry or
   controlled vocabulary. A free-form string field named "canonical" is not
   actually a controlled relationship vocabulary.

Personal-scale value of claim extraction: at 30 sources / 180 entities, claims
will not yet deliver automated discovery or robust contradiction analysis. But
they can deliver immediate Relate-by-reasoning value if the claim budget is
focused: "which sources assert X about Buffett?", "what does this source claim
about leverage?", "which assertions are conditional vs strong?" That is enough
to justify a pilot because it tests the central thesis with real data. The
payoff is not the first 100 claims; it is proving whether the extraction schema
can stay grounded and useful before the corpus grows.

Claim/LINKS_TO division of labor: coherent, with one caveat. The division is
sound if `LINKS_TO` remains associative adjacency and `Claim` is an assertion
object. They are not redundant because a claim carries polarity, modality,
condition, confidence, quote, state, and revision history. The caveat is that
query tooling must not force users to choose between two unrelated graphs. A
claim should be able to project a typed relation view for analysis while still
coexisting with `LINKS_TO` for neighborhood retrieval.

What we missed: the missing inventory item is not necessarily a graph node, but
it is a first-class ontology artifact: `PredicateClass`. The blueprint says
`predicate_class_canonical` is the controlled vocabulary, but Appendix A stores
it as a string with no visible registry. That is a weak point. The project needs
either a config file or a `PredicateClass` node/table defining canonical id,
scope, aliases, examples, and allowed subject/object expectations. Without
this, the Claim layer can silently degenerate into `LINKS_TO` with longer names.

Second missed issue: `ABOUT` is underspecified for role. The Claim row has
`subject_slug` and `object_slugs[]`, so perhaps `ABOUT` is merely an index from
claim to all participating entities. That is fine, but consumers will eventually
need to know whether an ABOUT entity is subject, object, predicate scope, or
context. Either add a role attribute to `ABOUT`, or document that role is
recovered only from Claim properties and `ABOUT` is an untyped lookup edge.

Recommendation: implement C as a feature-flagged or run-mode pilot with a small
predicate registry and hard extraction caps. Do not wire belief-revision edges
from Pass-2. Let Pass-2 only propose grounded claims. Promotion/revision remains
the only path to mutate belief state.

## D3 - T2/T3 domain-scoping

- Pick: C, with differentiated budgets for T2 and T3. Confidence: high.

Reasoning: hard domain gates violate the most important practical implication
of "domain = coordinate, not gate." Ingest is not gated, but a hard compile-time
context gate can still prevent the model from seeing cross-domain evidence at
the exact moment when new edges are born. That suppresses Discover and makes D1
errors more damaging. The right use of domain is retrieval shaping: same-domain
context should dominate the budget, but strong cross-domain matches should
remain eligible.

Same-domain weighting should be aggressive but not absolute. As a starting
policy, I would use something like:

- T2 exact/alias entity matches: search full graph; same-domain boost 2x-4x;
  reserve 60-70 percent of budget for same-domain if enough candidates exist.
- Cross-domain T2: reserve 20-30 percent for high lexical/canonical matches,
  especially if the entity is globally central or alias-exact.
- Global anchors: reserve about 10 percent for high-degree/high-confidence
  nodes or prior source-supported entities that survive normal ranking.

For T3, do not apply the same weighting mechanically. T3 is neighbor expansion;
it is where cross-domain structure becomes visible. Keep T3 open, but cap by
edge type, source proximity, and per-seed budget so popular hubs do not flood
the context. Same-domain neighbors can still be first in order, but
cross-domain neighbors should survive when they are attached to strong T1/T2
seeds.

Variant D: I would not hard-gate T2 seeds. T2 starts from Pass-1
`entity_search_keys`; if an exact entity key resolves outside the source's
primary domain, that may be a useful bridge, not a false positive. Gate-like
behavior is acceptable only for weak fuzzy matches. In other words: exact T2
matches search globally; fuzzy T2 matches are same-domain-heavy; T3 remains
open but budgeted.

What we missed: D3 needs an evaluation hook, not just a stance. Retrieval
changes can look better because they reduce context, while quietly killing
useful cross-domain links. Track at least two telemetry counters per compile:
same-domain context share and cross-domain context share, plus how many emitted
`LINKS_TO`/Claim references came from each. That gives the project a way to
tighten the coordinate as the corpus approaches critical density without doing
it blindly.

Recommendation: ratify C as the architectural stance, then implement a
parameterized ranking policy rather than a boolean `domain_scoped` flag.
Defaults should be same-domain-heavy, exact-match-global, and T3-open.

## Cross-cutting (inventory + frame)

The Source, Entity, Domain, and Claim inventory is mostly right. The edges are
also broadly right, but three clarifications matter:

1. `BELONGS_TO` should be documented as observed/attested domain membership,
   not intrinsic taxonomy. This prevents downstream consumers from treating
   inherited source domain as a truth claim about the entity.
2. The Claim layer needs a predicate-class authority. Whether this is a config
   file or graph node is secondary; the ontology needs a controlled predicate
   registry before extraction goes live.
3. `ABOUT` needs either a role attribute or a documented role recovery rule.
   Otherwise claim queries will quickly run into ambiguity.

I do not see a frame violation in the assistant's leans. D1-A honors broad
ingestion and uses graph structure as a coordinate. D2-C honors the Learn gate
by separating grounded assertions from belief mutation. D3-C is the cleanest
implementation of coordinate-not-gate.

One potential frame violation would be implementing D3-C with such aggressive
same-domain weighting that cross-domain context almost never appears. If the
budget policy produces de facto hard gating, it is still a gate. The blueprint
should call that out explicitly.

## Convergence note

I expect other reviewers to converge on D1-A; the run-3 evidence is strong and
the failure mode is clear. I also expect convergence on retiring `sub_domain`.
The `via_source` answer may split: some reviewers will prefer denormalizing
source IDs for explainability. My position is that exact provenance should stay
in the `SUPPORTS` join, with optional derived counts only.

D2 will likely be the contested decision. Reviewers focused on system purity
will endorse C; reviewers focused on current scale may argue for B until there
is a larger corpus. The synthesis should distinguish "do not wire belief
revision yet" from "do not extract grounded claims yet." I strongly agree with
the former and only partially agree with the latter: extraction should proceed,
but as a constrained pilot.

D3 should converge around C, but reviewers may differ on Variant D. The load
bearing point is not the exact percentage. It is preserving a nonzero
cross-domain budget and instrumenting the outcome.
