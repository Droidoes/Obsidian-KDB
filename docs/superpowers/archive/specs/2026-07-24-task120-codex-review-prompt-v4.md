Design review request, round 5 — Task #120 spec v1.4 (Pass-2 wikilink-emission restoration).

Repo: /home/ftu/Droidoes/Obsidian-KDB, branch main (post-#119 merge, HEAD 9a320fd).

Your round-4 review (docs/superpowers/archive/specs/2026-07-24-task120-pass2-wikilink-emission-restoration-review-codex-v4.md) returned REVISE with 1 Important + 1 Minor, and a closing recommendation: fix those two, then the design is ready for ratification. Both were absorbed exactly as specified. The revised spec:
  docs/superpowers/archive/specs/2026-07-24-task120-pass2-wikilink-emission-restoration.md

What changed in v1.4 — verify each of your fixes:

1. **R4 F1 (audit population):** the upper audit's candidate set is now ALL resolved `LINKS_TO` edges counted by `overall_resolved_density` (limited to the current cohort's final compiled-page occurrences) — no longer concept-origin-only, so summary/article edges that cause the `≥1.78` trigger are inside the sampled population. Sort `source_outdegree DESC, source_page_slug ASC, target_slug ASC`; `audited_edges = min(20, candidate_edges)`; pass = `supported/audited ≥ 0.90`; `source_page_type` persisted per edge; final-page-occurrence evidence authority unchanged.
2. **R4 F2 (ledger label):** `docs/TASKS.md` #120 row now reads "Candidate design v1.4 (awaiting ratification)" — the premature "Ratified design" wording is gone.

No other content changed since v1.3 (which you accepted modulo R4's findings).

Verdict format: GO or REVISE, with numbered findings (Critical/Important/Minor, file:line, concrete fix). Write your review to:
  docs/superpowers/archive/specs/2026-07-24-task120-pass2-wikilink-emission-restoration-review-codex-v5.md
