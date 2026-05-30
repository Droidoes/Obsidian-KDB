# Task #91 v0.1 — External Review Fire-Prompt (Panel β)

**Purpose:** Fire the v0.1 `kdb-orchestrate` blueprint (`docs/task91-kdb-orchestrate-blueprint.md`) at panel β (2 CLI reviewers, fast-pass). This task is the v1 simplification of Task #88 Components #3 (Trigger) + #6 (Orchestrator) — collapses elaborate event-emission/batching design into a manual-trigger + manifest-diff orchestrator appropriate for single-user infrequent workload.

**Dispatched:** 2026-05-27 evening (to be fired by Joseph)
**Panel scope:** β — Codex + Deepseek only (2-reviewer fast-pass per `docs/external-review-panel.md` §4 "medium-stakes single decision" sizing). Joseph called this scope 2026-05-27 evening because:
- Task #91 is a v1 simplification, not a new architectural fork
- 8 of the 9 substantive decisions (D-91-1..D-91-8) already ratified pre-blueprint
- One genuine OQ (OQ-91-1) is the load-bearing design question reviewers must weigh in on

**Target panel:**
- **Codex** — CLI (panel incumbent, default reviewer since Round 5)
- **deepcode CLI / Deepseek** — CLI (panel incumbent; clean across Task #87/#88/#89/#90 reviews)

**Response files (one per reviewer):**
- `docs/task91-v0.1-review-codex.md`
- `docs/task91-v0.1-review-deepseek.md`

---

## ─── Prompt body ───

You are reviewing **Task #91 v0.1 — the `kdb-orchestrate` E2E ingestion-orchestrator blueprint** for the Obsidian-KDB project (`docs/task91-kdb-orchestrate-blueprint.md`). The blueprint specifies a thin orchestrator CLI that wires `[optional] feeders → extended kdb_scan → kdb-enrich (Pass-1) → kdb-compile (Pass-2 + graph sync) → kdb-clean orphans`. It also specifies a minimal `kdb_scan.py` extension to walk multiple scan roots (KDB/raw + vault-in-place) under a unified manifest.

This is **both** an architecture review (does the simplification cover the v1 surface without leaving load-bearing gaps?) and an implementation-readiness review (is the workflow algorithm + error handling + per-root scope-config specified well enough for the next phase to start TDD?). Both dimensions matter — please address each.

### 1. REPO-MODIFICATION GUARDRAIL (CRITICAL — read first)

Create EXACTLY ONE file in this CLI session. Your output file path depends on your reviewer identity:

- Codex:        `docs/task91-v0.1-review-codex.md`
- deepcode CLI: `docs/task91-v0.1-review-deepseek.md`

Do NOT modify, create, or delete any other files in the repository.
Do NOT modify code, schemas, configuration, blueprints, or other docs.
Do NOT propose implementation patches or write code.

Your entire CLI session output must be confined to producing your single review file. Violating this guardrail (e.g., editing other files, committing changes, modifying code) results in de-selection from future review cycles per the one-strike rule (`docs/external-review-panel.md`).

Both reviewers have clean track records (Codex from Round 5 onward; Deepseek across Task #87/#88/#89/#90). This review continues under the same discipline.

### 2. Project context (brief)

**The system.** Obsidian-KDB compiles Joseph's raw markdown sources into a knowledge graph (Kuzu GraphDB). The pipeline has two ends:
- **End A = compile pipeline** (mature) — `kdb-compile` reads source markdown + manifest state, fires Pass-2 LLM, writes wiki pages + GraphDB updates via the producer-contract pipeline (`docs/reference/graphdb-kdb-producer-contract.md`).
- **End B = ingestion pipeline** (Task #88 family, in design) — multi-source feeder framework that gets sources into the vault + enriches them for compile consumption.

**Where Task #91 fits.** End B's v1 minimum-viable shape per Joseph's 2026-05-27 simplification: a single command (`kdb-orchestrate`) runs the full end-to-end pipeline on demand. No watchers, no scheduled triggers, no elaborate event-emission. Just scan-the-vault → diff-against-manifest → for-each-new-or-changed run enrich + compile + update-manifest → final `kdb-clean orphans` cleanup.

**Lineage.** Task #88 v0.2 blueprint specified Component #3 (Trigger) with filesystem-watching + 8-event lifecycle taxonomy + batching, and Component #6 (Orchestrator) as a separate thin entry-point. Task #91 collapses both into one task per the principle that v0.2's #3 design was over-engineered for single-user infrequent workload (`[[feedback_no_imaginary_risk]]`).

**Current state of relevant code:**
- `kdb_compiler/kdb_scan.py` — already implements scan + manifest-diff for `KDB/raw/` only (read this file to understand what's being extended, not rewritten)
- `kdb_compiler/source_state_update.py` — manifest writer (sole writer, schema v3.0 per Task #73 Phase D)
- `kdb_compiler/kdb_clean.py` — `kdb-clean orphans` (Task #67/#68)
- `~/Obsidian/KDB/state/manifest.json` — current manifest at v3.0 (source-state-only ledger)
- `kdb-enrich` CLI — Pass-1 enrichment (Task #89)
- `kdb-compile` CLI — Pass-2 + graph sync (mature)

### 3. The 8 ratified decisions (D-91-1..D-91-8) — do NOT re-litigate

Listed in blueprint §2. Background:
- D-91-1: single unified `manifest.json` (no rename, no relocation; schema already path-keyed per D-88-1)
- D-91-2: `.md`-only file-type hard rule
- D-91-3: orphan-cascade policy (a) hands-off at scan-time
- D-91-4: `kdb-clean orphans` as final step of every E2E run
- D-91-5: command name `kdb-orchestrate` (not `kdb-ingest`) per `[[feedback_name_must_match_contents]]`
- D-91-6: #91 subsumes #88 Components #3 + #6
- D-91-7: real-time/scheduled triggering OUT of v1
- **D-91-8: fail-fast at first source failure** — Joseph call. If any source fails Pass-1 enrich OR Pass-2 compile, abort the run immediately. No skip-and-continue. Joseph's rationale: debuggability (first error caught immediately), manifest consistency (no partial state), simplicity (no error-aggregation logic). Trade-off captured for revisit (blueprint §2).

These are ratified — please do not propose alternatives unless you've found a genuine load-bearing flaw in the design rationale itself (not just preference differences).

### 4. What to focus your review on

**A. The v1 simplification soundness (blueprint §1).** Does the collapse of #3 + #6 leave any load-bearing gap that the v0.2 elaborate design covered? Specifically:
- Is manifest-diff sufficient as a substitute for the 8-event lifecycle taxonomy?
- Are there any v1 use cases where filesystem-watching or batching would be load-bearing despite the single-user manual-trigger assumption?
- Does the §11 v2+ roadmap correctly identify the trigger conditions for re-introducing v0.2's complexity?

**B. The workflow algorithm (blueprint §4 pseudocode).** Read it carefully against the project's existing kdb_scan / kdb-enrich / kdb-compile / source_state_update / kdb-clean orphans behaviors. Find:
- Sequencing bugs (e.g., does Step 4 process NEW + CHANGED in the right order? Does Step 6 DELETED handling correctly precede or follow Step 7 cleanup?)
- Atomicity assumptions that don't hold (e.g., source_state_update is atomic per source — is that actually true in the current codebase?)
- Edge cases (e.g., what if a source is BOTH MOVED AND CHANGED — does the algorithm handle this? `kdb_scan.py` Phase B/C/D already classifies, but the orchestrator may need to handle multi-classification)
- Behaviors the existing kdb_scan/kdb-enrich/kdb-compile expose that the orchestrator's signature assumes

**C. Per-root scope-config and MOVED detection (blueprint §5).** The scan-roots config (§5.1) is a new schema. Find:
- Are the default excludes for vault-in-place root (§6.1: `KDB/`, `.obsidian/`, `.trash/`) complete? Anything else that would create circular/noisy ingestion?
- §5.4 D-91-9 candidate: MOVED detection scoped per-root vs cross-root. Reviewer take: which way?
- Is the `scope_relative_to: "vault"` field useful or noise? (Currently set to the same value for both roots in the example.)

**D. OQ-91-1 — source-retraction journal (load-bearing).** This is the most important OQ for reviewers. When a source is DELETED from the vault:
- (a) Write a replayable journal event (Task #68 cleanup-event pattern) so `graphdb-kdb rebuild` doesn't re-introduce the source from old compile journals
- (b) Direct manifest+graph removal — simpler but `graphdb-kdb rebuild` would resurrect the source

Task #68's history (Task #67 → #68 arc): non-replayable cleanup ALWAYS resurfaced as a bug. Read `docs/archive/tasks/task68-cleanup-retraction-event-blueprint.md` for the precedent. Reviewer take: (a), (b), or a third option you see? What's the implementation cost of (a) vs (b)? Does (a) extend the existing cleanup journal schema or introduce a new event type?

**E. The other 6 OQs (OQ-91-2..7, blueprint §9).** Each has an assistant lean. Confirm, challenge, or propose alternatives:
- OQ-91-2: scan-roots config in separate `state/scan_roots.json` vs nested in manifest config block
- OQ-91-3: MOVED detection per-root (D-91-9 candidate)
- OQ-91-4: per-run summary `state/last_orchestrate.json` — useful or noise?
- OQ-91-5: unknown-feeder name → error vs warning
- OQ-91-6: cleanup empty-set (0 orphans to clean) — exit 0 with report, or any other behavior?
- OQ-91-7: re-entry safety — should `kdb-orchestrate` add a lock-file despite single-user assumption?

**F. CLI shape and exit codes (blueprint §3).** Are the flags right? Are the exit codes (1-6) actually useful for scripting, or should they be collapsed to 0/1? Any flag that should exist in v1 but doesn't? Any flag that's there but shouldn't be?

**G. Error handling under D-91-8 fail-fast (blueprint §7).** Joseph called fail-fast. Does the §7.2 manifest-consistency invariant ("manifest reflects all sources processed BEFORE the failing source") actually hold given the existing source_state_update.py atomic-write behavior? Is the §7.3 "no partial-run journal" claim load-bearing or accidental? Any failure scenario that produces partial graph state that contradicts the manifest's known-good guarantee?

**H. Feeder contract (blueprint §8).** v1 minimal contract: any executable script that writes into `KDB/raw/<feeder-name>/`. Is this contract too loose? Too restrictive? Will the orchestrator's `--feeders=NAME[,NAME...]` correctly handle feeders that produce no output (no error, just nothing changed)?

### 5. Output format for your review file

Mirror the structure used in `docs/archive/tasks/task90-v0.1-review-codex.md` (or your prior review files). Suggested sections:

```markdown
# Task #91 v0.1 Blueprint — [Reviewer Name] Review

## Summary
[1-paragraph overall assessment + verdict on simplification soundness]

## Findings
### F-1: [Title] (severity: critical/high/medium/low/probe)
[What you found, where in the blueprint, why it matters, suggested resolution]

### F-2: [Title] (severity: ...)
[...]

## OQ takes
### OQ-91-1 (source-retraction journal)
[Your take with reasoning]

### OQ-91-2..7
[Brief takes on each]

## Probes / questions
[Anything you couldn't fully assess from the blueprint alone — questions for Joseph or the assistant]

## Suggestions for v0.2 fold
[Concrete amendments you'd recommend, ranked by stakes]
```

Use severity labels honestly:
- **critical** — the design as-written has a load-bearing flaw (e.g., manifest can end up in inconsistent state under D-91-8); v0.2 MUST address
- **high** — significant gap or wrong choice that should be addressed in v0.2 (e.g., OQ-91-1 wrong default)
- **medium** — design improvement that would meaningfully strengthen v1 (e.g., default excludes incomplete)
- **low** — polish or naming or doc clarity
- **probe** — clarifying question that may or may not be a finding pending the answer

### 6. Logistics

- **Length target:** 1500-4000 words. Past v0.1 reviews ran 2000-3500 words; that range is appropriate for this scope.
- **Tone:** direct, technical, honest. Don't pad findings to look comprehensive; don't underclaim load-bearing issues to seem agreeable.
- **Cross-references:** when referencing existing code or other blueprints, cite the file path (and line if helpful). When referencing decisions, use the D-91-N identifier.
- **Convergence transparency:** if you suspect your finding overlaps with what other reviewers might raise, say so — the synthesizer values that signal.

---

**Reminder:** ONE output file at the path matching your reviewer identity. No other repo modifications. Thank you for the review.
