# #123 Round 1 Synthesis — opus5 review & vote

Date: 2026-07-25 · Respondent: **opus5** · Reviewing: `2026-07-25-task123-round1-synthesis.md`
Prior record: `2026-07-25-task123-round1-panel-discussion-opus5.md`

## Vote: **APPROVE**

The mechanism (D1), scope guardrail (D5), and determinism mitigation (D6) are sound, and my positions —
including both retractions — are represented faithfully. Two defects to fix before the vision doc; both are
documentation integrity rather than design. Two recommendations that do not block.

---

## Must fix

### 1. §7's D7 ruling answers a different question than D7 asked — the round's one unanimous evaluation finding is now unruled while appearing ratified

**§5-D7 is about *evaluation*:** define what a wrong answer is — held-out truth set over a fixed graph
snapshot, candidate-recall vs selector-precision reported separately, hub-returner adversarial case,
abstention correctness — *before any tuning* (#75 pattern).

**§7-D7 is about *validation*:** closed-world candidate-set membership, live-graph re-verify (active,
canonical), shape checks, FTS-is-not-an-authority, "the graph is the only validator."

These are different decisions. §7-D7's content is correct and should be kept — but it belongs to convergence
**E** (graph-authoritative, fail-closed, read-only), not to D7. As the document stands, finding **G** — the only
catch both external respondents reached independently, through different doors — has no ruling behind it, and a
reader will reasonably believe it does.

**Fix:** renumber the validation ruling (D9, or fold it into D1's validation clause) and rule D7 separately. G
is the finding that determines whether we can distinguish a working selector from a plausible-looking
hub-returner; it should not disappear into a numbering slip.

### 2. D3 is an override of a 3/3 unanimous finding, and the document labels it "RATIFIED"

- §3-D records **"Domain stops being a hard gate"** as 3/3 unanimous.
- §5-D3 proposes **"hard gate removed; prior-with-global-fallback."**
- §7 rules the gate **always on for context-build, no global fallback.**

That is a legitimate call — it is Joseph's to make and the reasoning is sound — but it **inverts** §5-D3 rather
than ratifying it. A reader who reaches §3-D and §5-D3 without reaching §7 will take away the opposite of the
decision.

**Fix:** label §7-D3 explicitly as an override of a 3/3 finding, and annotate §3-D as superseded. Per the
project's own convention, n/n findings may be overridden but not silently.

**On the substance, D3 is right, and I want that on the record as clearly as the objection.** My §0 evidence
shows 10/28 sources starved, but the *motivating* failure sits in the richest bucket: `warren-buffett` against
a value-investing pool of 29–46 entities that already contains Buffett composites, where exact match still
returns nothing. The gate gave that source plenty. The intelligence gap is the defect; starvation is not. And
**"abstention on domain-empty sources is correct-by-design and must never be scored as selector failure"** is
exactly the right reconciliation — it closes the misdiagnosis risk I raised in §0 of my response.

Worth adding to the record: the starvation is largely a **small-corpus artifact.** Six of the ten starved
domains held exactly one source in this 36-source corpus (`geopolitics`, `quotes`, `history`, `psychology`,
`math-statistics-logic`, `personal-finance`). At vault scale those domains populate, and the effect shrinks
without any intervention.

---

## Recommend (non-blocking)

### 3. Buy the cross-domain evidence — D3 makes it nearly free

The one consequence D3's reasoning does not address: with the gate always on for context-build, cross-domain
relevance can never be **discovered**. The 2/486 cross-community-edge statistic from the 2026-07-07 scale probe
may be partly the gate's own shadow — the compiler only ever sees same-domain context, so it only ever writes
same-domain links, so the graph stays single-community, so the probe measures the *consequence* of the gate as
though it were a property of the corpus. That is the same self-fulfilling shape #122 exposed in the legacy
metric, one level up.

D3 already supplies the instrument at no cost: the gate is "an optional query input, default off" for the human
surface, so the global path exists inside the function by construction.

**Proposal:** on one cohort, run the selector twice — domain-scoped and global — and record the delta as
telemetry. No change to production semantics, read-only, and cost is explicitly not a constraint at this stage.
The gate then stays or goes on data rather than on anyone's argument.

### 4. D6 needs a re-call escape hatch

"Replay reads the record, never re-calls" is correct for byte-pinning and reproduction. But it also means
replay can never exercise a **changed** selector — the moment we want to evaluate selector v2 against recorded
runs, read-from-record is precisely the wrong behavior.

**Fix:** one line in the decision — replay-from-record by default for reproduction; explicit opt-in re-call for
selector evaluation.

---

## Confirmed accurate

- **§1's verification of my §0** matches my figures exactly: pool==0 on 10/28 (deepseek), 10/28 (gpt), 10/29
  (gemini), 0/2 (warm).
- **§3-J's reading of the legacy matchers** — `_t2_slug_in_text` matches whole slugs literally so
  `buffett-balance-sheet-rules` can never fire; `_t2_title_in_text` requires verbatim title phrases;
  STRUCTURED ≥ LEGACY on record via NW-9; D-90-12 already marks the sunset.
- **§7-D4's disposition of FTS for T1 / T3 / domain sub-trees** — all three are structural (`SUPPORTS`,
  `LINKS_TO` BFS, `BELONGS_TO`) where text indexing adds nothing. FTS's homes are the human query surface and
  at-scale candidate generation.
- **§7-D6's scoping to T2 only** — T1 and T3 remain deterministic functions of graph state; only the LLM
  selection is stochastic and it feeds only T2.
- **D5's read-only guardrail** holds the #119 line correctly: an LLM relevance judgment must never leak into
  graph identity.

Nothing above blocks the vision doc once the two labels in §3-D/§5-D3/§7-D3 and §5-D7/§7-D7 are corrected.
