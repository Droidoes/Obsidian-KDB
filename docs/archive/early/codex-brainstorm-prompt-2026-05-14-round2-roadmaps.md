# Codex Brainstorm Request — Round 2: Extraction Roadmap, Manifest Succession, Producer Contract

**Purpose:** External architectural review of three companion documents drafted to durably capture the team's vision for GraphDB-KDB's evolution from "Python package inside Obsidian-KDB" to "standalone reusable package serving multiple producers and consumers."

**Date:** 2026-05-14.

**Reviewer:** Codex (or any senior-engineer-grade LLM with a 200K+ context window).

**Type:** **Document review**, not blueprint review. Three docs are the artifact; the question is whether the captured vision is sound, internally consistent across the three, and free of blind spots.

**Context for the reviewer:** This is the second-round brainstorm. The first round (2026-05-14 morning, `docs/codex-brainstorm-prompt-2026-05-14-schema-and-rebuilder.md`) addressed two specific open architectural questions: schema generality (Q-A) and rebuilder location (Q-B). Your prior responses produced two upgrades:

- **Q-A → "D + semantic rename pass"**: `Page → Entity`; surgical Source field renames (`compile_state/count/last_compiled_at → ingest_*`); leave `page_type/status/confidence` (values still Obsidian-flavored).
- **Q-B → "B-lite (adapter split)"**: thin generic replay core in `graphdb_kdb/rebuilder.py` + producer-specific logic isolated to `graphdb_kdb/adapters/obsidian_runs.py`; coupling rule "no Python import of producer code"; honest naming (`rebuild_from_obsidian_runs()`).

Your "biggest missing item" feedback was a formal producer-contract document. Combined with a manifest-succession-arc concern the team had raised separately, this prompted three companion documents — now drafted, attached as appendices, and the subject of this round's review.

Paste the entire content of this file as a single user message into a fresh Codex session.

---

## 1. Your role

You are a **Senior Staff Engineer & Architect** acting as an external peer reviewer of architectural intent documents. Three documents are attached; your job is to:

1. Assess whether each captures the right things, at the right level of detail, with no blind spots.
2. Identify inconsistencies *across* the three documents (the cross-cutting check).
3. Flag premature commitments (over-specification of future stages) and under-specification (decisions that should be made now but are deferred).
4. Surface architectural risks the team has not yet considered.
5. Push back on team leans where warranted.

You are reviewing **forward-looking architectural vision**, not code. The output will guide whether these documents are ready to lock as durable artifacts.

**Do not write code.** **Do not redesign anything.** Focus on whether the documents are sound, complete, internally consistent, and free of latent problems.

---

## 2. Project context (load-bearing prior decisions)

These are durable team norms and decisions captured from prior sessions. Treat them as given; don't re-litigate.

- **The reframe (2026-05-10)**: KDB is a raw-text → knowledge-graph compiler. Wiki pages and `manifest.json` are *renderings* of the graph; the graph is the architectural primitive. Memory: `project_graphdb_kdb_refoundation`.
- **Locked decisions D32–D40** in `docs/task-graphdb-kdb-blueprint.md`. Highlights:
  - D32 (tempered): storage layer multi-source; ingestion API Obsidian-flavored for v1.
  - D34: independence-by-shared-upstream. Manifest and GraphDB each consume `compile_result` directly; neither reads the other's store.
  - D35: Kuzu data directory at `~/Droidoes/GraphDB-KDB/` (physical separation from `Obsidian-KDB/`).
  - D38: Stage 9 pipeline integration is non-fatal.
  - D39: replay eligibility filter `success=true AND dry_run=false AND payload_present`.
- **Sub-tasks #63.1 through #63.5 shipped**: schema, ingestion, query API, hybrid analytics, verifier. 76/76 tests green.
- **#63.6 (rebuilder), #63.7 (Stage 9 wiring), #63.8 (docs), #63.9 (snapshot)** still ahead.
- **B-lite + rename pass locked from Round 1**: `Page → Entity`, surgical Source renames, B-lite adapter split.
- **CLI naming**: `graphdb-kdb` for the multi-source ontology layer; `kdb-graph` reserved for a future Obsidian-graph-view utility (out of scope).
- **Storage**: Kuzu 0.11.3 (D33).
- **Analytics hybrid**: Cypher fetches topology; NetworkX/python-louvain computes (D40).

---

## 3. The three documents under review

Attached as Appendices A, B, C below:

| Doc | Purpose | Status |
|---|---|---|
| **A. `docs/graphdb-kdb-extraction-roadmap.md`** | Defines the 5-stage path from monorepo to standalone PyPI package. Captures invariants (PR1–PR8) that must be maintained, migration mechanics, anti-patterns, open questions. | ~280 lines, drafted 2026-05-14 |
| **B. `docs/manifest-succession-arc.md`** | Defines manifest.json's evolution from swiss-knife (source meta + pseudo-ontology) to narrow source-meta ledger. Captures stages M0–M4, field-by-field migration plan, validation gates. | ~230 lines, drafted 2026-05-14 |
| **C. `docs/graphdb-kdb-producer-contract.md`** | Defines what GraphDB-KDB expects from any producer (4 artifacts: mutation payload, scan/state payload, run journal, sidecar archive) and the adapter interface that bridges them to graph mutations. Includes new-producer authoring checklist. | ~280 lines, drafted 2026-05-14 |

These docs are intended to live alongside `docs/task-graphdb-kdb-blueprint.md` as the durable architectural-intent record for GraphDB-KDB.

---

## 4. Review priorities (in order)

### Tier 1 — Cross-cutting consistency

