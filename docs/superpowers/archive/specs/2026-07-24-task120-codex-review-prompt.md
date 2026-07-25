Design review request — Task #120 spec v1.0 (Pass-2 wikilink-emission restoration).

Repo: /home/ftu/Droidoes/Obsidian-KDB, branch main (post-#119 merge, HEAD 9a320fd).

Context: at #119's Phase-5 live cohort, deepseek-v4-flash's concept-page wikilink emission collapsed 0.45 → 0.08 links/page (overall 1.30 → 0.68) between prompt 3.0.0 and 4.0.1, while gpt-5.4-mini stayed baseline-normal on the identical contract (concept 0.59 → 0.68). Code-verified mechanism: the 4.0.1 proposal schema (`compiler/schemas/proposal_response.schema.json`) dropped both schema-level link mentions the 3.0.0 schema carried — the top-level "wiki-native … [[wikilinks]]" phrasing and the `body` field's wikilink instruction (3.0.0: "Use Obsidian wikilink syntax `[[slug]]` inline whenever you reference another page in this response or in EXISTING CONTEXT"; 4.0.1: no `body` description at all). `link_density` is a scored leaderboard axis (0.30 of the graph block).

The spec (read it first, it is the review target):
  docs/superpowers/archive/specs/2026-07-24-task120-pass2-wikilink-emission-restoration.md

Ratified-by-Joseph decisions to review: D1 = B+ (restore both 3.0.0 mentions + an explicit linking expectation sentence — exact text in the spec); D2 = PASS2_PROMPT_VERSION 4.0.2; D3 = split `entity_search_key_resolution` into resolution + novelty, both watched-not-scored (the cold-start conflation fix); D4 = deepseek-only re-fire with acceptance bands (concept ≥0.4/p, overall ≥1.2/p) and a falsification criterion. Plus a schema canary test pinning the wikilink instruction against future silent removal.

Focus areas:
1. The B+ text itself (spec §D1) — is the added sentence well-formed for a schema-literal model? Any way it induces over-linking that damages the graph (noise links, self-links, links-to-current-summary)?
2. The D3 split — is resolution+novelty the right decomposition for the cold-start conflation, and is keeping both watched-not-scored correct while the graph is young?
3. The D4 acceptance design — are the bands (concept ≥0.4/p, overall ≥1.2/p) the right restoration criterion given n=1 runs and ±10-15% observed run variance? Is deepseek-only sufficient evidence?
4. Anything the spec misses (e.g., does the metric split touch the pass2 leaderboard board surface, not just measurements.json? Does the schema edit interact with the golden SHA guard or replay dispatch?).

Verdict format: GO or REVISE, with numbered findings (Critical/Important/Minor, file:line, concrete fix). Write your review to:
  docs/superpowers/archive/specs/2026-07-24-task120-pass2-wikilink-emission-restoration-review-codex.md
