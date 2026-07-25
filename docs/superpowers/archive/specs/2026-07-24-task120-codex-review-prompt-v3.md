Design review request, round 4 — Task #120 spec v1.3 (Pass-2 wikilink-emission restoration).

Repo: /home/ftu/Droidoes/Obsidian-KDB, branch main (post-#119 merge, HEAD 9a320fd).

Your round-3 review (docs/superpowers/archive/specs/2026-07-24-task120-pass2-wikilink-emission-restoration-review-codex-v3.md) returned REVISE with 2 Important + 1 Minor. All three were controller-verified (benchmark/runs/ is indeed gitignored at .gitignore:42; the replay probe confirms a 4.0.0 `summary-callout` concept is semantic-valid today; the ledger rows were indeed stale). The revised spec:
  docs/superpowers/archive/specs/2026-07-24-task120-pass2-wikilink-emission-restoration.md

What changed in v1.3 — verify each of your fixes:

1. **R3 F1 (upper audit executable):** sample unit is now the resolved EDGE — candidates `(source_page_slug, target_slug)` with canonical-concept sources, sorted `outdegree DESC, source_page_slug ASC, target_slug ASC`, `audited_edges = min(20, candidate_edges)`, pass = `supported/audited ≥ 0.90`. Evidence authority is the concrete final page occurrence that produced the stored outgoing set — the analysis persists its `compiled_source.source_id`, source/target slugs, raw-source excerpt, and verdict (acknowledging LINKS_TO stores no raw source_id). Persistence moved to a tracked path: `docs/superpowers/evaluations/2026-07-24-task120-<model>-<run-id>.md` (nothing force-added into gitignored benchmark/runs/).
2. **R3 F2 (D5 replay policy):** declared RETROSPECTIVE across the whole 4.x era (validator bugfix — the `summary-` namespace was always system-owned; the `startswith("4.")` dispatch stays). New tests: 4.0.0 replay fixture with a `summary-foo` concept → proposal-schema OK, `semantic_ok=False` with `slug_collision`; existing valid 4.x fixtures stay green; bridge tests pin the guard on the POST-COERCION planned slug (`SUMMARY--Foo` → `summary-foo` must reject).
3. **R3 F3 (ledger):** `docs/TASKS.md` now records #118's three-way decomposition scope and #120's spec-v1.3 link + D1–D5 scope with the stale promotion wording removed — applied in the worktree, rides the first commit.

Also confirm no regressions were introduced: the D4 equations/gates and D1/D2/D3 content are unchanged from v1.2 (which you accepted modulo R3's findings).

Verdict format: GO or REVISE, with numbered findings (Critical/Important/Minor, file:line, concrete fix). Write your review to:
  docs/superpowers/archive/specs/2026-07-24-task120-pass2-wikilink-emission-restoration-review-codex-v4.md
