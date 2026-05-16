# Task #69 — `compile_count` Attribute-Drift Audit

**Date:** 2026-05-16
**Status:** Determination reached — investigation closed, no code change.
**Verdict:** **D39 replay-eligibility tax. Not a counter-computation bug.**

---

## 1. The Question

The post-#68 `graphdb-kdb verify` reports a uniform attribute drift on all 4 sources:

| Source            | manifest `compile_count` | kuzu `ingest_count` | drift |
|-------------------|--------------------------|---------------------|-------|
| Buffett           | 3                        | 2                   | −1    |
| CODEBASE_OVERVIEW | 2                        | 1                   | −1    |
| Howard-Marks      | 2                        | 1                   | −1    |
| EP1               | 7                        | 6                   | −1    |

Plus a matching `compile_state` mismatch (`recompiled` in the manifest vs
`compiled` in the graph) — 8 `attribute_mismatch` issues total.

The audit question: **is the uniform −1 purely the expected D39 replay-eligibility
/ history tax, or is there a real counter-computation bug** in how
`_update_source_ingest_state` advances `ingest_count` against how the manifest
advances `compile_count`?

Scope was investigation-only: no code change until this document answers it.

## 2. Evidence

**E1 — Both counters are simple, single-site `+1`-per-compile.**
`manifest_update.py` initialises `compile_count` to `0` (lines 191, 499) and has
exactly one mutation site: `rec["compile_count"] = int(rec.get("compile_count", 0)) + 1`
(line 508). The graph's `ingest_count` is incremented once per replayed compile
event in `_update_source_ingest_state`. Neither counter double-counts, seeds to
1, or has a second write path. A computation bug would have to live in code that
does not exist.

**E2 — The graph `ingest_count` provably equals the eligible-journal count.**
Counting replay-eligible journals (D39: `success && !dry_run && payload_present`
and `schema_version ∈ supported_journal_versions`) per source gives exactly
2 / 1 / 1 / 6 — identical to the kuzu `ingest_count` column above. The graph
counter is correct *for the journals it is allowed to replay*.

**E3 — The manifest `compile_count` is internally consistent.**
For every source, `len(previous_versions) == compile_count − 1`. The manifest's
own history corroborates its counter; it is not inflated.

**E4 — Each source's missing compile is its FIRST compile, predating the
eligible-journal era.** The −1 is not a lost recent compile — it is the original
one:
- `2026-04-20T02-34-09Z` — `schema_version: 1.0`, ineligible by D39
  (`unsupported_version`). Its `deltas.pages_created` includes
  `summaries/codebase-overview.md` — it compiled Buffett, CODEBASE_OVERVIEW and
  Howard-Marks.
- `2026-04-21T17-48-32_EDT` — `schema_version: 2.0`, no retraction/compile
  sidecar, ineligible by D39 (`payload_missing`). It compiled EP1 (22 pages).

Both first-compile journals predate #63.7, which introduced sidecar archival.
They can never become replay-eligible without a backfill, so the graph will
never replay them.

**E5 — Uniformity is explained by `first_seen_at` clustering, not a systematic
off-by-one.** Three sources share `first_seen_at 2026-04-20T01:21:34Z` and EP1
`2026-04-21T17:48:32` — every source was first compiled before sidecar archival
existed. The drift is uniform because the *cause* (one pre-archival first
compile per source) is uniform, not because a formula is uniformly wrong.

## 3. Determination

**The −1 `compile_count` drift is the D39 replay-eligibility tax.** The manifest
counts every compile that ever happened; the rebuilt graph counts every compile
whose journal is *replay-eligible*. Each source has exactly one compile — its
first — whose journal predates sidecar archival and is therefore permanently
ineligible. `manifest − graph = 1`, uniformly, by construction. There is no
counter-computation bug; both counters are correct against their own inputs.

## 4. Why It Is Permanent (D39 By Design)

D39 makes `graphdb-kdb rebuild` replay only journals that carry a complete,
schema-supported payload. This is deliberate: a journal without a payload cannot
be replayed deterministically, so the rebuilder skips it rather than guessing.
The pre-archival first-compile journals will never satisfy D39 unless someone
synthesises sidecars for them (the same one-shot technique #68 used for the
cleanup backfill). Absent that backfill, the −1 is a **stable, expected
property of the system**, not drift that will grow or that a fix would remove.
It should be read as "the graph reflects the replayable history," not as
corruption.

### 4a. `compile_state` is a *separate* sub-issue — not the same mechanism

The companion `compile_state` mismatch (`recompiled` vs `compiled`) looks
related but is **not** the replay tax. The manifest computes
`"recompiled" if compile_count > 0 else "compiled"`. The graph computes
`compile_meta.get("compile_state") or cs.get("compile_state") or "compiled"`
in `_update_source_ingest_state` — and the producer **never writes
`compile_state` into `compile_meta`**. Verified on the replayed sidecar
`state/runs/2026-05-16T09-36-03_EDT/compile_result.json`: both
`compile_meta.compile_state` and `cs.compile_state` are `None` for all 4
sources, so the graph always falls through to the literal `"compiled"`.

Consequence: the graph `ingest_state` is `"compiled"` **regardless of replay
history** — it would mismatch a `recompiled` manifest even if every journal
were replay-eligible. So a future verifier-classification refinement must treat
the two differently: `compile_count` drift is a function of replay eligibility;
`compile_state` drift is a function of a producer field that is simply never
populated. Same `verify` line, two distinct causes.

## 5. Recommendation

1. **Close #69 — no code change.** The audit answered the question: tax, not
   bug. The investigation-only scope is satisfied.
2. **Keep `verify` output interpretable.** The 8 `attribute_mismatch` issues
   (4 `compile_count`, 4 `compile_state`) are a **known-benign class**. This
   document is the reference; future `verify` reads should not re-investigate
   them.
3. **Possible follow-up task (not #69, not now):** teach `graphdb-kdb verify`
   to classify pre-eligible-era `compile_count` drift and the unpopulated
   `compile_state` as a distinct known-benign band, so the signal-to-noise of
   `verify` stays high. Per §4a this needs two separate rules, not one. File
   as its own implementation task only if `verify` noise becomes a real
   nuisance — YAGNI until then.
4. **Out of scope (confirmed):** the 2 dead links
   (`confucianism→mencius`, `yield-chasing→risk-management`) are content/link
   hygiene, not graph-replay counter correctness. They belong to a future
   `kdb-clean links` discussion, not here.
