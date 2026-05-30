# Task #88 v0.1 Checkpoint — Deepseek Review

**Date:** 2026-05-24
**Blueprint reviewed:** `docs/task88-ingestion-pipeline-blueprint.md` v0.1
**Supporting docs consulted:** Producer Contract v1.0, CODEBASE_OVERVIEW.md §Milestone Changelog, JOURNEY.md, session-handoff-2026-05-23-saturday-afternoon.md §Strategic pivot, external-review-panel.md

---

## 1. Convergence

The architectural skeleton is sound at the structural level. The following hold together cleanly:

- **5-component decomposition (§2)** is the right granularity. Enrichment / Source Storage / Trigger / Model-selection / Move-from-compile each have non-overlapping responsibilities. Separating Source Storage from Trigger is particularly important — storage defines *what changed*; trigger defines *when to act on it*. These have different change cadences.
- **Read-in-place (D-88-2)** is the right call. Copy-into-managed-area would create a two-source-of-truth problem exactly as the decision rationale states. The state-tracking-only model keeps the vault as the single authoritative store.
- **Two-pass worth-judgment (D-88-4)** is architecturally necessary. Pass-1 without ontology context cannot make a definitive worth call; Pass-2 without Pass-1 would force compile to re-evaluate every source from scratch. The split is load-bearing.
- **Dir-exclusion as general-purpose (§3.3)** — correctly frames it as more than a circularity guard. Prevents future reviewers from collapsing the capability.
- **Pass-1 binary with bias-to-inclusion (§4.3)** — "uncertain → pass" is the right default. False-rejects are invisible; false-includes get caught at Pass-2. The asymmetry favors the auditable path.

## 2. Findings

### F1 — Producer Contract gap: missing intermediate layer (§9, review axis 9)

> "#88's source storage + enrichment together produce the artifacts this contract specifies."

The blueprint asserts alignment but never maps **how**. The Producer Contract v1.0 §3 requires four artifacts emitted per discrete run: mutation payload, scan/state payload, run journal, and sidecar archive. The source-storage component (§3.5) defines a per-source state schema (`{size, mtime, sha256, dir-path, filename, last-ingest-time, feeder-id}`) — this is a state-tracking record, not any of the four contract artifacts.

The enrichment output (§4.1) emits `{verdict, domain, sub_domain, property_tags, wikilink_suggestions}` per source — this is a per-source enrichment record, also not any of the four contract artifacts.

**The missing piece:** a component (or sub-component) that assembles enrichment outputs into the compile-side entry shape. The Producer Contract's `compile_result.json` analog expects per-source records with `source_id`, `summary_slug`, `concept_slugs`, `article_slugs`, `pages`, etc. The enrichment output has none of these fields. Something — the compile pipeline or a new ingestion-side assembler — must bridge this gap. The blueprint mentions Component #5 (Move-from-compile) as owning domain/sub_domain extraction, but that's one field; the full shape-mapping is unaddressed.

**Second conflict:** The Producer Contract assumes **discrete runs** — a compile invocation that produces one set of artifacts. The source-storage component (§3.5) does **continuous change-detection** — per-file state tracking with no natural run boundary. The contract's `run_id` concept has no analog in the source-storage component. How do per-source enrichment outputs get batched into runs? Who owns the batching decision? This is a first-order design question the blueprint doesn't surface.

> **Codex-specific cross-check** (per review prompt §9, item 4): the D-83/84-6 schema-grounded catch precedent applies here. The blueprint's claim of contract alignment should be verified against the contract's actual artifact shape — just as D-83/84-6 caught Page vs Source schema drift by checking against the real schema file. The gap is analogous: the blueprint describes artifacts (per-source state + per-source enrichment) that don't match the contract's required artifact shape.

### F2 — Identity dimension is underspecified (§3.2 dimension 3, review axis 2)

> "Identity scheme: vault-relative path"

The dimension decomposition claims identity = vault-relative path. But the change-detection logic (§3.5) tells a different story:

```
if (dir-path, filename) != last_seen: re-ingest as new (orphan old)
```

This means path IS identity — a file moved to a different directory is treated as a **new source**, and the old path is orphaned. This is a defensible choice (path-as-identity is simple and deterministic) but has two unexamined costs:

1. **No rename-stability.** A user renaming `Investing/buffett-notes.md` → `Investing/buffett-philosophy.md` produces a new source entity. The old source is orphaned; any graph entities derived from it lose provenance unless the orphan-cascade preserves them. The review axis asks: "should identity include content-hash for rename-stability?" — the blueprint's answer is implicitly no, but that choice should be **explicit** with acknowledged trade-offs.

