# #123 v0.16 — concurrence review, kimi

Date: 2026-08-02 · Subject: `2026-08-02-task123-v016-concurrence-brief.md` ·
Reviewer: **kimi** · Suite re-run independently: **3,059 passed, 34 skipped, 1
deselected** (91.97 s) — matches the brief's figure exactly. kdb_search package
alone: 1,060 passed, 33 skipped.

## Verdict: CONCUR — with one material staging finding that must be resolved before commit 1

The code matches the ratified D-123-A…F decisions on every point I checked, and
both flagged consequences (§1.1, §1.2) are correctly handled. The one blocker is
not in the code — it is in the **current git index**, which cannot produce the
landing plan's commit 1.

## F1 (material, blocking commit 1) — the v1→v3 rename collapse is live in the index right now

The brief's §6 staging note records that `selector_fat_v2.txt` was overwritten
by v3, git collapsed the rename to v1→v3, and v2 was reconstructed and verified
byte-exact against `sha256:3083b474…58a7d9`. That trap is **currently armed
again**:

- The index holds two **pure renames with zero content change**:
  `selector_fat_v1.txt → selector_fat_v3.txt` and
  `selector_thin_v1.txt → selector_thin_v2.txt`
  (`git diff --cached`: 0 insertions, 0 deletions).
- The staged blob of `selector_fat_v3.txt` is sha256 `b4679b90…a37d4` — **byte
  identical to HEAD's v1**. Same for the staged thin blob (`415c97f9…` = v1).
- The worktree holds the real v3 fat (`18ecd6a4…`) and real v2 thin.
- The byte-verified **fat v2 reconstruction exists in neither the worktree nor
  the index** — no `selector_fat_v2.txt` anywhere, no stash.

Consequence: the landing plan's commit 1 ("`_v2` prompts · … · panel
absorption") **cannot be produced from the current repository state**. If the
index is committed as staged, history records v1→v3 directly under the v3 name
and the real v2 is unrecoverable except by re-deriving it a second time.

**Ask:** before commit 1, re-materialize `selector_fat_v2.txt` (re-reverse the
four v3 edits, re-verify against `3083b474…58a7d9`), and stage the three
commits as file-level splits rather than trusting the aggregate index. If the
plan has changed and v2 is intentionally being skipped as a history step, say
so in the commit-1 message — the prose-review document's status header names
v2 as the D5-calibrated contract, so silently dropping it from history would
leave the record pointing at bytes no commit contains.

## The two checks the brief asked for

### §1.1 — thin's output allowance following M: correct, and correctly framed as derived

Verified from source: `schema_maximum_thin_document()` at M=150,
MAX_SLUG_LEN=120 serializes to exactly **18,464 B** (ran it); old figure 12,314
B at M=100 reproduces the same way. 20,000/18,464 = 8.3% headroom vs
13,000/12,314 = 5.6% — the brief's relative-headroom claim is exact.
D8(iii)'s rule is "the allowance derives from the exact maximum," and M is an
input to the exact maximum, so the allowance following M is the derivation rule
operating, not a new decision. Concur. `PROVIDER_MAX_TOKENS_THIN` = 36,000 is
asserted ≤ the route's `max_output_tokens` in `resolve_selector_route`
(`budget.py:188-194`) — the guard is executable, not prose.

One framing endorsement: recording this as "the amendment did not anticipate
it" (both in the brief and in `constants.py:154-157`) rather than absorbing it
silently is the right call. It is the same species of surprise as the D5
estimator — a quantity M feeds that nobody listed — and the record is better
for naming it.

### §1.2 — `FAT_PREFLIGHT_BUDGET` reachable only by an oversized single body: acceptable; record it as a contract narrowing

The mechanism checks out. Thin reserves 36,000 output tokens; fat reserves
26,000. Any route passing thin's pre-flight has at least ~10,000 tokens
(~40 kB) more fat-side room than thin's entire evidence block needed, so a
window too small for many moderate bodies can no longer exist *past thin's
gate* — the many-bodies case is now handled by the fill seating fewer and
succeeding, which is strictly better than failing. The terminal's surviving
role — "one entity alone blows the budget" — is a genuine `budget_exceeded`,
and the rebuilt branch rows (60,000 window, ~120 kB body) exercise exactly
that.

On the question posed: this **is** a contract change beyond §7.1's wording.
§7.1 said "narrows to *not even one entity fits*"; the stronger truth is
"*reachable only by a single oversized body*." The difference matters to a
future reader of the branch table, who would otherwise hunt for a window-size
row that can no longer exist. The `search.py:453-458` comment already states
the strong form; recommend §7.1's prose be amended to match it at the next
spec touch. Not a defect — a record-keeping gap of the kind this repo
(otherwise) reliably closes.

## Spot-checks against the deletions and judgment calls

