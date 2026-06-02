# Codebase Realignment — External Panel Review Prompt

**Purpose:** Fire `docs/superpowers/specs/2026-06-01-codebase-realignment-panel-brief.md` at the external panel
for independent critique of an **architecture-level refactor proposal**: realigning the KDB codebase's structure
and vocabulary so the implementation reflects the (already-decided) architecture. We author; the panel
stress-tests; we synthesize.

**Panel (full, 5):** Codex · DeepSeek · Qwen · Gemini · Grok-build. Per `docs/external-review-panel.md` this is
a foundational, repo-wide fork → full panel.

**Dispatch mode — mixed, and that's deliberate:**
- **CLI reviewers with repo access (e.g. Codex, Grok-build):** you MAY (and are encouraged to) **read the
  repository read-only** to verify the brief's grounded claims against the actual code. **You MUST NOT modify
  the repository in any way** — no edits, no new files, no git operations. Produce your review **only** as your
  output file (below). This guardrail is absolute and non-negotiable.
- **Chat reviewers (DeepSeek / Qwen / Gemini chat):** the brief is self-contained — it inlines the import-graph
  facts, the relocation map, and the dependency contract. Reason from it; you need no repo access.

**Save each reply to its own file** (for synthesis + convergence tally):
- `docs/superpowers/specs/2026-06-01-codebase-realignment-review-codex.md`
- `docs/superpowers/specs/2026-06-01-codebase-realignment-review-deepseek.md`
- `docs/superpowers/specs/2026-06-01-codebase-realignment-review-qwen.md`
- `docs/superpowers/specs/2026-06-01-codebase-realignment-review-gemini.md`
- `docs/superpowers/specs/2026-06-01-codebase-realignment-review-grok.md`

---

## ─── Prompt body (paste to each reviewer; attach the brief) ───

You are one of several **independent** reviewers on a multi-model panel. The attached document
(`2026-06-01-codebase-realignment-panel-brief.md`) is an **architecture-level code review and refactor
proposal** for KDB — a personal knowledge-graph compiler that turns a raw Obsidian vault into a Kuzu graph.
Reviewers do not see each other's takes; **convergence across independent reviewers is the signal we synthesize.**

### 0. Rules of engagement

- **The architecture is decided — do not re-open it.** The target shape (two pipelines — *ingestion* and
  *compiler* — over a *graph* substrate, conducted by an *orchestrator*, with out-of-band *tools* and a *common*
  shared-infra layer; brief §1.3) is **ground truth, not under debate.** Your job is to critique whether the
  proposed refactor makes the *implementation* faithfully reflect that architecture — **not** whether the
  architecture is right.
- **Repo access (CLI reviewers only): read-only, verify, never modify.** Use it to check our grounded claims
  (the legacy-only set, the fan-in numbers, the relocation homes, the layering inversions). If you find a claim
  the code contradicts, that is a high-value catch — cite the file/line. **No repository modifications of any
  kind; review goes only to your output file.**
- **Challenge the leans; don't rubber-stamp.** The brief states leans — the A→B cut, the renames
  (`reconcile→repair`, `patch_applier→page_writer`, `ingestion→enrich`), the module homes. Agree or disagree,
  but show your reasoning.

### 1. Context (brief)

KDB just shipped `v0.5.0` (reliable orchestration). The codebase's package layout and vocabulary, however, still
date from the original monolithic `kdb_compile` era — names now mean the wrong thing or two things at once
(exhibit: `reconcile`; two files both calling themselves "the orchestrator"; `kdb_compiler/` is a stage-named
package holding *every* stage). The team is about to build the 0.6 **feeder/ingestion** subsystem directly on top
of this. The thesis: **the terminology debt IS the architecture problem**, and a release boundary is the cheapest
moment to pay it. The proposal is **one refactor in two sequential, both-mandatory phases**: **A** (fix in place —
renames, retire the legacy driver, close a Kuzu-access boundary leak, fix two layering inversions, rewrite the
stale North Star) **then B** (split the monolith into peer packages per a module-by-module relocation map).

### 2. What we want — review these (brief Part 3)

For **each**, give your position + reasoning + confidence, and flag anything our framing under-weights:

1. **The A/B cut.** Is "fix-in-place (A) then move-into-packages (B)" the right seam? Should the layering-inversion
   fix (A.4) or the single-door-to-Kuzu fix (A.3) move to B (or vice-versa)? Does **A alone** leave a coherent,
   shippable, *not-half-honest* state?
2. **Rename adjudications** (§1.4 / A.1). `reconcile→repair`, `patch_applier→page_writer`, `ingestion→enrich`,
   `source_state_update→source_state_writer`. Wrong? Better names? Anything we'll regret when *feeders* land?
3. **Relocation-map errors** (§B.2). Any module in the wrong package — especially `context_loader`
   (compiler vs graph), `resp_stats_writer` (compiler vs common), `pipeline_registry` (orchestrator vs common)?
4. **Retirement risk** (§A.2). Any path by which `kdb_compile.py`, `run_journal.py`, or `validate_last_scan.py`
   is still load-bearing on a live flow we've misread? Is excising `planner` worth bundling into A?
5. **Layering-fix approach** (§A.4). Best way to invert `source_io → ingestion.frontmatter_embedder` and
   de-couple `types` so `common` is a true leaf?
6. **CLI surface** (§B.4). Which `kdb-*` commands earn a binding; which are internal-only?
7. **Sequencing vs 0.6.** Should any of this defer *into* the feeder work rather than precede it?
8. **What's missing.** Other legacy terms, dead modules, collisions, or coupling not in our inventory.

### 3. Output format

```markdown
# Codebase Realignment — [Your model] Review

## Summary
[3-5 sentences: overall verdict on the refactor + the single highest-value catch]

## 1. A/B cut
- Position / Confidence / Reasoning / What we under-weight

## 2. Rename adjudications
- Per rename: agree / better-name / regret-risk

## 3. Relocation-map errors
- Any mis-placed module (cite the one you're most confident about)

## 4. Retirement risk
- Load-bearing-on-live concerns; planner-in-A?

## 5. Layering-fix approach
## 6. CLI surface
## 7. Sequencing vs 0.6
## 8. What's missing
[Dead code / collisions / coupling we didn't list — repo-verified if you have access]

## Convergence note
[Points you expect other reviewers to raise or contest — helps weight load-bearing vs unique catches]
```

### 4. Logistics

- **Length:** ~1500–3500 words. Depth over breadth; don't pad.
- **Tone:** direct, technical, honest. Don't soften a load-bearing concern to seem agreeable; don't inflate minor
  polish to look thorough.
- **Stay refactor-focused:** the eight questions are the point. Verifying our grounded claims (if you have repo
  access) is the strongest contribution you can make that a chat reviewer cannot.

---

**Reminder:** the architecture is decided — review the *refactor*, not the architecture. CLI reviewers: read-only,
**no repo modifications**, review to your output file only. Thank you for the review.