2. **Move ≠ new content.** Per §3.4, dir-path changes trigger re-ingestion because "subdirs are semantic provenance tags." But for Config B (user-organized vault), moving 50 files between folders during routine reorganization would fire 50 enrichment LLM calls for content that hasn't changed. The recompile-trigger logic should check content-hash BEFORE treating a move as a new source — if `sha256` matches a known hash under a different path, the system should recognize it as the same source entity that moved, not a new one.

### F3 — Lifecycle dimension conceals sub-dimension complexity (§3.2 dimension 5, review axis 2)

> "Lifecycle: new / change / delete + dir-as-meta"

The review axis asks: "Is 'lifecycle' actually multiple sub-dimensions (new-detection vs change-detection vs delete-detection vs move-detection have different costs and semantics)?" **Yes.** The change-detection signal table (§3.5) implicitly acknowledges this — Tier 1 (size+mtime), Tier 2 (hash + filename + dir-path), and Tier 3 (our-state) have different costs, different trigger behaviors, and different downstream effects. The "lifecycle" dimension in the 6-dimension framework collapses these into one row, which understates their differences.

Delete-detection is particularly different from the others: it's not a property of the source file (a deleted file has no properties to observe) — it's an **absence** detected by diffing the current file listing against the previous state. The blueprint acknowledges this (§3.5: "Delete handling is a separate code path in Component #3") but the dimension decomposition doesn't reflect it.

**Recommendation:** split "lifecycle" into at least two dimensions: (a) **presence detection** (new, existing, deleted) — driven by filesystem enumeration; and (b) **change detection** (content-changed, path-changed, unchanged) — driven by metadata comparison. These have different inputs and different costs.

### F4 — "One component, two configurations" abstraction is contingently true (§3.1, review axis 3)

> "5 of 6 dimensions are identical across both configurations."

This is true for v1, but two of the "SAME" dimensions are **contingently** same, not architecturally same:

- **Format (§3.2 dimension 4):** both configs read `.md` because both happen to point at the Obsidian vault. A third configuration (RSS feeds → HTML, YouTube → transcripts, PDFs) would have a different format. The dimension is correctly identified but the "SAME" label understates its config-sensitivity.
- **Access pattern (§3.2 dimension 2):** `Read-in-place` is SAME only because D-88-2 mandates it for all configurations. If a future non-vault source requires copy-first (e.g., downloading a YouTube transcript before processing), the dimension changes.

Neither breaks the abstraction, but labeling these as "SAME" in the decomposition table risks future reviewers treating them as architecturally fixed rather than config-sensitive. The table should distinguish "architecturally identical" from "contingently identical in v1."

### F5 — Slippery slope concern on D-88-5 is real but manageable (§4.4, review axis 6)

> "Pass-2 is the only permitted new surface on end A under the pivot rule."

The exception is well-justified — Pass-2 is the **necessary architectural counterpart** to Pass-1. Without it, Pass-1 alone gates compile entry on content-only judgment, which is strictly worse than no gating at all (false-rejects are invisible). The defense is structural: Pass-2 doesn't just "improve" end A; it completes a split whose other half lives in end B.

The slippery-slope risk is that future components could claim the same "necessary counterpart" exception. The blueprint should encode a **structural gate**: a future exception requires demonstrating that (a) the new end-A surface is the direct counterpart of a specific end-B component, and (b) the end-B component cannot function correctly without it. This isn't a reason to reject D-88-5 — it's a reason to make the exception criteria explicit so Joseph can evaluate future claims consistently.

### F6 — Pass-1 attention dilution risk is real but overcomplicating now is premature (OQ-88-4, review axis 7)

> "Pass-1 currently crams four outputs into one LLM call: verdict + domain/sub_domain + property_tags + wikilink_suggestions."

The risk is genuine: the worth-verdict is a single binary signal competing for attention with larger generative outputs (tags + wikilinks). If the LLM's attention is a finite budget, the richest outputs consume the most of it.

However, splitting into two calls doubles cost before we have empirical evidence that single-call quality is degraded. Recommendation: ship v1 as single-call, but add a **quality gate** — if any of the four output fields is null or structurally malformed (domain is null but the source has named entities; verdict is missing; tags are empty array on a non-trivial source), re-fire as two separate calls. This keeps the happy path cheap while providing a safety net. The gate's thresholds can be tuned with real-corpus data.