- **Deletions confirmed.** `_excerpt_policy_v1`, `_truncate_to_block_ceiling`,
  `ProjectedEntity.truncated`, the three excerpt constants,
  `fat_worst_case_request_bytes`, `fat_static_guarantee_tokens`, and
  `advisory_unresolved` survive only as historical comments and in the frozen
  fixture builder (`scripts/build_task123_snapshot_fixture.py` — correctly
  untouched). No live references.
- **§3.1 (`EXCERPT_POLICY_VERSION`)** — retirement is clean: `artifact.py:227`
  and `test_artifact.py:262` record the removed hash term explicitly, and the
  snapshot hash moving because the evidence bytes moved is unavoidable and
  correctly attributed. Concur.
- **§3.2 (`worst_case_input_tokens` kept)** — verified: its only callers are
  `test_budget.py:284-286`. The asymmetry with the deleted `truncated` is real
  but not special pleading: it is the executable form of the
  `tokens_lte_bytes` premise that `resolve_selector_route` actively enforces,
  and its test is the only place the proof obligation is asserted. Keep.
  (If consistency is ever preferred over the proof, the deletion is indeed one
  line plus two test lines — but the premise would lose its executable
  witness.)
- **§3.3 (2/163 capped fixture divergence)** — concur. Unrecoverable bodies,
  checksums untouched, probes not re-opened: the least-bad option, honestly
  recorded.
- **§3.4 (`types.py:99` orphan)** — confirmed referenced nowhere;
  flag-don't-delete is correct for a pre-existing orphan.

## §4 verification claims — independently confirmed

- The **+1 byte** accumulator overstatement is real and in the safe direction:
  `stream_contribution_bytes` (`projection.py:151-168`) charges block + 1
  separator; `"\n".join` over n blocks costs n−1. The docstring states the
  off-by-one and its direction explicitly.
- **Boundary tested, not just slack**:
  `test_a_pool_filled_to_the_LAST_BYTE_still_passes_its_own_pre_flight`
  (`test_two_stage.py:1471`) exists and asserts both sides of the refusal line.
- **Membership and presentation asserted separately**:
  `test_two_stage.py:1438-1444` (seated set == thin's top-K) vs
  `1466-1468` (rendered order == manifest, ≠ thin's).
- **`ABOVE_M = M + 20`** (`test_two_stage.py:63`) — derived, not the stale
  literal 120. The brief's account of what the literal had silently become is
  exactly the failure mode deriving it prevents.
- `fat_input_byte_allowance` (`budget.py:237-259`) is algebraically derived
  from `preflight`'s own inequality, with the exact-for-integer-bytes argument
  stated. The clamp-to-0 path is, as noted, belt-and-braces behind
  `resolve_selector_route`.

## Two stale comments found (minor, non-blocking)

1. **`kdb_search/prompts.py:265-268`** — `template_overhead_bytes`'s docstring
   still says "The evidence stream (M x `EXCERPT_BLOCK_CEILING_BYTES`) … are
   budgeted separately by the fill's per-entity cost." The constant is deleted
   and the fill does not budget M × ceiling; it accumulates
   `stream_contribution_bytes` against `fat_input_byte_allowance`. The sentence
   describes the retired scheme.
2. **`kdb_search/tests/test_prompts_golden.py:93-94`** — names
   `budget.fat_worst_case_request_bytes()` as "the only consumer" of the fat
   overhead figure. That function is deleted; whatever now consumes
   `GOLDEN_OVERHEAD_BYTES` should be named, or the parenthetical cut.

Both are one-line fixes and squarely in "comments that now describe the old
behavior" territory.

## Disposition of my round-1 prose-review feedback

For the record, since the brief's §5 references kimi F5: v3 absorbs both of my
substantive round-1 points. The silence-premise sentence I challenged (item 2)
is **inverted and conditioned** in v3 — "Where a body is given it is the
entity's whole page … its silence about a topic is evidence that the entity
does not cover it. A title-only entry is the exception" — which is precisely
the narrowing I argued for, now true by construction under D-123-C rather than
true 161/163 by corpus luck. And my item 5 (the `unresolved` metrics-typing
question) is **dissolved by D-123-F**: with the advisory list off the wire
there is no field left to drift. The marker-rendering cost-framing correction
(item 1) is moot — `truncated` no longer exists to render. The tiktoken proxy
suggestion for the unmeasured `gpt-5.4-mini` (item 3) stands as filed; it is
unaffected by v0.16 since the D5 gate concerned the thin side.

## Summary

| | |
|---|---|
| §1.1 derived allowance | **Concur** — numbers reproduce exactly |
| §1.2 narrowed terminal | **Concur** — acceptable; recommend §7.1 prose catch up to the code's own comment |
| Deletions / §3.1–3.4 | **Concur** on all four |
| §4 verification claims | **Confirmed independently** |
| Suite | **3,059 passed, 34 skipped** — matches |
| **F1 staging** | **Blocking for commit 1** — v2 reconstruction absent from worktree and index; pure v1→new-name renames staged |
| Stale comments ×2 | Minor; one-line fixes |
