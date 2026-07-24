Design review request, round 2 — Task #120 spec v1.1 (Pass-2 wikilink-emission restoration).

Repo: /home/ftu/Droidoes/Obsidian-KDB, branch main (post-#119 merge, HEAD 9a320fd).

Your round-1 review (docs/superpowers/specs/2026-07-24-task120-pass2-wikilink-emission-restoration-review-codex.md) returned REVISE with 3 Important + 1 Minor. All four findings were controller-verified against the code (the schema-wins-over-system-prompt precedence at `compiler/prompts/KDB-Compiler-System-Prompt.md:65,123`, the final-graph resolution computation at `compiler/kpi/graph.py:171-176`, the intake dangling-skip at `kdb_graph/intake.py:345-375`, and the loader at `compiler/prompt_builder.py:91`). The revised spec:
  docs/superpowers/specs/2026-07-24-task120-pass2-wikilink-emission-restoration.md

What changed in v1.1 — verify each of your fixes:
1. **F1 (D4 gate):** now gates on resolved edges — `graph.scored.link_density ≥ 1.2` + resolved concept outgoing edges per canonical concept ≥ 0.4 (deepseek canary); safety conditions (zero self-links, zero links-to-current-summary, dangling rate ≤ the 3.0.0 run's ~5%, upper investigation band ~1.78 with semantic sample audit); acceptance analysis persisted as a committed artifact with numerators/denominators.
2. **F2 (D3):** Joseph picked Path 1 — `entity_search_key_novelty` dropped entirely; the existing metric is re-documented as final-graph realization (not extraction quality); the three-way decomposition (pre-existing / materialized / unresolved, via canonical `first_run_id`) deferred to #118.
3. **F3 (B+ wording + gpt guard):** the amplification sentence is constrained to authoritative targets ("already has a page in this response or EXISTING CONTEXT") with explicit no-invent / no-self-link / no-current-summary guardrails; D4 now includes a gpt non-regression run (≥1.5 historical band) alongside the deepseek canary.
4. **F4 (canary):** pins both schema surfaces through `prompt_builder.load_response_schema_text()` + `PASS2_PROMPT_VERSION == "4.0.2"` in one provenance suite.

Verdict format: GO or REVISE, with numbered findings (Critical/Important/Minor, file:line, concrete fix). Write your review to:
  docs/superpowers/specs/2026-07-24-task120-pass2-wikilink-emission-restoration-review-codex-v2.md