### F7 — Dir-exclusion hedge clause watch-rule is underspecified (D-88-3, review axis 4)

> "if the vault grows large (5,000+ files) AND LLM cost reverts from current promo pricing, revisit."

"Large" has a concrete threshold (5,000 files), which is good. But "LLM cost reverts from current promo pricing" is vague — what pricing? Anthropic's current tier? A specific $/1M-token threshold? Without a concrete cost trigger, the watch-rule may never fire even if costs silently triple. Tie it to a specific metric: e.g., "average enrichment cost per source exceeds $X" or "total monthly enrichment spend exceeds $Y."

## 3. Recommendations

**R1 — Add "Ingestion → Compile bridge" as a v1 component (or sub-component of #5).** The gap between enrichment output and Producer Contract artifact shape is a first-order missing piece (F1). Without it, the blueprint describes two halves of a pipeline that don't connect. Minimum viable: a §5.6 subsection documenting (a) that enrichment outputs get assembled into the compile entry shape, (b) what the assembly mapping is (even if just a placeholder), and (c) who owns the batching-into-runs decision. **Do not defer this to implementation** — it's an architectural seam, not an implementation detail.

**R2 — Make path-as-identity trade-off explicit (§3.2).** Add a note to dimension 3: "Identity = vault-relative path. Trade-off: no rename-stability. A moved or renamed file is treated as a new source; the old path is orphaned. Graph entities from the old source must be preserved by the orphan-cascade (Component #3 delete-handling)." This closes the review axis question about content-hash identity.

**R3 — Add content-hash check before move-triggered re-ingest (§3.5).** Before treating a dir-path change as "re-ingest as new," check whether the content-hash matches a known hash at a different path. If it does, recognize the move and update the path — don't create a new source. This avoids the 50-file-reorganization LLM-cost bomb for Config B.

**R4 — Split the lifecycle dimension (§3.2).** Per F3: `presence detection` (new/existing/deleted) and `change detection` (content/path/unchanged). Delete detection's "absence from filesystem" semantics are genuinely different from the other lifecycle events.

**R5 — Add structural gate to D-88-5 exception criteria (§4.4).** Amend D-88-5 with: "Future exceptions require demonstrating that (a) the proposed end-A surface is the direct counterpart of a specific end-B component, and (b) the end-B component cannot function correctly without it."

**R6 — Distinguish architecturally-fixed from contingently-same dimensions (§3.2 table).** Add a column or annotation: "Format" and "Access pattern" are marked as "SAME (contingent in v1; may diverge with new configs)."

**R7 — Tie D-88-3 hedge to a concrete cost metric.** Replace "LLM cost reverts from current promo pricing" with a specific threshold (e.g., "$0.05 average enrichment cost per source, sampled monthly").

**R8 — Endorse explicit Pass-2 (OQ-88-2 option "explicit").** Implicit ("zero output = no contribution") is fragile — a compile failure producing zero pages is indistinguishable from a genuinely non-contributing source. Hybrid adds complexity without benefit. Explicit adds one field to the compile output and one code path in end A (already permitted by D-88-5).

**R9 — Endorse (a) for OQ-88-1 (vocabulary).** "Ingestion System" + "feeders" for source-producers. Option (b) keeps the ambiguity; (a) disambiguates cleanly. "System" is broad enough to contain the 5 components + the compile bridge.

## 4. Open Questions

- **OQ-R1 — Run-boundary ownership.** Who decides when a batch of source-changes becomes a "run"? The trigger component could batch by time-window, by source-count, or by manual trigger. This decision gates the F1 bridge design. Recommend Component #3 deep-design as the forum.

- **OQ-R2 — Orphan-cascade depth.** When a source is orphaned (moved or deleted), how far does the cascade propagate? Remove the `Source` node only? Remove all `SUPPORTS` edges? Remove orphaned `Entity` nodes with no remaining `SUPPORTS`? The Producer Contract's cleanup-event handling (Task #68 pattern) suggests a precedent, but #88's delete-handling should state its cascade depth explicitly.

- **OQ-R3 — Config B scope: `.obsidian/` exclusion is listed as scope-rule (§3.2 dimension 6) but `.obsidian/` contains plugins, themes, workspace config — not markdown sources. Is this a genuine exclusion or a non-issue (the location glob `~/Obsidian/**/*.md` already wouldn't match `.obsidian/` contents)? If the latter, remove it from scope-rules to keep the config surface minimal.
