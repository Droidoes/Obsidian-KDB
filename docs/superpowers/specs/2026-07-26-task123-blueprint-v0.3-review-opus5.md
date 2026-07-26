# #123 Blueprint v0.3 + spec v0.5 — opus5 review of `51a16f2`

Date: 2026-07-26 · Respondent: **opus5** · Reviewing: the diff landed in `51a16f2` (blueprint v0.2 → **v0.3**, spec v0.4 → **v0.5**, ledger + North Star sync)
Prior: round-1 · synthesis · vision · spec v0.1/v0.2/v0.3 · blueprint v0.1 (F1–F8) · blueprint v0.2 concurrence (G1–G8)

## Verdict: **the corrections land — one substantive residual, one contract desync, one internal contradiction**

All eight of my G-items are absorbed, and three landed better than I wrote them (§1). Three items below would
otherwise reach implementation: **H1** is a real ceiling that still isn't a ceiling, **H2** puts the blueprint out
of contract with its own ratified basis on a closed enum, **H3** is a phase-ordering contradiction inside §12.
H4–H6 are one-liners.

---

## 1. Absorption check — G1–G8

| G | v0.3 disposition | Verdict |
|---|---|---|
| **G1** measurement contract | §11: pass-1.5 **out of the scored union** + a non-movement test; cost-centre diagnostics only, no third ranked board; one measurement per search with `prompt_versions {thin,fat}`; `searches_attempted` header; explicit `effective_top_weights` case; reconciliation invariant | **Closed, in the strongest form.** The non-movement test is better than a prose commitment — it makes the silent failure loud. One residual on the *diagnostic* series (H4) and one on the invariant's independence (H5). |
| **G2** provenance carrier | §3.3: per-hit `{slug, first_run_id, match_recency}` from one batched read (new `entity_first_run_ids`), plus a deterministic *representative* per-expression projection; KPI aggregation over the hit-level list | **Closed exactly.** State C and unattributed hits are covered because the facts hang on hits. The synthesis with codex's cardinality question (all-match at hit level, representative at expression level) is cleaner than either input. Verified: `active_entities()` returns only `{title, page_type}` (`kdb_graph/queries.py:247-257`), so the new query is genuinely required, not redundant. One boundary wording gap (H6). |
| **G3** stage-2 bound | §7: re-derived from policy-max 2,500 B/entity ⇒ 94k < 102.4k, 8% margin, verified against fixture max 2,209 B; fat-stage estimator declined with the asymmetry recorded | **Arithmetic absorbed, premise still wrong — H1.** The decline of the fat estimator is defensible *only if* the static bound is real, and it isn't yet. |
| **G4** calibration | §7/§11: provider-reported usage, all three candidates, **timing moved to end of P2**, Joseph fires, P1 not blocked; persisted as `{counting_source, model id, input sha256, input_tokens, bytes/token}` | **Closed, and improved on what I proposed.** codex c-4 is right that a pre-P1 measurement would calibrate a renderer that doesn't exist yet; I had accepted the blueprint's own placement without questioning it. The `counting_source` + input sha256 stamping is a good addition neither of us asked for. Collides with §12's P1 test list (H3). |
| **G5** sub-retry policy | §8: stage entry records the provider's *actual* policy (openai-family 2, gemini none); pass-1's no-backoff posture **adopted deliberately**, recorded as a posture not an oversight | **Closed.** Stating it as an adopted posture with a named later refinement is the right disposition for a non-regression. |
| **G6** `ctx_window` | §2.1/§8: asserted at resolution as a typed config error before any work; `fits_context` non-reuse explained (pre-computed `est_input`, no headroom concept) | **Closed.** The non-reuse rationale is correct — different semantics, not laziness. |
| **G7** serializer clauses | §5: both clauses stated (split on `"\n"`; blank lines indented), golden tests pin them, "any tidy breaks the pins deliberately" | **Closed verbatim.** |
| **G8** naming + plumbing | §2.2/:72 `fat_after_thin_failure` in the `execution` enum; §3.1 names the P3a plumbing incl. the check-the-manifest-first caution | **Closed — but the enum addition is out of contract (H2).** |