1. **Three-doc internal consistency.** Do the three documents agree on:
   - What the end-state looks like (standalone package; manifest narrowed; producer contract honored)?
   - The role of the Obsidian adapter (where it lives, what it does, when it moves)?
   - The triggers for stage transitions (do triggers in one doc cohere with triggers in another)?
   - Any contradictions between the extraction stages (0–4) and the manifest stages (M0–M4)?

2. **D32-tempered through-line.** D32 says "storage layer source-agnostic; ingestion API Obsidian-flavored v1." Do all three docs honor this consistently, or does any one of them re-open a settled decision?

3. **Independence claim (D34) preservation.** The extraction roadmap PR1 (no upward imports) and the producer-contract adapter rule (no Python import of producer code) both encode D34's discipline. Are they consistent? Is anything orphaned between them?

### Tier 2 — Per-document soundness

4. **Extraction roadmap (Doc A)**:
   - Are the 5 stages right-sized? Anything that should be split or merged?
   - Are PR1–PR8 the right invariants? Anything missing? Anything over-specified?
   - Anti-patterns: any common-failure-mode the team has missed?
   - Migration mechanics (§6 git-subtree-split commands): correct?

5. **Manifest succession arc (Doc B)**:
   - Is the field-by-field migration plan (§4) accurate against today's manifest shape?
   - Is the M0→M4 staging sound, or are any stages unnecessary / missing?
   - Validation gates (§6): are they verifiable as stated, or are some too soft to act on?
   - Anti-patterns: anything missing?

6. **Producer contract (Doc C)**:
   - Four artifacts (mutation payload, scan/state payload, run journal, sidecar archive): are these the right primitives, or is the abstraction wrong?
   - Adapter interface (§4): right shape? Are the four methods (`discover_runs`, `is_eligible`, `load_payload`, `apply`) the right primitives, or should they be different / fewer / more?
   - The "no Python import of producer code" rule: is it actually enforceable in practice? What happens if a producer's JSON shape evolves and the adapter needs to handle both versions?
   - Authoring checklist (§7): would this actually be sufficient for someone writing producer #2?

### Tier 3 — Blind spots

7. **What the docs collectively don't address.** Pretend you're a future maintainer 12 months from now, picking these up cold. What questions would you want answered that none of the three docs answer?

8. **Premature commitments.** Anywhere we've over-specified a future stage in a way that locks us out of better options when the time comes?

9. **Under-specification.** Anywhere we've punted on a decision that, in retrospect, should be made now while we have the context?

10. **The relationship to `docs/task-graphdb-kdb-blueprint.md`.** Do these three docs supersede parts of the blueprint? Should they be cross-referenced more aggressively? Are there contradictions between the blueprint and these three companion docs?

---

## 5. What NOT to review (out of scope)

- The B-lite vs C / Page-Entity-rename decisions from Round 1 — those are locked.
- The Kuzu choice (D33) / NetworkX hybrid (D40) / physical location (D35) / CLI naming.
- The technical correctness of #63.1–#63.5 code that has already shipped (76/76 tests green; not the subject of this review).
- Style / formatting of the docs themselves — substance only.
- Implementation of #63.6 / #63.7 / #63.8 / #63.9 — not yet started; out of scope for these vision docs.

---

## 6. Output format

Produce a single markdown response with these sections in order. Use the headers verbatim.

```
## Top-line verdict
GREEN | YELLOW | RED — one sentence per document, plus one sentence on cross-cutting consistency.

## Cross-cutting findings (priority 1)
Inconsistencies, contradictions, or seam-issues across the three docs. For each:
- **Severity**: CRITICAL | MATERIAL
- **Docs involved**: A / B / C / blueprint
- **Issue**: what you see
- **Recommendation**: specific

## Doc A — Extraction roadmap
- Findings (CRITICAL / MATERIAL / cosmetic) with locations (§ / table row)
- What looks right (3–6 bullets)

## Doc B — Manifest succession arc
- Same structure as Doc A.

## Doc C — Producer contract
- Same structure as Doc A.

## Blind spots (priority 3)
What 12-months-from-now-you would want answered that none of the three docs answer. Be concrete.

## Premature commitments
Anywhere we've locked a future-stage decision too early. Be concrete; cite section / decision.

## Under-specification
Anywhere we've punted a decision that should be made now. Be concrete; cite section.

## Questions for the team
Genuine ambiguities only. If none, skip.
```

**Be opinionated.** **Be concrete.** Cite sections / table rows / decision IDs. Don't pad. Don't summarize what you read unless required to substantiate a claim.

If you find a contradiction with the constraint notes (§2), surface it as CRITICAL — don't silently re-litigate the locked decision.

---

# Appendix A — Extraction Roadmap (`docs/graphdb-kdb-extraction-roadmap.md`)

The five-stage path from monorepo to standalone package; invariants and anti-patterns. Drafted 2026-05-14.

```markdown
{{INSERT_DOC_A_HERE}}
```

---

# Appendix B — Manifest Succession Arc (`docs/manifest-succession-arc.md`)

The transition of manifest.json from swiss-knife to source-meta ledger; field-by-field migration plan. Drafted 2026-05-14.

```markdown
{{INSERT_DOC_B_HERE}}
```

---

# Appendix C — Producer Contract (`docs/graphdb-kdb-producer-contract.md`)

What GraphDB-KDB expects from any producer; adapter interface; authoring checklist. Drafted 2026-05-14.

```markdown
{{INSERT_DOC_C_HERE}}
```

---

End of brainstorm request. Produce your structured response per §6 above.

**Operational note for the user firing this prompt:** before pasting, replace the three `{{INSERT_DOC_X_HERE}}` placeholders with the verbatim content of the three docs (or substitute paste-in-place per Codex's preferred input method). The placeholders exist because the three docs together are ~800 lines and the team prefers to compose the prompt explicitly rather than inline everything in this scaffold file.
