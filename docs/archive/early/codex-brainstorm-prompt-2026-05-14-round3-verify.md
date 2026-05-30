# Codex Brainstorm Request — Round 3: Verification of Round 2 Corrections

**Purpose:** Focused verification that the corrections you flagged in Round 2 were applied correctly, completely, and without unintended cascading effects. Not a fresh review.

**Date:** 2026-05-14.

**Reviewer:** Codex (continuity from Rounds 1 + 2).

**Type:** **Diff-style validation**, not blueprint review. The team applied your Round 2 feedback as faithfully as possible; this round asks: did it land, and did anything break in the process?

Paste the entire content of this file as a single user message into a fresh Codex session.

---

## 1. Your role (unchanged)

You are the same **Senior Staff Engineer & Architect** who delivered the Round 1 and Round 2 reviews. You have not retained Rounds 1+2 in this session, but you have seen the same kind of work product; the team is trusting your continuity of judgement.

**Your job this round:**

1. For each of the **7 strategic decisions** the team locked (D-A1, D-A2, D-B1, D-S0, D-S1, D-S2, D-S3), confirm the decision text + how it propagated to the docs captures your intent — or flag the divergence.
2. For each of the **~13 mechanical corrections** you flagged in Round 2, confirm the correction landed cleanly, or flag where it didn't.
3. Identify any **new issues** surfaced by the corrections (over-correction, under-correction, internal inconsistencies introduced by the edits).
4. Give a fresh top-line verdict per document (was YELLOW → expect GREEN or near-GREEN if Round 2 was fully addressed).

**Do not redesign anything.** **Do not write code.** **Do not re-litigate Round 2 conclusions.** Only verify or flag deviations.

---

## 2. What was applied — the work product to verify

### 2.1 The 7 strategic decisions (now in `docs/task-graphdb-kdb-blueprint.md` §2)

