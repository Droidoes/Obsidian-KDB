# Feedback round 1 — #123 selector prompt prose review + D5 calibration record

**Reviewer:** Kimi (external pass-1.5 review)
**Date:** 2026-08-02
**Subject:** `docs/superpowers/specs/2026-07-28-task123-selector-prompt-prose-review.md`
(CLOSED 2026-08-02 — three prose findings absorbed into `_v2`, D5 calibration FIRED)

Method note: the doc's load-bearing claims were checked against the code rather
than taken on faith. Verified-against-code items are listed first; feedback
follows.

## What checks out

- **`search.py:371` — manifest order for stage 2.** Stage 2 is built by
  filtering `space.entities` to thin's retained set, preserving manifest order,
  not thin's ranking; the comment cites spec §3.4. The "BEST FIRST is kept"
  ruling rests on real ground.
- **`_concordance` (`search.py:550-571`)** — reads `retained[:20]` against
  fat's top 10, and its null-casing is more careful than the doc describes:
  thin-ran-and-honestly-retained-nothing yields a real 0.0, while
  thin-never-produced-a-list yields `None` (`thin.validated is None` vs
  `retained == ()`). Minor: the doc cites `search.py:569`; the actual read is
  at line 570. Trivial drift, but this file's whole ethos is exact references.
- **`M = 100`** (`kdb_search/constants.py:20`) — the fixture's 163 > M, so the
  cap genuinely binds on the calibration fixture itself; the rank-to-cut
  justification is not theoretical.
- **`_excerpt_policy_v1`** (250 whitespace words + 25-word sentence extension)
  and **`render_fat_block` never rendering `projected.truncated`**
  (`kdb_search/projection.py:135-146`) — both as claimed. The open observation
  is accurately stated.
- **Fat v2 on disk matches the described rewrite**
  (`kdb_search/prompts/selector_fat_v2.txt`): the shortlist possibility is
  declared in the opener ("may already have been shortlisted by an earlier
  pass"), the "Never select… unseen body" imperative is gone, and the
  silence-is-weak-evidence premise is retained, exactly as the outcome section
  records.

## Feedback

### 1. The `_v3` cost framing for the open observation is wrong for one of the two options

The doc says closing the truncation gap "means either rendering a truncation
marker so the discount can be conditioned on it, or narrowing the premise to
the truncated case — both are prose changes, so both cost a `_v3` bump."

Rendering a marker is a `render_fat_block`/serializer change, **not** template
prose: the template sha256, version, and rendered-overhead pins do not move,
and the D5 thin block is untouched entirely. What it costs is a re-pin of any
golden that renders a capped fixture entity (2 of 163) — not a template
re-version. That matters because it changes the "not worth spending on their
own" calculus: the marker half may be cheap enough to do without waiting for a
prose-bump-worthy batch. (Whether a marker alone changes model behavior
without prose explaining it is a separate question — but that is an argument
about efficacy, not cost.)

### 2. A challenge to the surviving premise sentence itself

*"An excerpt is the opening of a body, so its silence about a topic is weak
evidence against the entity as a whole"* sits one line after *"Select on
positive support only."* Positive-support-only already forbids selecting on
absence; the silence sentence's only incremental effect is to suppress the
negative signal — and on this corpus that suppression is wrong 161 times out
of 163 (the excerpt **is** the whole body; silence is strong evidence).

The v3 candidate worth considering is therefore not just narrowing the premise
to the truncated case, but **deleting it** and letting *"text you cannot see
is not evidence for it either"* carry the truncated case alone — that half is
the one that is actually true for all 163. That said, deferring is agreed: the
direction is an experiment question (#125's stage-2 representation trial), not
a prose-review question.

### 3. `gpt-5.4-mini` does not need a paid call to be measured

The doc presents the follow-up as one-or-three paid API calls plus a
`write_artifact` merge fix. But the missing candidate is the one with a public
tokenizer: OpenAI's BPE is reproducible offline via `tiktoken`, so the exact
quantity under test — input tokens of fixed, pinned bytes — can be measured at
**zero cost**, deterministically, and committed as a script next to the
calibrator. It is not provider-reported ground truth, but as a proxy row it
would take the gate from two-thirds to effectively discharged, given the doc's
own math (a sub-3.2 B/token result is needed to threaten the 1.25× headroom;
two unrelated tokenizers landed at 3.71–3.76).

**Recommendation:** add the tiktoken proxy row now, leave the API row pending,
and keep option (c) — the `write_artifact` merge-by-`model_id` fix — as filed
regardless, since it is the right hygiene independent of this row.

### 4. The pre-registered prediction post-mortem is the strongest part of the document

Predicted 3.0 B/token, measured ~3.74, the published boundary table inverted
on evidence, and the "authorizes a request that does not fit" claim explicitly
withdrawn. Keep this pattern; it is what makes the D-series gates worth
anything.

### 5. One question the doc does not close

Finding 1 fixed the prompt side of the `unresolved` drift — v2's opener tells
the model EVIDENCE may be a shortlist. But under N > M, `unresolved` still
conflates *"the graph has nothing on key B"* with *"thin's unrecoverable cut
removed what bore on key B"* at the **metrics** level. The doc records the
semantic risk in prose; is the downstream consumer (the recall metric reading
`unresolved_expressions`) typed to distinguish the two, or does it still read
as graph-level absence? If the latter, that is a third open observation in the
same family — cheaper to type now than to disentangle from KPI series later.

## Minor

- `search.py:569` → 570, as noted above.
- The v1 code blocks are clearly marked superseded; consider a one-line
  pointer at each block header to the `_v2.txt` path so a skimmer does not
  quote v1.

## Net

The prose review and calibration are sound. The deferred precision tax is
correctly scoped but its cost is overstated for the marker option, and the
unmeasured-candidate gap has a free path the doc does not consider.
