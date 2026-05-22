# Session Handoff — 2026-05-22

A two-phase session arc spanning 2026-05-21 → 2026-05-22. **11 commits**,
two distinct themes: (Phase A) closing the #76 domain-pipeline follow-ups
+ filing the V0 step-3 ops regression foundation; (Phase B) an alignment
retrospective day that surfaced an architectural milestone that had been
invisible since 2026-05-17. Branch is **11 commits ahead of `origin/main`**.
Push gate stays with Joseph.

## What happened

### Phase A — Domain pipeline closure + V0 ops regression (2026-05-21)

Continuation of Task #76 (Round 5 §7.3 `domain` field). Self-review caught
an R12 gap in #76.3 (`sub_domain` stored verbatim though blueprint §6.3 +
Decision-Log R12 call for `_normalize_domain` to apply to it too). Closed
the gap as #76.6, fully closed #76, then worked through the two filed
follow-ups (#79 verifier coverage for schema v2.1, #80 snapshot format v3)
and the V0 step-3 ops regression foundation (#81, formerly `#78c` per
Task #75 §OQ-5 — renumbered post-#79/#80).

Pattern note: #81 went through the two-reviewer synthesis (Codex + Gemini)
before scope lock. Codex caught the critical code-grounded point — typed
traversal exists in **two distinct implementations** (compile-time hand-rolled
BFS in `graph_context_loader._t3_neighbors`, query-time variable-length-path
in `queries.neighbors`) — and both need separate coverage. Gemini's structural
A/B/C breakdown was adopted with Codex corrections applied.

### Phase B — Alignment retrospective + JOURNEY.md (2026-05-22)

Joseph opened with a 3-iteration retrace from his perspective ("9 weeks,
80 tasks, ~$300, and I still don't know if GraphDB can replace static-top-50
or if manifest can be reduced to file-meta only").

Code-state spot-check produced the headline finding of the session:
**both empirical questions Joseph perceived as open were actually closed
on 2026-05-17** via D49 + D50 + D51 + Task #71 cold-start widening
(empirical proof: graph 17–23 pages vs manifest 0–8). The architectural
milestone existed only as three separate decision-log entries + a same-day
empirical task — no milestone-level signal had surfaced it, so the
in-session mental model lagged the code state by ~5 days.

That gap became its own finding (`docs/JOURNEY.md` Lessons §5), and the
mitigation shipped in the same session: a dated Milestone Changelog at
the top of `CODEBASE_OVERVIEW.md` so future contributors (and future
sessions) see the inflection points one line each. The label fix on
`prompt_builder.py:138` ("manifest snapshot" → "graph snapshot") is the
first concrete instance of the rendering-debt question JOURNEY surfaces;
`types.py:277` carries the same stale framing in a class docstring and is
filed as a follow-up.

## Commits landed this session

| Commit | Title | Phase |
|---|---|---|
| `8e268f6` | `fix(graphdb-kdb): #76.6 — normalize sub_domain at ingest (R12 gap)` | A |
| `2f0a58d` | `docs: TASKS — #76.6 closure + file #79/#80 follow-ups` | A |
| `cc4904e` | `feat(graphdb-kdb): #79 — verifier coverage for Domain + BELONGS_TO (schema v2.1)` | A |
| `e903e18` | `feat(graphdb-kdb): #80 — snapshot format v3 (Domain + BELONGS_TO)` | A |
| `5bc5a82` | `docs: TASKS — close #79 + #80 with implementation SHAs + deviation flags` | A |
| `d38778f` | `test(graphdb-kdb,kdb-compiler): #81 — Step-3 V0 ops regression foundation` | A |
| `d29334e` | `docs: TASKS — file + close #81 with implementation notes + coverage map` | A |
| `1eb0bd6` | `docs: JOURNEY.md — three-iteration retrospective (loop-closure surfaced)` | B |
| `b229d63` | `docs: CODEBASE_OVERVIEW — Milestone Changelog + JOURNEY link` | B |
| `c2bbdee` | `fix(prompt-builder): label graph-derived context as "graph snapshot"` | B |
| — | (pre-session: `2f0a58d` predecessor `68dd2f4` closed #76.1–#76.5 the prior session) | — |

## Documents created or substantively edited

| Doc | Purpose | State |
|---|---|---|
| `docs/JOURNEY.md` | Three-iteration retrospective; *why we walked this way* | **New.** 229 lines. Reviewed by Codex (7 corrections) + Gemini (1 affirming refinement). All Codex factual claims verified against `git log` / current parser / decision-log before adoption. |
| `docs/CODEBASE_OVERVIEW.md` | North Star architecture spec | Added **Milestone Changelog** section between top-matter and §1; added JOURNEY callout inside §1 Vision; bumped stale "Last updated" 2026-05-08 → 2026-05-22. |
| `docs/TASKS.md` | Project task ledger | #76.6 closure, #79 + #80 + #81 filed and closed with implementation SHAs + deviation flags. |

## New behavioral protocol surfaced

**Core Rationale Restatement (the "devil's advocate" gate)** — Lessons §4
in JOURNEY.md, contributed by Gemini in the JOURNEY review.

When a discussion converges suspiciously fast, OR when the model is about
to retract a design constraint under user pressure, output a structured
3-point callout: (1) the original/opposing technical position in unvarnished
form; (2) the specific concessions being made; (3) the failure modes those
concessions might trigger (e.g., which hedge from
`task75-predeclared-eval-criteria-blueprint.md` §5 might fire). Pivot with
eyes open and document the retreat — never let it pass silently.

## Task status

| # | Sub-task | State | Commit |
|---|---|---|---|
| 76.6 | Normalize `sub_domain` at ingest (R12 gap) | ✅ landed | `8e268f6` |
| 76 | (parent) Round 5 §7.3 `domain` field | ✅ closed | (all 6 sub-tasks done) |
| 79 | Verifier coverage for Domain + BELONGS_TO (schema v2.1) | ✅ landed | `cc4904e` |
| 80 | Snapshot format v3 (Domain + BELONGS_TO) | ✅ landed | `e903e18` |
| 81 | Step-3 V0 ops regression foundation (Strand 1 of #75 §3.1) | ✅ landed | `d38778f` |
| **77** | **Probe-set curation — Strand 2 of #75/#81** | **next, blocked on user OQ-3 decisions** | — |
| 78 | PPR implementation (V1 step-3 op) | queued | — |
| 78b | Subgraph extraction implementation (V1 step-3 op) | queued | — |

## Test surface

```
graphdb_kdb:   ~140 passed (+9 from #79 + #80 v3 coverage + cli print)
kdb_compiler:  ~600 passed (+5 from #81 graph_context_loader regression suite)
kdb_benchmark: ~210 passed (unchanged today)
                          996 passed total (+7 vs start of Phase A),
                          1 bench deselected (#81 shortest-path runtime guard),
                          1 live-API skipped (pre-existing)
```

7 new tests landed across both phases. Test surface stable after each
commit. `bench` marker registered in `pyproject.toml`; `addopts` excludes
by default (opt-in via `pytest -m bench`).

## Architectural shifts worth surfacing for next session

1. **The loop-closure milestone is now visible.** `docs/CODEBASE_OVERVIEW.md`
   carries a dated Milestone Changelog at the top; `docs/JOURNEY.md` carries
   the three-iteration story. Future sessions inherit this signal layer —
   the 5-day mental-model lag that motivated JOURNEY.md should not recur.

2. **`@pytest.mark.bench` opt-in pattern established** (#81). Bench-marker
   registered, `addopts` excludes by default. Pattern available for future
   flakiness-prone runtime guards (next likely use: PPR runtime in #78).

3. **Schema v2.1 fully sealed.** Domain + BELONGS_TO covered by verifier
   (Layer 2 structural diff) and snapshot (v3 format). The Tier-2 OneDrive
   recovery path now preserves Domain state alongside Entity / canonical_id
   / ALIAS_OF.

4. **`prompt_builder.py:138` rendering-debt fix is the first concrete
   instance of an audit pass that hasn't been filed yet.** `types.py:277`
   carries the same stale framing in a class docstring. The wiki/rendering
   v2.1-alignment question is filed in JOURNEY.md's Open Empirical
   Questions table but not yet in `TASKS.md`.

## What's next

### Immediate (next coding session)

**#77 — Probe-set curation.** Blocks the §4.3 "≥95% match" gate (Strand 2
of #75/#81). OQ-3 questions pending Joseph's design decisions:

- **N** — how many probe pairs?
- **Curator** — Joseph manually? LLM-assisted? Mix?
- **When** — before #78/#78b, or alongside?
- **Vault-versioning** — probe set lives in repo (versioned, deterministic)
  or in vault (with the source corpus it probes against)?

Gemini suggested invoking `/grill-me` for an interactive OQ-3 resolution.
Joseph's call when to do that.

### After that

- **#78** — PPR implementation. V1 step-3 op. §4.1 criteria predeclared in
  Task #75. Likely uses the `bench` marker pattern from #81.
- **#78b** — subgraph extraction. V1 step-3 op. §4.4 criteria predeclared.
- **Trivial label fix** — `kdb_compiler/types.py:277` "Per-source manifest
  snapshot" → "Per-source graph snapshot" (same root cause as today's
  `prompt_builder.py:138` fix; one-line edit).
- **File the wiki/rendering v2.1-alignment audit task** in `TASKS.md`
  (currently only flagged in JOURNEY.md Open Empirical Questions).

### Deferred (post-V1)

- **#76 deferred follow-ups NOT folded into #76 closure:** per-source
  `source_id` on `BELONGS_TO` (R6 promotion); `analytics.py:29`
  canonical-only filtering; prompt + producer-contract amendments.
- **Pre-existing alias_of CLI print gap** — one-line fix.
- **Push to `origin/main`** — 11 commits queued locally. Push gate
  stays with Joseph.

## Loose ends + small risks

- **`uv.lock` is untracked** since the start of this session arc. Not
  touched by any commit today. Decide whether to add to `.gitignore`
  or commit explicitly on next session.
- **Two reviewer-flavor pairings hardened in this session.** Codex =
  code-grounded factual corrections; Gemini = structural breakdown +
  affirming + directional suggestions. Gemini still needs the review-only
  guardrail explicit in every prompt (memory `feedback_gemini_review_only_guardrail`).
- **The "loop closed but I don't feel it" gap (JOURNEY §5) was a 5-day
  lag.** The Milestone Changelog mitigation works *prospectively* —
  doesn't catch gaps that already opened. If another multi-week arc
  closes without a one-line milestone added the same day, the gap can
  re-emerge. Standing rule: closure commit = changelog entry.
- **No `graphdb-kdb` actions taken on the live graph today.** Phase A
  changes (verifier + snapshot v3) are additive against the existing
  graph; no migration needed. Phase B was docs/labels only.