| ID | Decision (one-line) | Round of origin |
|---|---|---|
| **D-A1** | `Page` node-table → `Entity` rename | Round 1 |
| **D-A2** | Source field renames: `compile_state/count/last_compiled_at → ingest_*` (leave `page_type/status/confidence` until producer #2) | Round 1 |
| **D-B1** | B-lite adapter split: thin generic replay core + `graphdb_kdb/adapters/obsidian_runs.py`; no `import kdb_compiler.*` from `graphdb_kdb/` | Round 1 |
| **D-S0** | Stage 9 wiring routes through Obsidian adapter (`sync_current_run`), not direct core call. Single Obsidian→graph entry point for both live sync and replay. | Round 2 (the one critical question) |
| **D-S1** | Multi-producer entity-id namespacing: Obsidian grandfathered as bare slugs; future producers use `<source_type>:<entity_id>` prefix | Round 2 |
| **D-S2** | Rebuild blast radius v1 = always-whole-DB drop, regardless of `--producer` flag; producer-scoped rebuild deferred (tracked as L8 + TR-3) | Round 2 |
| **D-S3** | Adapter declares `supported_journal_versions: ClassVar[list[str]]`; raises `UnsupportedJournalVersionError` on mismatch | Round 2 |

### 2.2 The mechanical corrections applied per your Round 2 findings

| Round 2 finding | Where applied | Verification cue |
|---|---|---|
| **C1** (CRITICAL): Stage 9 wiring contradicts Doc C's "producer never calls core directly" | D-S0 locks adapter routing; Doc C §2 invariant + two-arrow diagram; Doc C §4 adds `sync_current_run` method; Doc C §6 compliance table; Doc A §8 OQ-E9 closed | Doc C §2, §4, §6; Doc A §8 |
| **M1** (MATERIAL): Path collision — D35 reserves `~/Droidoes/GraphDB-KDB/` for Kuzu data, Doc A §1 used same for package code | Doc A §1 reworded: package code at `~/Droidoes/GraphDB-KDB-package/`, data at `~/Droidoes/GraphDB-KDB/` per D35 — two distinct paths | Doc A §1 |
| **M2** (MATERIAL): "Core" vs "package" vocabulary fuzzy in Doc A §5 | Doc A §5 vocabulary note: core = primitives in `graphdb_kdb/{schema,graphdb,ingestor,queries,analytics,verifier,rebuilder}.py`; adapter layer = `adapters/`; package = whole shipping artifact; PR1 applies to core↔producer, not CLI↔adapters | Doc A §5 |
| **M3** (MATERIAL, Doc B): Tombstones overstated — current schema has `Source.moved_to`, not `Entity.moved_to`; deleted-source tombstones are source lineage | Doc B §4 row downgraded to **OPEN DESIGN**; deferred to OQ-M7 (page-history modeling) | Doc B §4 + OQ-M7 |
| **M4** (MATERIAL, Doc B): M0 says "today every compile writes both" — actually Stage 9 wiring is #63.7, not yet shipped | Doc B §5 M0 retitled "target state once #63.7 lands"; added "Status as of 2026-05-14" paragraph noting Stage 9 is unshipped | Doc B §5 M0 |
| **M5** (MATERIAL, Doc B): M1 fallback rule missing — what happens if GraphDB unavailable? | Doc B §5 M1 specifies **fail loud** as locked policy; `GraphDBUnavailableError`; `KDB_CONTEXT_SOURCE` env var as operator-visible escape hatch; rationale: silent fallback would defeat M1's trust-building purpose | Doc B §5 M1 "Fallback behavior" |
| **M6** (MATERIAL, Doc B): M1→M2 validation "benchmark ≥ legacy ±1σ" too soft + expensive | Doc B §6 replaces with explicit `kdb-benchmark --context-source <manifest\|graphdb>` comparison harness; same corpus/model/settings; hard accept-or-reject gate pinned to a `task_C_acceptance_<date>.json` artifact | Doc B §6 |
| **M7** (MATERIAL, Doc A): `git subtree split --prefix=graphdb_kdb` makes a branch with contents at root; the later `git mv graphdb_kdb/*` was wrong | Doc A §6 mechanics rewritten: `git subtree split` then `mkdir graphdb_kdb` + `git mv` back into the subdir; alternative path documented (adjust pyproject `packages` config instead) | Doc A §6 |
| **M8** (MATERIAL, Doc A): `>=0.1,<0.2` conflicts with pre-1.0 minor-bump-for-breaking convention | Doc A §3 Stage 2 replaced with `~=0.1.0` or exact-tag pin; pre-1.0 semver convention spelled out explicitly | Doc A §3 Stage 2 |
| **M9** (MATERIAL, Doc C §3.1/§3.3): Exact field names `success`/`dry_run` conflict with "shapes are producer-specific" | Doc C §3.1 + §3.3 reworded: producer chooses field names; **adapter normalizes** to canonical eligibility values. Indirection explicit: "the contract does NOT require exact field names. The contract requires that the adapter normalizes producer-specific fields into canonical eligibility values when reporting to the generic replay driver." | Doc C §3.1, §3.3 |
| **M10** (MATERIAL, Doc C §4): `is_eligible() → bool` hides skip reasons | Doc C §4 redefined: `EligibilityResult` dataclass with `eligible: bool` + `skip_reason: SkipReason \| None` (Literal type: `'failed' \| 'dry_run' \| 'payload_missing' \| 'invalid_journal' \| 'unsupported_version'`) | Doc C §4 |
| **M11** (MATERIAL, Doc C §4): `discover_runs` mixes discovery + sort | Doc C §4 redefined: `discover_runs() → list[RunDescriptor]` (unsorted); `RunDescriptor` carries `sort_key`; **core** sorts by sort_key. Adapter no longer sorts. | Doc C §4 |
| **M12** (MATERIAL, Doc C §5): "tuple compatible with `apply_compile_result`" too Obsidian-shaped | Doc C §5 rewritten with v1-only Obsidian framing + explicit "Obsidian adapter does this; future adapters target `apply_mutations` via contract refactor path (a) when producer #2 arrives." Path (b) explicitly called out as anti-pattern. | Doc C §5 |
| **M13** (MATERIAL, Doc C §8): "Single-tenant Kuzu directory" wording | Doc C §8 anti-pattern rephrased: "Adapter deletes or rewrites another producer's `source_type` data" — describes the actual hazard; mentions co-tenant design intent. Also added namespace-prefix-skipping anti-pattern (D-S1). | Doc C §8 |
| **cosmetic, Doc A §2**: "13 subcommands" stales | Doc A §2 + §3 Stage 0 reworded to "current subcommand surface — see `--help` for the live list"; the §2 row now uses "current CLI surface"; the inline reference in §3 retains the 13-count parenthetically with the note that it will grow and to not hardcode in docs | Doc A §2, §3 Stage 0 |
| **cosmetic, Doc B §4**: `$s` ambiguous for both source and slug | Doc B §4 Cypher examples changed to `$slug` (entity primary key) / `$source_id` (Source primary key); renamed match variable `s` to `src_e` to avoid confusion | Doc B §4 |
| **Blind spot B3** (rebuild blast radius): not addressed | D-S2 locks v1 = whole-DB; **L8** added to blueprint §14; **TR-3** tracks the producer-scoped design for when producer #2 lands; Doc A anti-pattern row added; CLI warning before whole-DB drop noted | Blueprint §14 L8; §14.1 TR-3; Doc A §7 |
| **Blind spot B4** (verification post-succession): vague | Doc B §6 adds "Post-M3 verification path" sub-section: `graphdb-kdb verify --mode replay` rebuilds to temp DB + structural-equality compare; `verify_against_manifest` retained for source-meta dimension only. TR-2 tracks the work. | Doc B §6; Blueprint §14.1 TR-2 |
| **Blind spot B1** (versioning before Stage 1): | D-S3 lifts version declaration to first-class adapter contract; PR9 invariant added to Doc A §4 | Doc A §4 PR9; Doc C §3.3, §4 |
| **Blind spot B5** (fixture/data policy): | PR10 invariant added to Doc A §4 | Doc A §4 PR10 |
| **Premature P1** (Doc A §5 bundled-forever implication): | Doc A §5 Option A row gained "⚠️ Not implied as the forever-default; revisit at Stage 3" | Doc A §5 |
| **Premature P2** (Doc B §4 tombstones over-commit): | M3 above; downgraded to OPEN DESIGN | Doc B §4 |
| **Premature P3** (Doc C §3 run-shaped artifacts as universal): | Doc C §3 intro adds explicit "Scope caveat — v1 assumes run-shaped artifacts": streaming/event-sourced producers are out-of-contract for v1; would motivate a separate contract doc, not a stretch of this one | Doc C §3 intro |
| **Under-spec U5** (blueprint update after rename pass): | Tracked as **TR-1** in blueprint §14.1 — blueprint §4 schema DDL, §6 API surface, §7 Stage 9 skeleton, §10 test descriptions, §11 sub-task wording all need a mechanical sweep when rename pass executes. To be bundled into proposed sub-task #63.5b. | Blueprint §14.1 TR-1 |

---

## 3. Review priorities (in order)

### Tier 1 — Did the 7 strategic decisions land correctly?

For each of D-A1, D-A2, D-B1, D-S0, D-S1, D-S2, D-S3:

1. Does the **decision text** in the blueprint §2 table capture the substance correctly?
2. Was the decision **propagated** to all docs where it has implications? (D-S0 → Doc A + Doc C; D-S1 → Doc C; D-S2 → Doc A + Blueprint; D-S3 → Doc A + Doc C; etc.)
3. Did the propagation introduce any **new inconsistencies** with locked decisions (D32–D40) or with the team's stated leans?

### Tier 2 — Did each Round 2 finding land correctly?

For each finding in §2.2 of this prompt (C1, M1–M13, blind spots B1/B3/B4/B5, premature P1/P2/P3, under-spec U5):

1. Was the fix applied where indicated?
2. Is the fix **complete** (vs partial)?
3. Did fixing one thing break or weaken something else?

### Tier 3 — Did the corrections introduce new issues?

Anywhere the edits created:

1. **Internal inconsistency** within a doc (e.g., new section conflicts with existing).
2. **Cross-doc drift** (e.g., D-S1 namespace convention in Doc C is described differently in the blueprint).
3. **Over-correction**: a Round 2 issue was over-addressed in a way that creates new awkwardness.
4. **Under-correction**: a Round 2 issue's fix is technically present but operationally weak.

### Tier 4 — Hidden-effect check on the adapter interface

The adapter interface in Doc C §4 was the heaviest revision (M10 + M11 + new `sync_current_run` + new ClassVars). Sanity check:

1. Is the interface as written actually implementable as Python? (e.g., do the type hints work, are the dataclass shapes coherent, would a real adapter author find it usable?)
2. Are the seven critical adapter rules (§4) internally consistent — or do any two of them contradict?
3. Could a producer #2 author build an arxiv adapter against this interface without ambiguity?

---

## 4. What NOT to review (out of scope)

- The 7 strategic decisions themselves — they are locked per your Round 1 + Round 2 recommendations. Verify their landing; don't relitigate the choice.
- Any Round 1 outcomes (D-A1, D-A2, D-B1) revisited.
- Implementation details of #63.6 / #63.7 — those aren't written yet.
- Architecture choices outside the three docs + blueprint diff (Kuzu, NetworkX, physical location, CLI naming).
- Style, formatting, or prose quality — substance only.

---

## 5. Output format

Single markdown response with these sections in order.

```
## Top-line verdict
One sentence per document (Doc A / Doc B / Doc C / blueprint): GREEN | YELLOW | RED, with one-line justification.
Plus one sentence on cross-cutting consistency post-corrections.

## Tier 1 — strategic decisions landing
For each of D-A1, D-A2, D-B1, D-S0, D-S1, D-S2, D-S3:
- **Landing**: clean | needs adjustment | wrong
- **If not clean**: what's off and what to change

## Tier 2 — Round 2 corrections
For each finding (C1, M1–M13, blind spots, premature, under-spec):
- **Landed**: yes | partial | no
- **If partial/no**: what's missing

## Tier 3 — new issues introduced by corrections
For each newly-surfaced issue:
- **Severity**: CRITICAL | MATERIAL | cosmetic
- **Where**: doc / section
- **Issue**: what changed; why it's a problem now
- **Recommendation**: specific

## Tier 4 — adapter interface sanity
Three pass/fail/concern responses to the Tier 4 questions in §3.

## Questions for the team
Genuine ambiguities only. If none, skip.
```

**Be terse.** This is verification, not fresh review. If something is clean, say so in one line and move on. Reserve detailed analysis for issues.

---

# Appendix A — Updated Extraction Roadmap (`docs/graphdb-kdb-extraction-roadmap.md`)

```markdown
{{INSERT_DOC_A_HERE}}
```

---

# Appendix B — Updated Manifest Succession Arc (`docs/manifest-succession-arc.md`)

```markdown
{{INSERT_DOC_B_HERE}}
```

---

# Appendix C — Updated Producer Contract (`docs/graphdb-kdb-producer-contract.md`)

```markdown
{{INSERT_DOC_C_HERE}}
```

---

# Appendix D — Blueprint additions only (D-A1, D-A2, D-B1, D-S0, D-S1, D-S2, D-S3, L8, TR-1, TR-2, TR-3)

The blueprint is large; only the new rows are reproduced here. The 7 decisions are appended to §2's locked-decisions table; L8 is appended to §14; §14.1 is new.

```markdown
{{INSERT_BLUEPRINT_ADDITIONS_HERE}}
```

---

End of brainstorm request. Produce your structured response per §5 above.

**Operational note for the user firing this prompt:** replace the four `{{INSERT_…}}` placeholders with verbatim content. Appendix D is just the new rows from the blueprint (the rest of the blueprint is unchanged from Round 2's context and need not be re-sent).
