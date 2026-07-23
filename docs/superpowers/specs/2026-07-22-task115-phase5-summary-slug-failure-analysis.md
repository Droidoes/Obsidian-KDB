# Task #115 Phase-5 finding — summary-slug gate failures: first-principle analysis + root-cause proposal

**Date:** 2026-07-22 (v1.0) · revised 2026-07-23 (v1.1) · **Author:** Kimi (for Joseph + Codex design review)
**Status (v1.1):** **Disposition RATIFIED by Joseph 2026-07-23 — close #115 with an explicit Phase-5 waiver; the root-cause fix ships as #119** (normalization-boundary design, scope seed in §5). The *design* itself is NOT ratified — #119 gets its own architecture cycle. Codex R1 absorbed (§6); v1.0 errors corrected (§2, §4).
**Evidence:** Phase-5 comparison cohort (anchor `782120b`, Gate 4) vs Phase-0 baseline (`e9ca323`), corpus 36 sources, models deepseek-v4-flash + gpt-5.4-mini.
**Review:** Codex R1 `docs/superpowers/specs/2026-07-22-task115-phase5-summary-slug-failure-analysis-review-codex.md` (verdict: revise before ratification — root issue broader than the summary slug).

---

## 1. Problem statement

The Phase-5 comparison runs each **quarantined exactly one source** — the first Pass-2 quarantines these two models have ever produced on this corpus:

| Run | Source | Model authored | Gate expected (derived) | Outcome |
|---|---|---|---|---|
| deepseek 3.0.0 | `GraphRAG for Adaptive KB - Gemini3.1.md` | `summary-graphrag-for-adaptive-kb-gemini31` | `summary-graphrag-for-adaptive-kb-gemini3-1` | retry → same deviation → quarantine (`validate`/`SemanticCheckError`) |
| gpt-5.4-mini 3.0.0 | `what's React and Tailwind.md` | `summary-whats-react-and-tailwind` | `summary-what-s-react-and-tailwind` | retry → same deviation → quarantine (`validate`/`SemanticCheckError`) |

Both deviations are the **same class**: the model *deletes* punctuation (`.` / `'`) instead of *converting it to a hyphen separator*.

**The "we've never had failures before" observation is evidence, not luck.** The old contract had **no exact-match gate** on the summary slug — and the baseline runs (prompt 2.0.0) emitted the **identical deviations**, which passed silently:

| Baseline run | Source | Emitted summary_slug (parsed_summary) | Verdict then |
|---|---|---|---|
| deepseek 2.0.0 | `…Gemini3.1.md` | `summary-graphrag-for-adaptive-kb-gemini31` | clean (ungated) |
| gpt 2.0.0 | `what's React and Tailwind.md` | `summary-whats-react-and-tailwind` | clean (ungated) |
| gpt 2.0.0 | `…Gemini3.1.md` | `summary-graphrag-for-adaptive-kb-gemini3-1` | clean (correct) |

So the deviations are **stable, reproducible model behaviors on punctuation-bearing stems** — the same models make the same mistake at 2.0.0 and 3.0.0, and they repeat it on retry. The new exact-match gate did not create a failure; it made an existing behavior visible, classified it correctly (`validate` stage, zero bad writes), and disposed of it at the cost of a retry plus that source's payload **for that run** (corrected failure semantics in §2.3).

**The Phase-5 gate result, stated plainly.** The ratified gate (blueprint §Phase 5; audit-findings §D): *"quarantine/retry/recovery KPIs stable; graph-KPI deltas enumerated (not hidden) on canonical-collision cases."* Result: quarantine 0 → 1 per model, plus one wasted retry per model — **the KPI gate FAILED.** These deltas are not the canonical-collision graph deltas the gate carves out. (v1.0 called them "explained deltas" — that reading is retracted; Codex F1.)

The system **worked as designed**. The open question is whether the *design's disposition* for this deviation class — author-and-gate with reject/retry/quarantine — is the right one.

## 2. First-principle analysis

Our first principle (North Star): **the model proposes; Python disposes.** Its #115 sharpening ("derivation-first"): **Python owns everything mechanical; the LLM's contract shrinks to what only it can author.** Anything Python can compute deterministically, Python computes; the model is never trusted with it.