**codex's items also land well, and two are worth crediting explicitly:** c-1's branch-specific call-count table
(§8) replaces "two calls per executed search," which was quietly false on four of six terminal paths once F1 and D3
existed; and c-5's **B1 label correction** ("Selected, pending blueprint ratification" — v0.2 said "RATIFIED via
blueprint v0.1 approval to proceed"). I read v0.2's B1 row and let that overclaim pass; codex caught it.

**Spec v0.5 §0** records D1–D4 verbatim with both dissents preserved, and D3's entry carries the full terminal
contract (`completed`/`thin_attempted`/hits `[]`/all expressions unresolved/concordance null/`not_applicable`).
Ledger and North Star are synced in the same commit. That is the discipline working.

---

## 2. Findings

### H1 — the stage-2 bound is still an estimate wearing a bound's clothes (load-bearing)

§7 derives 2,500 B/entity from "275w at the corpus's ~8.8 B/word" and concludes `150 × 2,500 B ≈ 94k < 102.4k`,
an **8% margin** that "holds for any window ≥128k" — and §9 is told to assert it.

Two problems, one arithmetic and one structural.

**Arithmetic.** The ~8.8 B/word figure is mine from the v0.2 review, and it is the *total* block bytes ÷ words for
the single densest **long** page — it silently includes the 188 B of per-entity field/delimiter overhead, and it is
not the densest page. Measured over fixture v1 (excerpt bytes only, overhead added back separately):

