# #123 Semantic Graph Search Vision v1.1 — opus5 review

Date: 2026-07-25 · Respondent: **opus5** · Reviewing: `2026-07-25-task123-semantic-graph-search-vision.md` (v1.1)
Prior records: `…-round1-panel-discussion-opus5.md` · `…-round1-synthesis-review-opus5.md`

## Verdict

**APPROVE the vision. APPROVE D10 (fat text) with two conditions** — §B1 and §B2 below.

Both must-fixes from my synthesis review landed correctly: the evaluation decision and the validation decision
are now distinct principles (P7 / P8) rather than one number covering two subjects, and P3 carries the explicit
"Joseph's override of a 3/3 panel finding, on record" annotation. P6 picked up the re-call escape hatch.

The v1.1 amendments introduce **one new architectural risk** (§A1) that I would fix before the spec phase, and
D10 has a **quantified scale consequence** the document does not state (§B2). Neither is a reason to withhold
approval; both are cheap now and expensive after implementation.

---

## A. Must fix

### A1. Dissolving the exact/alias path (P1, amendment [10.1]) removes the only deterministic route to T2 — keep it as a degraded-mode fallback

P1 is right that one batched call should be the **happy path**: the marginal cost of including
string-matchable keys is ~zero, and splitting paths creates a real merge/ordering problem. I agree with the
amendment as far as it goes.

What it also does, unintentionally: **it makes every T2 hit conditional on a network call succeeding.** Today
exact-slug resolution is deterministic, free, and cannot fail. Under P1 as written, a selector failure — API
error, timeout, invalid JSON, quarantine — yields an empty T2 *including for keys whose exact match would have
been trivial and certain*. Pass-2 then compiles with no context where previously it had some.

P1 already assigns "fallbacks" to the Python controller but does not say what they are. The natural one is the
path being dissolved:

> **On selector failure, fall back to deterministic exact/alias resolution over the same search space.**

That keeps [10.1]'s merge problem solved (no dual paths in the happy path, no ordering ambiguity — the fallback
only ever runs when the selector produced nothing) while preserving fail-safety. It also costs almost nothing
to implement, since P8 already requires the canonical-validation layer that the fallback would reuse.

**Honest magnitude:** on the 2026-07-25 cold runs, exact-match T2 was 0–2 hits per source, so what is at risk
today is small. The objection is not about magnitude — it is that we would be making a free, certain path
depend on a paid, stochastic one for no benefit, at exactly the moment the graph starts getting rich enough for
exact matches to land more often (warm at-load was 11× cold).

### A2. State the disposition of the existing `T2Mode` machinery