1. **The summary slug is 100% mechanical.** `expected_summary_slug(source_id)` derives it from the filename stem with certainty: slugify (lowercase, ASCII-fold, non-alphanumeric runs → one `-`) → 112-char budget → `summary-` prefix. There is no judgment in it. Python *already knows the answer* — the model's emission adds zero information.
2. **The cohort evidence says models cannot reliably perform this computation.** Two different production models, two different punctuation forms, identical failure class, systematic across baseline/comparison *and* across retry. This is not noise and not a prompt-clarity issue alone: it is a probabilistic system being asked to do a deterministic transform. Measured: **1/36 = 2.8% of sources quarantined per run in this cohort.** Cross-model and retry recurrence demonstrates systematic *risk*; the general prevalence is **unestimated** (corrected per Codex — v1.0's "~3% if this generalizes" presented an unestimated extrapolation).
3. **Author-and-gate on a mechanical field is a category error.** The gate enforces *uniqueness of one reproducible answer* — a legitimate need. The slug is not decoration: it is the **wiki filename/path, the graph entity identity, the wikilink target namespace, the manifest identity, and the replay identity** — identity across those five stores IS its function (corrected per Codex — v1.0's "no functional effect beyond uniqueness" understated this). But enforcing uniqueness by *rejecting an otherwise-good payload* and asking the model to recompute a value Python already holds is the wrong disposition: it costs a retry (~2× tokens on that source) and, on repeat failure, **excludes the entire source's candidate payload from that run's commit** — pages, bodies, concepts — over a naming form. (Corrected failure semantics per Codex: a compile failure marks the source `error_compile` and skips its candidate commit — `orchestrator/kdb_orchestrate.py:754-770`. In a fresh cohort graph the source is absent from that run's wiki/graph/manifest; in an existing KB, **previously committed content is NOT deleted**. v1.0's "deletes the entire source's content from the knowledge base" was wrong for the steady-state case.)
4. **On "both forms are acceptable":** true, and beside the point. The gate never claimed `gemini3-1` is *better* than `gemini31`; it claims the system needs *exactly one* answer, computable by anyone. The strictness is the feature; the specific rule is conventional. What the failures show is that the strictness should be *enforced by ownership* (Python resolves), not *by rejection* (model quarantined).

**Root cause, restated per Codex R1 (verified accurate).** v1.0 framed the defect as "model authorship of a Python-derivable summary slug." That is one *instance* of the broader defect: **canonical representation is enforced at the raw model-response boundary, before any deterministic semantic normalization stage exists.** Today the same strict schema both describes the model's raw response and stands in for the canonical representation (`compiler/schemas/compiled_source_response.schema.json:37-42` requires `slug` on every raw page), and the pipeline order is recover-JSON → strict canonical schema → exact-match semantic check → retry (`compiler/compiler.py:309-475`) — raw representation is validated too early. The governing rule for the fix:

> **Reject ambiguity, not harmless representational differences. If Python can deterministically map an LLM proposal to exactly one valid meaning, normalize it and continue. Reject only when there is no valid interpretation, more than one plausible interpretation, information loss, or a collision.**

Canonical exactness remains mandatory — at the **output** of Python's normalization boundary, not at the raw-response boundary. For the summary slug specifically the resolution authority is unique and deterministic: the one `page_type == "summary"` page + the current compile unit's `source_id` jointly determine exactly one valid slug (`expected_summary_slug(source_id)`), regardless of the punctuation form the model proposed. That is resolution by **identity authority** (role + provenance), never string similarity.

## 3. Options (v1.0, annotated per Codex R1)

### Option A — derive-and-stamp (v1.0 recommendation)

Python owns the summary slug outright: the model emits its best-effort slug (preserved as signal), the runner stamps `expected_summary_slug(source_id)` post-parse, a `summary_slug_deviation` measure-finding keeps the error signal as a *metric*, the semantic gate keeps the count check, and a scoped mechanical propagation renames the emitted variant → stamped value across body wikilinks.

**Codex R1 annotation:** survives as the summary-field **instance** of the normalization boundary (§2's governing rule), with three corrections:
- Keeping `slug` **required** in the raw schema only fixes the observed mode — a missing/malformed/non-string slug still schema-fails before stamping ever happens. The proposal contract must decide the field's presence deliberately (§5 item 4). A field should not remain required in model output *solely* to manufacture a quality metric (Codex telemetry note).
- v1.0's "post-canon invariant becomes trivially true" is **retracted**: against a stale/hostile alias ledger, the canonicalize guard (`compiler/canonicalize.py:424-457`) + post-canon invariant (`compiler/compiler.py:717-736`) remain the fail-closed pair protecting summary identity. #119 must decide whether system-resolved summary identities bypass alias resolution or stay fail-closed against any ledger operation.
- The body-wikilink propagation must be **deterministic reference resolution**, not prose rewriting: parsed wikilink target tokens only; display aliases + heading suffixes preserved; prose/code spans byte-identical; one old target → one canonical target; collision or multiple plausible targets → reject; re-validate all resulting links (Codex F6).

### Option B — prompt hardening (mitigation, orthogonal)

Punctuation-specific worked examples (`Gemini3.1` → `gemini3-1`; `what's` → `what-s`). Cheap, bumps the prompt version, probably fixes the two observed stems; does not eliminate the class. Useful as an orthogonal quality lift for concept slugs and body wikilinks, where the model *must* keep naming things. **Codex boundary:** do NOT generalize the two summary examples into global concept-slug normalization rules — concept identity is semantic (version dots, apostrophes, `C++`, `C#` carry meaning); a concept slug is normalized/resolved only when an authoritative context yields one target, otherwise preserved or rejected as genuinely ambiguous.

### Option C — tolerant gate (rejected; Codex F4 confirms)

"Normalization-equivalent" acceptance reintroduces model-dependent identity and breaks exactly what the strictness protects. Codex sharpens the rejection: **no** general edit-distance, punctuation-blind comparison, or probabilistic equivalence anywhere in the design — equivalence requires deterministic authority (role, provenance, registry, structural invariant), never similarity.

## 4. Disposition (RATIFIED by Joseph, 2026-07-23)

Joseph's call, with Codex R1 on record: **close #115 with an explicit Phase-5 waiver; file #119 for the root-cause fix.**

- **The waiver (explicit):** the Phase-5 comparison cohort did **NOT** satisfy the ratified KPI gate (quarantine/retry moved). Joseph accepts this as **temporary production behavior** until #119 lands: punctuation-stem sources may burn a retry and quarantine out of a run (measured 2.8%/run on this cohort corpus, two production models). The behavior is fail-closed — zero bad writes; the cost is retry spend + that source's absence from the run.
- **What #115 still proved:** the gate machinery works exactly as designed — typed telemetry (`failure_stage: validate`, `SemanticCheckError`), correct classification, zero bad writes, prompt-version + SHA stamps verified on both comparison runs, Pass-1 zero quarantines in both.
- **Why this path:** #119 gets the full design space (§5) in its own architecture cycle; a scoped amendment inside #115 would have pre-committed to the summary-field slice under closure pressure. Codex's condition for this disposition — Joseph explicitly accepting the failed gate as temporary production behavior — is met by this ratification.

## 5. #119 scope seed — the normalization boundary (root-cause fix)

**Title:** Pass-2 normalization boundary — proposal contract vs canonical contract (reject ambiguity, not representation).

The full root-cause fix, per Codex R1 (all items required for #119's architecture pass):

1. **Ratify the governing rule** (§2) as a North-Star-level principle; update `docs/CODEBASE_OVERVIEW.md` **before code** — it currently records the summary slug as "fully model-authored including its slug" and defines no proposal-vs-canonical boundary.
2. **Two logical contracts** (physical form = implementation option, item 3):
   - **Proposal contract** — decides whether Python has enough structure and semantic evidence to interpret the response; may accept harmless representational variation where a field-specific policy resolves one meaning deterministically.
   - **Canonical contract** — exact; the only shape allowed to reach canonicalization, persistence, wiki, manifest, run journal, graph.
   - **Processing order:** model response → recover JSON → parse proposal → structural sufficiency checks → deterministic normalization + identity resolution → strict canonical schema + semantic validation → canonicalization → post-canonicalization invariant validation → write.
3. **Implementation-option selection (Joseph's pick at #119 architecture):**
   - **Option 1 — in-place proposal normalizer.** Dedicated post-parse stage applies field-specific deterministic normalizers, then the existing strict gates. Lowest implementation cost; risk of ad-hoc accretion unless every rule carries explicit authority + ambiguity policy + test; highly reversible.
   - **Option 2 — explicit proposal schema + canonical schema.** Tolerant raw-boundary schema; strict canonical schema; a typed normalization step as the only bridge. Moderate cost; makes the trust boundary a versioned artifact.
   - **Option 3 — typed intent decoder.** Raw JSON → proposal-specific types → field-owned adapters → canonical domain types. Strongest long-term ownership; highest cost (Codex: potentially disproportionate — evaluate against actual field-audit findings).
4. **Contract-wide per-field audit** (the summary slug is evidence, not the whole scope). For every current Pass-2 field: who owns the meaning (model / Python / shared) · what semantic information it carries · which proposal variations are harmless (enumerated, evidence-backed) · the canonical form · the authority that proves equivalence (role / source / registry / context / none) · when normalization is forbidden (ambiguity / collision / loss / missing meaning) · what telemetry records the decision. Every existing rejection gate gets classified: semantic/structural failure (stays fail-closed) vs representational difference (normalize deterministically). The audit need not implement every coercion — it must produce the classification.
5. **Summary-slug resolution:** authority = the unique `page_type == "summary"` page + `source_id` (role + provenance), never string similarity. Open question to answer in the blueprint: does the summary `slug` stay in the proposal contract at all — and if it leaves, what may bodies link *to* (prompt-injecting the canonical slug remains a ratified non-goal from #115)?
6. **Exact canonical invariants kept:** normalized object must still contain exactly one summary whose slug equals `expected_summary_slug(source_id)`; post-canonicalization re-validation stays load-bearing. Decide: system-resolved summary identities bypass alias resolution entirely, or remain fail-closed against any alias-ledger operation. Body-link resolution follows the same deterministic identity policy (§3 Option A annotation).
7. **Telemetry:** every normalization decision records the rule applied, the raw value (when safely capturable), the canonical value, and the authority used — in telemetry / the archived raw response, never in the canonical product contract. The `summary_slug_deviation` metric is the summary-field instance.
8. **Regression fixtures:** the two Phase-5 quarantined sources (`…Gemini3.1.md`, `what's React and Tailwind.md`) as positives, plus ambiguity and collision negatives.
9. **Acceptance gate (inherits the one #115 waived):** new clean comparison anchor + re-fire BOTH complete cohorts (deepseek-v4-flash + gpt-5.4-mini); #119 closes only when quarantine/retry/recovery KPIs are stable vs the new baseline — the original Phase-5 gate, satisfied for real.

**Sequencing relative to #116:** independent. #116 owns cross-source reservation/lifecycle; #119 owns the intra-source proposal→canonical boundary. A stamped/resolved deterministic summary slug makes #116's reservation simpler, not harder.

## 6. Codex R1 — verification record (2026-07-23)

Every load-bearing citation verified against code/docs before absorption (receiving-code-review discipline). Zero false positives.

| Finding | Claim | Verification |
|---|---|---|
| F1 (blocking) | Phase-5 gate = "quarantine/retry/recovery KPIs stable"; the delta carve-out covers graph-KPI canonical-collision cases only; result moved 0→1 quarantine + retry per model → gate FAILED | **Accurate** — blueprint §Phase 5 (l.381-391), audit-findings §D (l.175-189). v1.0's "explained deltas" retracted |
| F2 (blocking) | Defect is the missing proposal-vs-canonical boundary; strict schema requires `slug` on raw pages; keep-required-and-stamp leaves missing/malformed/non-string modes gated | **Accurate** — `compiled_source_response.schema.json:37-42`; observed class fixed by stamping, the unobserved modes are not |
| F3 (blocking) | Two contracts + ordering (recover → parse → sufficiency → normalize/resolve → strict canonical gates → canonicalize → post-canon invariants → write); current order validates raw representation too early | **Accurate** — `compiler/compiler.py:309-475` verified stage-by-stage |
| F4 (blocking) | "Close enough" = uniquely resolvable by deterministic authority; never fuzzy similarity; resolution-policy table per variation class | **Accurate** — aligns with v1.0's Option C rejection; summary case = role+`source_id` authority |
| F5 (blocking) | Strict equality moves AFTER normalization, not deleted; post-canon check + canonicalize summary guards stay load-bearing; v1.0's "trivially true" incorrect | **Accurate** — `compiler/compiler.py:717-736`, `compiler/canonicalize.py:424-457` verified |
| F6 (blocking) | Body links = deterministic reference resolution on parsed wikilink tokens (aliases/headings preserved, prose byte-identical, 1:1 mapping, collision/multi-target reject, re-validate); prompt-injecting the canonical slug is not the default remedy (would reverse #115's ratified non-goal) | **Accurate** — non-goal confirmed at blueprint l.393-397 |
| Accuracy 1 | Quarantine ≠ content deletion: candidate commit skipped, source marked `error_compile`; prior committed content survives | **Accurate** — `orchestrator/kdb_orchestrate.py:754-770`; §2.3 corrected |
| Accuracy 2 | Slug = wiki filename, graph identity, wikilink target, manifest identity, replay identity — not "uniqueness only" | **Accurate** — §2.3 corrected |
| Accuracy 3 | Measured = 1/36 = 2.8% per run in this cohort; general prevalence unestimated | **Accurate** — §2.2 corrected |
| North Star | `CODEBASE_OVERVIEW.md` records "fully model-authored including its slug" — update before code | **Accurate** — milestone entry 2026-07-22 (l.15) verified verbatim |

## 7. What this is NOT

- Not a retreat from "fail closed." Normalization is not auto-correction of model *content*; it is Python resolving representational differences where exactly one valid meaning exists, and rejecting everywhere else (ambiguity, collision, loss, missing meaning). Content (titles, bodies, concept slugs, wikilinks) remains model-authored and fully gated.
- Not a judgment that the models regressed. The baseline evidence proves the behavior pre-existed; only the gate was new.
- Not a change to #116's carve. Cross-source reservation/collision policy is untouched.
- Not a waiver of the Phase-5 gate's intent. The gate caught a real design defect; #119 inherits the identical gate as its acceptance criterion and must satisfy it with a re-fired cohort before closing.
- Not permission for global concept-slug punctuation rules (§3 Option B boundary).