| density basis | max excerpt B/word | ⇒ 275-word entity | ⇒ 150 entities |
|---|---:|---:|---:|
| all 163 pages | 10.53 (`summary-vs-code-system-prompts…`, 51w) | 3,026 B | **113k tokens — over the 102.4k budget** |
| pages ≥150 words | 9.35 (`age-related-sleep-changes`, 162w) | 2,700 B | **101k tokens — 1% margin** |
| pages ≥200 words | 8.16 (the 251w page v0.3's figure came from) | 2,375 B | 89k tokens |

2,500 B at 275 words implies 9.09 B/word — and **102 of 163 fixture entities already exceed that density.** They
pass today only because they are short. So the 8% margin is a property of *which pages in this corpus happen to be
long*, not of the policy.

**Structural, and the reason the number keeps moving.** This is its fourth value across four documents (55k → 74k
→ 94k → ?), and it will keep moving, because **the excerpt policy caps words and the budget needs bytes.** A
"word" is whitespace-separated: one 200-character URL is one word. Nothing in policy v1 bounds bytes, so no byte
bound is derivable from it — only estimated from a corpus. At vault scale (~9,600 entities, 60× the fixture, an
unmeasured tail containing code blocks, URLs, tables, and CJK) that estimate has no support at all.

**Fix — put the guarantee in the projector, not in a corpus statistic.** Add a **byte ceiling** to excerpt policy
v2: after the existing 250-word + sentence-extension rule, hard-cut at a fixed byte budget (2,000 B is ample — the
fixture's largest excerpt content is ~2,020 B, so the ceiling binds on approximately nothing today). Then
`150 × (2,000 + 188) ≈ 328 kB ≈ 82k tokens` is a **property of the code**, the §9 test asserts something the
implementation guarantees rather than something the corpus currently happens to satisfy, and the fat-estimator
decline in §7's second bullet becomes genuinely safe rather than conditionally safe.

This is a **spec amendment** (excerpt policy is spec-level, and it bumps `excerpt_policy_version` in the fixture
manifest — a small, contained change, since the fixture would need one regeneration only if the ceiling actually
binds, which it doesn't). I flag it as an amendment deliberately: v0.3 declined my optional fat-estimator on the
correct grounds that R2 is a stage-1 rule, but the alternative it kept isn't sound, and this is the cheaper of the
two ways to make it sound.

### H2 — `fat_after_thin_failure` is out of contract with the ratified spec (load-bearing, documentation)

Blueprint §2.2 (:72) declares `execution` values as
`not_executed | thin_attempted | two_stage_attempted | fat_after_thin_failure`. The ratified spec declares a
**closed three-value enum** in two places — §1.1 (`spec:53`) and §5.1 (`spec:202`) — and codex's absorbed
correction #4 (`spec:409`, v0.4 changelog) named exactly those three. **Spec v0.5 does not amend it**, even though
v0.5 exists in this very commit precisely to synchronize owner rulings into the ratified basis (codex c-5).

So the blueprint's §12 P1 test (`fat_after_thin_failure` naming, `test_contract.py`) would encode a fourth enum
value that the spec forbids. Nobody disputes the value should exist — it's my G8.1 and it's the right name. It
just needs to be *in the spec*: one line in §0 (a D5, or an amendment note under D3's sibling) plus the two enum
sites. Cheap now, confusing later when the spec is the artifact someone reads to implement against.

### H3 — §12's P1 test list contradicts the new calibration timing (minor, but it blocks P1 as written)

§7 and §11 move calibration to **end of P2** and state plainly that "P1 is not blocked on it." §12's **P1** entry
still says `test_budget.py` asserts "estimator asserted against **recorded calibration measurements**" — which
won't exist until after P2. As written, P1's test list cannot go green.

Fix: P1's budget test asserts structure only (threshold arithmetic against a synthetic window, zero-invocation
`budget_exceeded`, never-retried, `max_tokens=2000`, `ctx_window=None` ⇒ typed error). The
assert-against-measurements clause moves to the calibration gate row. Same for the stage-2 bound assertion, which
§12 lists under P1 and §11 lists under P2 — pick one (P2, with the golden bytes).

### H4 — the measurement contract pins the scored population but not three diagnostic series (minor)

§11 says the scored axes' population is unchanged. Three **diagnostic** series are also computed over the whole
`calls` list, not per-pass: `retry_load` (`processing.py:91-95`, `N = len(calls)`), `token_overrun_rate`, and
`repair_rung_rate` (`:98-106`) — all un-suffixed, all rendered. If the `pass1_5` projections join the list that
`compute_processing` receives, those three move even though the scored three don't. State in-or-out; either answer
is fine, silence isn't.

### H5 — the reconciliation invariant needs an independent side to be worth a test (minor)

§11's "total run cost and call count == pass1 + pass1.5 + pass2" — there is **no run-level cost total anywhere in
the repo** (grep: no `total_cost` / `run_cost`; cost exists only as `cost_usd_pass1/2` derived from the same
projections). If both sides of the equality derive from one measurement list, the test is a tautology. It is still
worth having as a **mis-partitioning** check (a dropped or double-counted pass-1.5 record), which is probably what
codex meant — say so, or name the independent counter it reconciles against (the envelope files on disk are the
obvious one: `len(glob("search/*.json"))` vs `searches_attempted`).

### H6 — §3.1's flow doesn't say who performs the provenance read (minor, boundary-relevant)

B1's entire boundary claim is that `kdb_search` never touches Kuzu. The batched `entity_first_run_ids` read is
necessarily **adapter-side** (`compiler/search_adapter.py`, which may import `kdb_graph`) — §3.3 describes the read
but §3.1's six numbered flow steps don't include it, and a reader implementing from §3.1 alone would have to guess.
Add it as step 5.5 ("batched `entity_first_run_ids` over the validated hit slugs → per-hit provenance for the V2
record"), which also makes explicit that it runs post-validation over ≤50 slugs (`max_results`), i.e. one cheap
query per source.

---

## 3. Verified while reviewing

- **`active_entities()` lacks `first_run_id`** — returns `{slug: {title, page_type}}` only
  (`kdb_graph/queries.py:247-257`). §3.3's justification for a new query holds.
- **`first_run_id` is an Entity property set on create** — `kdb_graph/intake.py:316`. Hit-level read needs no
  resolver, as claimed.
- **`execution` enum in the ratified spec is closed at three values** — `spec:53`, `spec:202`, `spec:409` (H2).
- **Sizing table unchanged from v0.2 and still byte-exact** — 14,343 / 4,404 / 112,673 / 38,512 / 107,885 B, all
  reproduced from fixture v1 under §5's grammar including both G7 clauses.
- **Fixture max fat block = 2,209 B** (`value-investing-as-owner-mindset-and-analytical-rigor`, 251 words),
  second 2,164 B — v0.3's citation is correct; it is the *conclusion drawn from it* that H1 disputes.
- **Diagnostic aggregates over the full `calls` list** — `processing.py:46-47` (`N`, `T`), `:91-106`
  (`retry_load`, `token_overrun_rate`, `repair_rung_rate`) (H4).
- **No run-level cost total exists** — cost is only ever aggregated from `PassCallMeasurement` projections (H5).
- **Retry facts as stated** — openai-family `max_retries=2` (`call_model.py:192`, `:273`), gemini none (`:212`),
  `_RETRYABLE` covers anthropic + openai exception types only (`call_model_retry.py:28-37`), pass-1 precedent is
  bare `call_model` (`pass1_caller.py:179`).
- **D4 candidates + windows** — `gpt-5.4-mini` 400,000 / `gemini-3.6-flash` 1,048,576 / `deepseek-v4-flash`
  1,000,000, all live in `common/models.json`. Every entry in H1's table passes the configured pool's 80% budgets;
  H1 is about the *asserted* bound and about vault scale, not about a live overflow risk today.
- **Ledger + North Star** — TASKS.md #123 narrative and the 2026-07-26 Milestone Changelog entry both reflect
  v0.3/v0.5 accurately, including D1–D4 and the "next: ratification → P1, no wait on labels" sequencing.

## 4. What I'd fold before ratification

- **H1** — it changes the excerpt policy (spec touch) and the §9 assertion, so it is cheaper before P1 than after.
- **H2** — one line in spec §0 plus two enum sites; otherwise P1's contract test contradicts the ratified spec.
- **H3** — one clause moved between phase rows.

H4–H6 are one-liners that can ride with the phases that touch them. Nothing here reopens the architecture, and
nothing contradicts D1–D4.

---

## 5. Addendum — audit of the confirmation diff's *removals*

The confirmation diff `…-blueprint-v0.2-to-v0.3-confirmation.diff` is **byte-identical** to `51a16f2`'s diff for
the spec and blueprint (verified), so §§1–4 above already cover its *additions*. Its **removals** are audited
separately in `2026-07-26-task123-blueprint-v0.3-confirmation-diff-audit-opus5.md`, which carries three further
load-bearing findings — v0.3 is 58 lines shorter than v0.2 (296 → 238) and eight commitments disappeared in the
compression, none of them requested by a panel item:

- **H7** — the V2 retained-field list is gone (`candidate_universe_size`, `domain_scope`, `cold_start`, `t1/t2/t3`,
  `max_hops`, `page_cap`, `keys_emitted`): nothing in v0.3 says what V2 carries forward.
- **H8** — the #119 byte-pinning note (§9) and the `search_summary` caller-supplied-snapshot qualifier (§3.2) both
  dropped: the invariant this feature could most easily break no longer appears in the blueprint.
- **H9** — the retained resolvers' "never surfaced as search results, fallback, annotation, comparator, or
  telemetry" enumeration reduced to "identity, not retrieval": R1's enforcement clause.

Plus four minors (SD-5's tracked series, the fail-hard propagation posture, T3's `T1∪T2` seed clause,
`delimiter_collision_guard`'s test hook). Restoring the set costs ~6 lines.
