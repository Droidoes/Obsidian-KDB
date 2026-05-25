# Task #88 NW-4 v0.2 Review — Codex

## Convergence

The 24-domain list is directionally sound for v1. D-NW4-1's flat single-domain shape is the right default for Pass-1 cognitive load, and D-NW4-4's config-driven posture is essential. The strongest parts are the empirical-source weighting, the investing/business split, and the explicit boundary section.

The core design intuition holds: `domain` should be a coarse, stable coordinate; tags and graph edges should carry refinement and cross-cutting structure. I would keep the flat list, but tighten the contract around residual buckets, quote handling, and metadata/graph fallback behavior.

## Findings

**Finding F-1:** NW-4 contradicts the parent ingestion blueprint on `sub_domain`.

NW-4 says:

> Pass-1 LLM classifies each source into exactly one domain from a flat ~20-25-entry list. No `sub_domain` field.

But `docs/task88-ingestion-pipeline-blueprint.md` §4.1 still specifies both `domain` and `sub_domain` in Pass-1 output. Existing graph ingest also supports `domain: str | list[str]` plus `sub_domain` on `BELONGS_TO`. This is the highest-priority structural issue because implementers could faithfully follow the parent blueprint and rebuild the hierarchy NW-4 rejected.

**Finding F-2:** Quotes-as-domain is defensible only for standalone quote artifacts.

As written, `quotes` risks becoming a content-shape override for materials whose real subject is investing, philosophy, psychology, or literature. The v0.2 scope says "Standalone quotes," which is the right constraint, but D-NW4-3 should make this rule load-bearing. Quote-rich essays, speeches, books, and notes should classify by substantive subject.

**Finding F-3:** Graph-only cross-cutting is elegant but brittle for "load-bearing AI/ML" retrieval.

D-NW4-2 is architecturally aligned with graph-over-vector discipline, but relying only on graph edges assumes entity extraction and later graph compilation preserve the right bridge. That is fragile for abstract content like "LLMs as research infrastructure for biology" where the important signal may be topical rather than entity-named. The query "show me all content where AI/ML is a load-bearing topic, even when not primary" may not be answerable cleanly from graph walks alone unless Pass-1 reliably emits AI/ML entities or tags.

**Finding F-4:** `science-technology` is too broad and too similarly named to the human-readable S&T cluster.

Its scope includes applied chemistry, materials science, climate science, engineering disciplines, and generic STEM (§3.1 #8). That gives Pass-1 a plausible escape hatch for many hard cases, especially if confidence is low. The current §4 guardrail is directionally correct but should be stronger and measurable.

**Finding F-5:** `logics` is conceptually overloaded and oddly named.

Mathematics, probability, statistics, formal logic, and decision theory can live together for v1, but applied statistics will often be closer to economics, business analysis, AI/ML, or health research than to formal logic. The current ID is also unnatural in English and will feel awkward in queries.

**Finding F-6:** The Human & Society cluster is missing an explicit social-institutions bucket.

Sociology, law, education, and public policy are all forced into `geopolitics`, `history`, `psychology`, or `others`. Do not add all four now, but watch for empirical density because this is the most likely non-S&T gap.

**Finding F-7:** There are two residual buckets: `science-technology` for STEM residuals and `others` globally.

That is acceptable only if both have monitored rates. If either grows beyond a small threshold, the taxonomy is hiding missing domains. `others` should be treated as a drift signal, not a normal destination.

**Observation O-1:** Flat does not need to mean cognitively flat. The prompt can ask the LLM to internally reason broad cluster first, then emit one flat ID. That preserves D-NW4-1 without adding schema fields.

**Observation O-2:** `arts` and `food-drinks` are fine as low-frequency domains if they reflect Joseph's actual organization. Low frequency is not a defect when the category is stable and intuitive.

**Observation O-3:** `spirituality` as a religion superset is acceptable for v1, but only if the scope explicitly covers religious history/theology and not only personal practice.

## Recommendations

**Recommendation:** Amend the parent blueprint and schemas so NW-4's actual contract is unambiguous: `domain: <one enum>`, no `sub_domain` in Pass-1. If legacy GraphDB supports multi-domain/subdomain for historical reasons, mark it adapter compatibility, not the new ingestion contract.

**Recommendation:** Keep `quotes`, but tighten the rule: use `quotes` only when the source's primary unit is a standalone quotation or quote collection. Quote-rich essays, speeches, books, and notes classify by substantive subject.

**Recommendation:** Add a lightweight `topic_hints` or `secondary_domain_hints` field only if D-NW4-2 fails in evaluation. Keep it non-routing, max 3, optional, and generated from the same config. This would answer "show me AI/ML as load-bearing topic" without reintroducing multi-domain authority.

**Recommendation:** Rename `science-technology` to `applied-science-engineering`, or split out `environment-sustainability` if corpus evidence supports it. Also require Pass-1 to provide an internal reason before choosing it: "use only when no named S&T domain fits."

**Recommendation:** Rename `logics` to `math-logic` or `mathematics-logic`. Scope it as formal math, logic, probability theory, statistics theory, and decision theory. Applied statistical work should classify by the object domain unless the statistical method is the content.

**Recommendation:** Config should own more than IDs: display name, scope, inclusion examples, exclusion examples, boundary pairs, deprecated aliases, prompt rendering text, evaluation probes, and expected rollup cluster. D-NW4-4 depends on this.

**Proposal:** Add NW-5 evaluation counters for `others_rate`, `science_technology_rate`, and per-domain confusion pairs. The review concern is not just whether the list looks plausible, but whether Pass-1 collapses hard examples into residuals.

## Concrete Classification Probes

1. **Charlie Munger speech essay on incentives and human misjudgment** — `psychology` if the substance is behavioral error; `value-investing` if framed as investing method. Not `quotes`.

2. **Standalone Munger aphorism extracted from Poor Charlie's Almanack** — `quotes`, with entities/tags carrying Munger, book, investing, and mental models.

3. **Book note on Poor Charlie's Almanack** — `value-investing` or `business-management` depending dominant framing. Not `quotes`, even if quote-dense.

4. **Survey of AI for protein folding or drug discovery** — `biology` if biological discovery is the subject; `ai-ml` only if model architecture or ML method is the subject.

5. **Climate engineering or battery materials overview** — currently `science-technology`; this is exactly the pressure case that argues for stronger catch-all guardrails or `applied-science-engineering`.

## Open Questions

1. What residual-rate threshold makes `others` or `science-technology` fail? I would predeclare a benchmark threshold in NW-5.

2. Should `topic_hints` be evaluated before implementation by replaying a small probe corpus, especially AI-applied-to-X and quote-cross-section cases?

3. Is `retirement-lifestyle` empirically dense enough as a domain, or should it be a tag under `health-wellbeing`, `economy-markets`, or `value-investing` until it proves volume?

4. Should config support domain deprecation/alias migration from day one? This matters once v0.3+ renames `logics` or `science-technology`.
