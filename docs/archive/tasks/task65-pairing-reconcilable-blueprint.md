# Task #65 — `pairing_type_mismatch` Should Be Reconcilable, Not a Hard Gate

Status: **open** — awaiting Proceed gate.

---

## 1. Why this exists

Recompiling EP1 (prep for Task #64's Task 6) failed Stage 4 on **three** consecutive
fires — gemini-3.1-flash-lite ×2, gpt-5.4-mini ×1 — with the *identical* defect:

```
[$.compiled_sources[0].concept_slugs[N]] 'ethnic-integration-in-china'
  is page_type='article', expected 'concept'
```

The gpt-5.4-mini compile was otherwise excellent — 28 pages (1 summary, 22 concepts,
5 articles). The only fault: 2 slugs (`ethnic-integration-in-china`,
`china-as-cohesive-civilization`) were emitted as correctly-typed `article` **pages**
but filed into `concept_slugs` instead of `article_slugs`.

The two topics are genuinely borderline — abstract-sounding names, article-length
treatment — so every model resolves the tension the same way. It is content-driven,
deterministic across models, not random.

## 2. Root cause

`validate_compile_result.py:200-210`: when a slug in `concept_slugs`/`article_slugs`
resolves to a `pages[]` entry whose `page_type` disagrees, the validator emits
`pairing_type_mismatch` at **`gate`** severity (also in `HARD_ZERO_FINDING_TYPES`).
A gate finding aborts the run. The code comment justifies it: *"no principled way to
pick a winner."*

But there **is** a principled winner. `concept_slugs`/`article_slugs` are denormalized
index lists, fully derivable from `pages[].page_type`. A `pages[]` entry carries the
page's title and full body — `page_type` is the model's deliberate, body-bearing
classification. The slug-list entry is a lightweight filing act. **The page object is
authoritative** — exactly the doctrine **Task #57** established for `outgoing_links`
("body-wins": the reconciler derives the denormalized field from the authoritative
source). `pairing_type_mismatch` is the one pairing finding that was never brought
under that doctrine: its siblings `pairing_omission` and `pairing_commission` are
already `measure` severity and auto-healed by the reconciler at Stage 5.

Net effect today: the pipeline **discards 28 good pages over 2 mis-filed slugs**.

## 3. The fix — two options

Both make `pairing_type_mismatch` non-fatal. They differ in how the slug lists are
made consistent.

### Option A — Targeted: gate→measure + finding-driven move
- `validate_compile_result.py`: `pairing_type_mismatch` severity `gate`→`measure`;
  drop it from `HARD_ZERO_FINDING_TYPES`.
- `reconcile.py`: add a handler — for each `pairing_type_mismatch` finding, remove the
  mis-filed slug from the wrong list. The already-emitted `pairing_omission` finding
  for the same slug adds it to the correct list. Net: slug moved.
- **Pro:** minimal, surgical, stays finding-driven. **Con:** still relies on the
  validator emitting both findings; the slug-list inconsistency class persists as a
  measured-then-healed defect rather than being structurally impossible.

### Option B — Wholesale: derive the slug lists from `pages[]` (#57-consistent)
- New unconditional `reconcile_slug_lists(parsed_json)` in `reconcile.py`, mirroring
  Task #57's `reconcile_body_links`: `concept_slugs = sorted(p.slug for p in pages if
  p.page_type == "concept")`, likewise `article_slugs`. Wired into
  `compiler.compile_one` right after `semantic_ok`, alongside `reconcile_body_links`.
- By the time Stage 4 validation runs, the lists are consistent with `pages[]` by
  construction — `pairing_type_mismatch`, `pairing_omission`, `pairing_commission`
  cannot survive into the validated payload.
- `validate_compile_result.py`: `pairing_type_mismatch` severity `gate`→`measure` and
  out of `HARD_ZERO_FINDING_TYPES` anyway (the validator still runs for the benchmark
  scorer, which reads raw pre-reconcile model output — see §4).
- **Pro:** eliminates the entire pairing-inconsistency class structurally; one
  rebuild, no per-finding surgery; exact parity with the #57 body-wins precedent.
  **Con:** larger conceptual shift — the model's emitted `concept_slugs`/`article_slugs`
  become fully advisory (the prompt still asks for them; the reconciler overwrites).

**Recommendation: Option B.** It is the principled, #57-consistent fix — it makes the
defect class structurally impossible rather than caught-and-patched, and the reconciler
is simpler (one derive vs finding-by-finding slug surgery). Task #57 already proved the
pattern is sound and accepted for `outgoing_links`.

## 4. Benchmark-scoring ripple (must be acknowledged)

`pairing_type_mismatch` is in `HARD_ZERO_FINDING_TYPES`, which the benchmark scorer's
`check_compiled_source` uses to derive **S0** (`validator_hard_zero_pass_rate`) from
raw model output. Removing it means a model that emits a pairing type-mismatch is no
longer hard-zeroed on S0 — **S0's definition changes**. Consequences:
- Models previously hard-zeroed by pairing type-mismatch score higher on S0.
- Per the D29.9 cross-generation doctrine, post-#65 scorecards are not comparable to
  pre-#65 ones on S0.
- A fresh benchmark merge fire is needed after #65 to establish the post-#65 baseline.

This is correct and intended: if the defect is reconcilable, it should not hard-zero a
model's quality score either — it becomes a measured (non-fatal) quality signal,
consistent with `pairing_omission`/`pairing_commission` already being `measure`.

## 5. Decision (proposed — D45)

| ID | Decision |
|----|----------|
| **D45** | **`pairing_type_mismatch` is reconcilable; `pages[].page_type` is authoritative.** The validator demotes it `gate`→`measure` and drops it from `HARD_ZERO_FINDING_TYPES`. `concept_slugs`/`article_slugs` are denormalized indexes of `pages[]`; on conflict the page object wins (Task #57 body-wins doctrine, extended). S0 is redefined accordingly; a post-#65 benchmark re-fire establishes the new baseline. |

## 6. Test surface (provisional — finalize in plan)
- A compile_result with a slug in `concept_slugs` whose page is `article` → no gate
  error; after reconcile the slug is in `article_slugs`, absent from `concept_slugs`.
- The symmetric case (article-list slug, concept page).
- A clean compile_result is unchanged by the reconcile step (idempotent).
- `pairing_type_mismatch` no longer appears in `HARD_ZERO_FINDING_TYPES` /
  `check_compiled_source` output.
- (Option B) `reconcile_slug_lists` rebuilds both lists from `pages[]`, sorted,
  deduplicated; a summary page's slug lands in neither list.
- End-to-end: the EP1 gpt-5.4-mini payload that currently gate-fails now passes Stage 4.

## 7. Acceptance / closure
- EP1 recompiles cleanly (the live re-fire that motivated this task passes).
- Full `kdb_compiler` suite green.
- A post-#65 benchmark merge fire is recorded.

## 8. Out of scope
- The Task #64 migration / EP1 page supersession — resumes once #65 lands and EP1 is
  recompiled.
- Any change to how the *model* is prompted for `concept_slugs`/`article_slugs` — the
  prompt is unchanged; #65 only changes post-processing.
