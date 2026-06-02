# Task #91 Plan 1 — Review Synthesis & Decisions (2026-05-29)

Two review passes on `docs/superpowers/plans/2026-05-29-task91-plan1-kdb-compile-rebuild.md`:
1. **Workflow** (4 Claude-subagent lenses → adversarial verify): code-grounding + TDD-executability succeeded (9 verified findings, 0 false positives — caught the `single_scan` `PagePatchError` crash + provenance gap); spec-fidelity + architectural-risk lenses **failed** (agents didn't emit structured output). Folded into Plan 1 already.
2. **External panel** (Codex · Deepseek · Qwen · Grok · Gemini-agy), scoped to the two dimensions the workflow couldn't cover. Reviews: `docs/task91-plan1-review-{codex,deepseek,qwen,grok,gemini}.md`. All five verdicts: **proceed-with-changes**.

## Panel convergence

| # | Finding | Convergence | Disposition |
|---|---|---|---|
| **A** | Cross-source page-merge lost on one-element `cr` (`_merge_page_intents` merges across sources; vacuous on length-1 → last-writer-wins) | **4/5** (Grok dissent **code-refuted** at canonicalize.py:368-405) | **Accept** wiki last-writer-wins as single-user trade-off — graph stays authoritative (`SUPPORTS` edges all land); `kdb-audit` (#93) reconciles wiki↔graph drift. Document. |
| **B** | Wiki writes inside `compile_source` land before manifest commit → dirty disk on case-(a) failure | **5/5 unanimous** | **Fix:** `compile_source` = **produce-don't-write**; orchestrator owns `patch_applier` + writes at the commit boundary. |
| **C** | Collapsed `error: str` too thin for orchestrator case-(a)/(b) routing; context-snapshot read escapes the wrapper | **4/5** (Deepseek abstain) | **Fix:** add `failure_stage` + `exception_type` to `CompileSourceResult`; wrap the snapshot read. |
| **D** | Context-snapshot built internally couples core to Kuzu | **3/5** | **Fix:** add optional `context_snapshot: ContextSnapshot \| None = None` param (default None = build internally). |
| **E** | `source_hash`/`source_mtime` are orchestrator concerns leaking into the core | 2–3/5 | **Subsumed by B** — provenance + apply move to the orchestrator; core sheds both params. |
| **F** | "Circular import `CompileJob`→`SourceFrontmatter`" | **1/5** (Gemini) | **Refuted** — `SourceFrontmatter` is in `source_io.py` (not `compiler.py`) + the plan uses a `TYPE_CHECKING` guard. No runtime cycle. |

Plus document-only: Qwen's alias-singleton-rename test (one-element `cr` still hits the rename path — add a test), `source_name`-from-`source_id` rationale comment, resp_stats/in-place-`cr` partial-state note.

## Decisions (Joseph-ratified 2026-05-29)

- **Fork 1 — produce-don't-write:** `compile_source` returns `cr` + page-patches; the orchestrator (Plan 6) writes wiki pages + threads provenance at the per-source commit boundary. Resolves B + E; aligns with the spec's embed-at-commit sequencing.
- **Fork 2 — accept cross-source wiki trade-off (A):** loop does last-writer-wins; graph is the authority; `kdb-audit` (#93) is the out-of-band reconciler. (Per [[feedback_obsidian_wikilinks_are_vanity]] — wiki is a projection.)
- **Adopt regardless:** C (structured failure fields), D (optional snapshot param), the alias-rename test, document-only notes.
- **New tasks filed:** #92 (NW-9 T2/T3 redesign hypothesis), #93 (`kdb-audit` cross-store reconciler).

## What this answered ("workflow vs panel")

- **Workflow** = mechanical truth: read + executed code, caught the crash & signatures. High precision on facts. Its *architectural* lens failed, and the author's (Claude's) own manual architectural pass got **Finding A wrong**.
- **Panel** = independent design judgment: 4/5 diverse models caught the cross-source-merge loss that the correlated all-Claude approaches structurally missed; convergence filtered a false positive (F).
- **Verdict:** complementary by failure class — workflow for code-grounding, panel for design judgment + convergence signal.

## Pending

Spec Pass-2 ingress contract + Plan 1 revision per Forks 1+2 (next work unit).