The vision says the selector supplies T2 seeds and that legacy regex does not come along (§7), but it never says
what happens to the three shipped T2 modes. `STRUCTURED` is production; `LAYERED` and `LEGACY` are already
benchmark-only (`compiler/context_loader.py`, and `:554` records NW-9's STRUCTURED ≥ LEGACY finding). Without a
ruling, #123 ships a **fourth** T2 architecture beside three existing ones and inherits their config surface
and tests.

One line in the spec is enough. My recommendation, which dovetails with A1: `LEGACY` and `LAYERED` retire;
`STRUCTURED`'s key-resolution survives *only* as the A1 fallback; the selector becomes the production path.

---

## B. D10 (fat text) — approve with conditions

The reasoning in §5 is sound and answers codex's four requirements properly. Wiki body as content evidence with
the graph retained as sole identity authority is the right split, and routing through the established
`page_writer` / `get_body` authority avoids any parallel store.

### B1. The re-call escape hatch cannot reproduce the search space from a hash alone

P6 persists the **search-space snapshot hash**. That is sufficient for the default path (replay reads the
recorded selection and never re-calls) and it is sufficient to *detect* divergence. It is **not** sufficient for
the opt-in re-call mode — the mode I asked for — because you cannot reconstruct excerpt text from a digest. A
re-call would run selector v2 against *today's* space rather than the recorded one, which destroys the
attribution the escape hatch exists to provide.

Compounding it: §5.2's determinism claim ("the same (graph, wiki) state always yields the same search-space
text") is true only if "state" means **mid-run** state. During a cold run, pass-1.5 for source N reads bodies
written by sources 1…N−1, so the space is a function of intra-run compile order. Replay-from-record is immune;
re-call is not.

**Fix:** persist the projected search-space **payload** (or the per-entity excerpts), not only its hash, when
re-call evaluation is intended. Cost is explicitly not a constraint at this stage, and this is the difference
between an A/B you can trust and one you cannot.

### B2. Fat text trades scale headroom for signal, and the trade lands during vault ingestion — not "later"

§6 defers FTS pre-filtering to a "measured, not guessed" threshold at some future scale. With **thin** text that
deferral was safe: 3KB at 62 pages could have held thousands of entities. With **fat** text the arithmetic
changes materially, and the vault is the next strategic step.

Observed today: 36 sources → ~62 entities (~1.7 entities/source), largest domain pool **46 entities**
(`candidate_universe_size` max, value-investing). The vault holds **1,706 markdown notes**.

| | entities | largest-domain pool | @100-word excerpts | @500-word excerpts |
|---|---|---|---|---|
| today (36 sources) | ~62 | 46 | ~6k tokens | ~30k tokens |
| vault (1,706 notes, same ratio) | ~2,900 | ~800–1,300¹ | ~140k–230k tokens | ~700k–1.1M tokens |

¹ scaling the observed domain skew — value-investing held 46 of ~62 entities in this corpus.

At 500-word excerpts the largest domain subtree **does not fit any current context window** at vault scale, and
even 100 words is at or past the practical limit. So the pre-filter is not a future scale concern — it is a
prerequisite for #123's first realistic workload, which is the ingestion the project has had queued since the
2026-07-07 pivot.

**Fix (spec phase, not blueprint):** compute the excerpt bound *from* a vault-scale entity-count projection and
state the entity-count ceiling at which the bound stops fitting. That makes the excerpt bound a load-bearing
sizing decision rather than a tuning constant, and it tells us up front whether FTS pre-filtering must ship in
v1 rather than "when measured." Cheap to do now; painful to discover mid-ingestion.

---

## C. Clarifications worth one line each

1. **`search_space` — slugs or projected text?** §3's signature has the caller materialize the space, while §5
   makes the body excerpt the space's text. Whether the caller passes an entity set (and the function projects
   text) or passes the finished payload determines who performs the `get_body` reads, where the excerpt rule
   lives, and where the P6 hash is computed. Name it.
2. **Entities vs sources in the return type.** §2.2 states the objective as identifying relevant knowledge
   *sources*; §3 returns *entities*, and Source nodes are never returned. Summary entities proxy for sources in
   practice, but the CLI/MCP surface — D4's designated first FTS consumer — will ask "which of my notes covers
   X," which is a Source-level question the contract as written cannot answer directly. Either confirm entity
   identity is sufficient and adjust §2.2's wording, or record the source-level projection as a known gap.
3. **My cross-domain A/B recommendation is neither adopted nor declined.** P3(b) keeps the domain-empty rate
   visible, which is good, but the experiment I proposed — run one cohort with the domain-scoped space and again
   with the whole graph, record the delta — appears nowhere, including in §6's deferred list. It is read-only,
   changes no production semantics, and is nearly free because P3(c) already gives human callers the
   whole-graph path. It is the only way to learn whether the 2/486 cross-community-edge figure is a property of
   the corpus or a shadow of the gate. Adopt it into the P7 program or record it as declined — silence on it is
   the only outcome I would object to, and I am not re-litigating D3 itself.

---

## D. Affirmations — decisions I think are right and should not drift

- **P1's telemetry annotation** (recording which returned hits *would* have been string-matchable) is better
  than anything I proposed. It directly measures what the LLM adds over dumb matching, which is the hardest
  question P7 has to answer, and it costs one set-intersection.
- **The pass-1.5 naming rationale** (§3) is correct for a reason worth preserving in the record: pass numbers
  are load-bearing across telemetry fields, #117's split leaderboards, and per-pass KPIs. Renumbering would
  have been churn with a real regression surface.
- **P3's abstention rule** — domain-empty abstention is correct-by-design and never scored as selector failure —
  is the right reconciliation of my §0 evidence with the D3 override, and P7 carries it into the evaluation.
- **P8's identity/relevance split** — Kuzu is the runtime identity authority, the D7 truth set is the relevance
  authority, FTS is neither — is the cleanest statement of the #119 line applied to retrieval that has appeared
  in this round.
- **P5 and §7's non-goals**, particularly keeping the parked #83–#87 tier out and refusing legacy-regex revival.

Nothing above blocks the spec phase once A1 and A2 are settled and D10 carries the B1/B2 conditions.
