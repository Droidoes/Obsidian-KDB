# #123 — selector prompt prose review: round 1

Review target: `docs/superpowers/archive/specs/2026-07-28-task123-selector-prompt-prose-review.md`

Scope: Pass-1.5 selector prose and its consistency with the Task #123 contracts,
implementation, calibration record, and canonical tracking artifacts.

## Verdict: REVISE

The owner review caught real defects, but Pass-1.5 should not yet be represented
as fully closed.

## Findings

### 1. HIGH — Fat still treats complete bodies as incomplete excerpts

The v2 fat prompt says an excerpt's silence is weak evidence against the entity
as a whole. That instruction applies to every entity even though the frozen
fixture establishes that 161 of 163 excerpts contain the complete body. This
systematically discounts strong negative evidence and compromises the fat
stage's precision role.

`ProjectedEntity.truncated` already records the distinction, but
`render_fat_block` does not render it. Add an explicit completeness/truncation
marker and condition the silence guidance on that marker before D7/P5a model
comparisons.

A fat-only `_v3` change would not invalidate the paid D5 calibration: the
calibration harness renders and measures only the thin prompt. The review's
framing incorrectly couples both templates to that measurement.

References:

- Review observation: lines 319–331
- Current fat prompt: `kdb_search/prompts/selector_fat_v2.txt`, lines 25–28
- Thin-only harness input: `tools/task123_calibrate_estimator.py`, lines 197–209

### 2. HIGH — `unresolved` has conflicting prompt and controller semantics

The fat prompt defines `unresolved` as keys that nothing in EVIDENCE answers.
The controller instead defines unresolved expressions as keys not attributed to
any returned, validated hit. Those meanings diverge whenever EVIDENCE contains
support for a key but the result cap excludes the supporting entity. In that
case `selector_accounting_delta` records expected cap behavior as selector
disagreement.

Choose one semantic contract and align the prompt, specification, and
controller. The returned-selection interpretation is the simplest match for
the existing controller.

There is also an implementation defect in the diagnostic: when the selector's
advisory `unresolved` list is empty, `resolve_accounting` forces the delta to
zero instead of counting disagreement with controller-computed unresolveds.
That contradicts the documented promise that discrepancies are counted.

References:

- Fat prompt: `kdb_search/prompts/selector_fat_v2.txt`, lines 39–43
- Controller accounting: `kdb_search/response.py`, lines 235–261
- Spec contract: `docs/superpowers/specs/2026-07-25-task123-semantic-graph-search-spec.md`, lines 174–175

### 3. HIGH — Canonical tracking artifacts contradict the review outcome

The prose-review artifact says the owner review is closed and D5 calibration
was fired. The active P2 implementation plan still says calibration is blocked
on prose review and leaves the measurement and persistence items unchecked.
`docs/TASKS.md` still describes P2 as in progress.

Task #126 also remains recorded as a prerequisite of D5 because calibration was
expected to consume real keys, whereas the completed calibration used an empty
query. Either the owner overruled that prerequisite or the gate was fired out
of sequence; the decision must be recorded explicitly.

Before treating the state transition as authoritative, synchronize:

- `docs/TASKS.md`
- `docs/superpowers/plans/2026-07-27-task123-p2-implementation-plan.md`
- The Task #126 prerequisite narrative
- The North Star milestone entry, if the provisional D5 result changes its state

References:

- Review status: lines 3–8 and 368–415
- P2 gate checklist: implementation plan lines 799–813
- Task #123 ledger entry: `docs/TASKS.md`, line 49
- Task #126 ledger entry: `docs/TASKS.md`, line 52

### 4. MEDIUM — The provisional D5 ruling overstates its evidence

The record correctly says `gpt-5.4-mini` is unmeasured, but then says the
no-change decision is "safe either way" because the measured Gemini and
DeepSeek densities are higher than the approximate failure threshold. Those
two providers do not establish the density of an unmeasured tokenizer family.

Keep the no-change ruling strictly provisional. Operational urgency is low at
the current vault size, but GPT selector admission should not rest on
cross-provider extrapolation.

Reference: review lines 404–415.

### 5. MEDIUM — Calibration artifact merging needs a full fingerprint guard

The proposed clean follow-up is to merge calibration rows by `model_id`. That
is unsafe unless the writer first verifies that the existing artifact and the
new run share the same fixture version, prompt version, query source, rendered
byte count, estimator setting, and input SHA-256. Otherwise a later rerun could
combine incomparable measurements under one artifact header.

The options text is also internally inconsistent: implementing merge behavior
does not become a prerequisite for the copy-aside/manual-merge option; it
replaces that option. File the guarded merge implementation as the prerequisite
for a safe single-candidate rerun.

Reference: review lines 431–440.

## Recommended disposition

Resolve findings 1–3 before D7/P5a experiments. Findings 4–5 can remain tracked
follow-ups, provided the D5 status stays explicitly provisional and the
single-candidate rerun is not fired before guarded artifact merging exists.
