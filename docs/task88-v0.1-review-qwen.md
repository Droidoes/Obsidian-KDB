# Task #88 v0.1 Checkpoint — Qwen Review

**Date:** 2026-05-24
**Blueprint reviewed:** `docs/task88-ingestion-pipeline-blueprint.md` v0.1
**Supporting docs consulted:** Producer Contract v1.0, CODEBASE_OVERVIEW.md, JOURNEY.md, session-handoff-2026-05-23-saturday-afternoon.md §Strategic pivot, external-review-panel.md

---

## 1. Convergence

Several elements of the architectural skeleton hold together cleanly:

- **Component decomposition (§2)** — the 5-component split is clean. Separating Source Storage from Trigger is the right seam: storage defines *what can change*; trigger defines *when something did change*. Different change surfaces, different code.
- **Read-in-place + state-tracking-only (D-88-2)** — the vault stays the single source of truth. Copy-into-managed-area doubles storage and creates consistency problems that don't exist yet.
- **Dir-exclusion as the only pre-LLM gate (D-88-3)** — piggybacking worth-verdict on the enrichment call that's already firing per-source is the efficient choice. A separate pre-gate would burn tokens for no context gain.
- **Two-pass worth-judgment (D-88-4)** — structurally necessary. Pass-1 (content context only) and Pass-2 (content + ontology context) each have an information asymmetry the other resolves. Neither is redundant.
- **Subdirs as semantic provenance (D-88-6)** — treating Config A subdirs as gmail-style tags scales; flat structure would not.

---

## 2. Findings

### F1 — Producer Contract alignment gap is the highest-severity omission (§2, §4, review axis 9)

The blueprint states: *"The source storage + enrichment together produce the artifacts [the Producer Contract] specifies."* This assertion is not borne out by the artifact shapes.

Producer Contract v1.0 §3 defines four artifacts per discrete run: mutation payload (`compile_result.json`-analog), scan/state payload (`last_scan.json`-analog), run journal, and sidecar archive. The #88 blueprint's source-storage component emits a per-source state record (`{size, mtime, sha256, ...}`) and the enrichment component emits a per-source enrichment record (`{verdict, domain, sub_domain, property_tags, wikilink_suggestions}`). Neither is any of the four contract artifacts.

The contract's mutation payload expects per-source entries with `source_id`, `summary_slug`, `concept_slugs`, `article_slugs`, `pages`, `compile_meta`. The enrichment output has none of these. **There is a shape gap, and the blueprint does not document what bridges it.**

The contract also assumes **run-shaped artifacts** — discrete invocations producing batched output. The source-storage component (§3.5) does continuous per-file state tracking with no defined run boundary. Who decides when accumulated source changes become a "run"? How are enrichment outputs batched? These questions are first-order design decisions, not implementation details.

**Severity:** This is not a "nice to clarify" gap — it's an unconnected pipe between the ingestion system and the compile pipeline. Without a bridge specification, #88's output cannot consume by the contract.

### F2 — Recompile-trigger logic has an ordering bug (§3.5, review axis 8)

The pseudocode in §3.5:

```
if (size, mtime) == last_seen: skip
elif sha256 == last_seen.sha256: skip (mtime drift only)
elif (dir-path, filename) != last_seen: re-ingest as new (orphan old)
else: re-ingest (content change)
```

The `elif (dir-path, filename) != last_seen` branch is checked **after** the SHA-256 equality check. This means a file that was both moved AND had its content unchanged would take the `sha256 == last_seen.sha256: skip` branch and **not** trigger re-ingestion — even though its dir-path changed, which per D-88-6 should be semantically significant.

This is likely unintentional. The intent per §3.4 is: dir-path changes should always trigger re-ingestion because they change the provenance tag. The current logic would silently suppress this if the content-hash happens to be unchanged.

The fix is to check dir-path/filename **before** SHA-256:

```
if (size, mtime) == last_seen: skip
elif (dir-path, filename) != last_seen: re-ingest as new (orphan old)
elif sha256 == last_seen.sha256: skip (mtime drift only)
else: re-ingest (content change)
```

### F3 — Identity-as-path + move-as-new creates unnecessary LLM cost (§3.2 dimension 3, review axis 2)

Per §3.5, a dir-path change triggers "re-ingest as new (orphan old)." Per §3.4, this is because subdirs are semantic provenance tags. For Config A (raw/), this is correct — a feeder writing to a different subdir is a different provenance category.

For Config B (vault-in-place), the semantics differ. A user reorganizing their vault (moving files between thematic folders) would fire re-ingestion for every moved file. If content is unchanged, the enrichment LLM would process the same content again, producing the same tags and verdict, burning tokens for no ontology gain.

**Recommendation:** the re-ingest-as-new logic should distinguish Config A from Config B. Config A: path change → new source (provenance tag changed). Config B: path change with matching content-hash → update path in-place (same source, new location); re-ingest only if content also changed. This requires the per-source state to track content-hash as a cross-reference key, which it already does (`sha256` in the state schema).

### F4 — Lifecycle dimension is under-specified (§3.2 dimension 5, review axis 2)

The dimension "new / change / delete + dir-as-meta" collapses four distinct operations with different detection costs and semantics:

| Operation | Detection mechanism | Cost | Downstream |
|---|---|---|---|
| New | diff(current_files, previous_files) | O(N) stat | Fresh ingest |
| Content change | SHA-256 comparison | O(file_size) | Re-enrich |
| Path change | (dir, filename) comparison | O(1) | Re-ingest or move |
| Delete | diff(previous_files, current_files) | O(N) stat | Orphan cascade |

Delete-detection is structurally different — it's an **absence** detected by set-difference, not a property of a file. The blueprint acknowledges this (§3.5: "Delete handling is a separate code path in Component #3") but the dimension table doesn't reflect it.

This matters because Component #3 (Trigger) will need to handle each case differently. The dimension decomposition should surface the split, not hide it.

### F5 — "Format" dimension is config-contingent, not architecturally fixed (§3.2 dimension 4, review axis 3)

Both configs read `.md` today because both happen to point at the Obsidian vault. The "SAME" label in the decomposition table implies architectural fixedness. In reality, this is v1-contingent: a third configuration (RSS → HTML, YouTube → transcripts, PDF → text) would necessarily have a different format.

Similarly, "Access pattern" (dimension 2) is marked "SAME" but D-88-2 *mandated* read-in-place for both configs — it's a policy decision, not an inherent identity. A non-vault source (e.g., a downloaded podcast transcript) requires copy-first by definition.

The table should distinguish "architecturally identical" from "contingently identical in v1" so future reviewers don't treat v1 coincidences as structural invariants.

### F6 — Pass-1 attention dilution: single-call is correct for v1, needs an empirical escape hatch (OQ-88-4, review axis 7)

Pass-1 crams four outputs into one LLM call: `verdict` (binary), `domain/sub_domain` (classification), `property_tags` (structured list), `wikilink_suggestions` (generative text). These are genuinely different task shapes — classification, extraction, and generation competing for the same context window.

The verdict (a single bit) is the most critical output, yet it's the smallest. There is a real risk that the LLM's attention is dominated by the larger generative outputs, degrading verdict quality.

However, splitting into two calls doubles the LLM bill before we have empirical evidence that single-call quality is degraded. The right v1 approach: **ship single-call, but monitor output quality.** Add a structural quality gate: if any of the four outputs is null, empty, or structurally degenerate (domain is null on a source with named entities; verdict is missing; tags are empty on a non-trivial source), flag the source for audit. This provides a cheap safety net without burning extra tokens in the happy path.

### F7 — Dir-exclusion hedge watch-rule lacks a concrete cost trigger (D-88-3, review axis 4)

The file-count threshold (5,000+ files) is concrete. The cost threshold ("LLM cost reverts from current promo pricing") is not. Without a specific trigger, this hedge may never fire even if costs silently increase.

Recommendation: tie it to a specific metric — e.g., "average enrichment cost per source exceeds $0.05" or "total monthly enrichment spend exceeds $X." This gives the watch-rule a trigger that actually fires.

### F8 — Pass-2 exception gate needs structural criteria (D-88-5, review axis 6)

Pass-2 as the single permitted new end-A surface is well-justified — it's the necessary architectural counterpart to Pass-1. The slippery-slope risk is that future components could claim the same "necessary counterpart" exception.

The blueprint should encode a structural gate: a future exception to the pivot rule requires demonstrating (a) the proposed end-A surface is the direct counterpart of a specific end-B component, and (b) the end-B component cannot function correctly without it. This isn't a reason to reject D-88-5 — it's a reason to make the exception criteria explicit.

### F9 — Daily Notes exclusion is a non-issue for Config B (OQ-88-5, review axis 4)

OQ-88-5 asks whether Config B should exclude `Daily Notes/` by default. But Config B's location glob is `~/Obsidian/**/*.md`. Daily Notes files are at `~/Obsidian/Daily Notes/2026-05-24.md` — they **would** match the glob. So this is a genuine question, not a non-issue.

However, the deeper question (what is knowledge vs noise for Daily Notes) is correctly deferred to its own discussion. For v1, the pragmatic choice is: **exclude by default in scope-config, user can override.** Daily Notes are meta-commentary about the vault itself, not source material. Including them would burn enrichment tokens on content that Pass-1 would reject anyway.

### F10 — OQ-88-3 (Move-from-compile inventory) is under-specified (§5.4, review axis 11)

Domain/sub_domain extraction is identified as the first move. But the blueprint doesn't survey the compile pipeline systematically for other candidates. Per the "move-don't-duplicate" discipline (handoff §Strategic principles §4), a systematic survey should be part of Component #5 deep design.

Candidates worth surveying:
- Wikilink resolution logic (compile resolves wikilinks to paths; ingestion could emit wikilink suggestions that compile consumes)
- Frontmatter stamping (compile stamps frontmatter; could ingestion pre-stamp some fields?)
- Canonicalization (Stage 6) — could ingestion-side canonicalization reduce compile-side work?

This is not a v1 blocker, but the blueprint should acknowledge the survey as an explicit Component #5 deliverable.

---

## 3. Recommendations

**R1 — Add "Ingestion → Compile bridge" as a first-class v1 design item.** The gap between enrichment output and Producer Contract artifact shape (F1) is the highest-severity omission. Add a §5.6 (or a new component) that documents: (a) how enrichment outputs get assembled into compile entry shape, (b) the field-level mapping (even as a placeholder), (c) who owns the run-boundary/batching decision. **Do not defer to implementation** — this is an architectural seam.

**R2 — Fix recompile-trigger ordering (§3.5 pseudocode).** Check dir-path/filename before SHA-256 (F2). A moved file with unchanged content should still trigger re-ingestion per D-88-6. Current logic silently suppresses this.

**R3 — Differentiate Config A and Config B move semantics (§3.5).** Config A: path change → new source (provenance tag). Config B: path change with matching content-hash → update path in-place; only re-ingest if content also changed (F3). This avoids the 50-file-reorganization LLM-cost bomb.

**R4 — Split lifecycle dimension (§3.2 table).** Separate presence detection (new/existing/deleted) from change detection (content/path/unchanged). Delete detection's absence semantics are structurally different (F4).

**R5 — Mark contingent dimensions in the decomposition table (§3.2).** Annotate "Format" and "Access pattern" as "SAME (contingent in v1; may diverge with new source types)" (F5).

**R6 — Add structural quality gate for Pass-1 single-call (OQ-88-4).** Ship single-call for v1; add a monitor that flags sources where any of the four outputs is null, empty, or structurally degenerate (F6). Re-fire as split-call only for flagged sources.

**R7 — Tie D-88-3 hedge to a concrete cost metric.** Replace "LLM cost reverts from current promo pricing" with a specific threshold (e.g., "$0.05/source") (F7).

**R8 — Add structural gate to D-88-5 exception criteria.** Future pivot-rule exceptions require demonstrating counterpart relationship and necessity (F8).

**R9 — Endorse OQ-88-1 option (a): "Ingestion System" + "feeders".** Disambiguates cleanly. "System" is broad enough for the 5 components + bridge (F1 naming).

**R10 — Daily Notes: exclude by default in Config B scope-config (OQ-88-5).** Meta-commentary about the vault is not source material; defer the deeper knowledge-vs-noise discussion (F9).

**R11 — Endorse explicit Pass-2 mechanism (OQ-88-2).** Implicit ("zero pages = no contribution") is fragile — a compile failure producing zero pages is indistinguishable from a genuinely non-contributing source. Hybrid adds complexity. Explicit adds one field to compile output and one code path in end A (already permitted by D-88-5).

---

## 4. Open Questions

- **OQ-R1 — Run boundary ownership.** Who decides when a batch of source changes becomes a "run" with a `run_id`? The trigger component could batch by time-window, source-count, or manual trigger. This gates the bridge design (R1) and should be addressed in Component #3 deep design.

- **OQ-R2 — Orphan-cascade depth.** When a source is orphaned (moved or deleted), how far does the cascade propagate? `Source` node only? `SUPPORTS` edges? `Entity` nodes with no remaining `SUPPORTS`? The Producer Contract's cleanup-event handling (Task #68) sets a precedent; #88 should state its cascade depth explicitly.

- **OQ-R3 — `.obsidian/` exclusion in Config B scope-rules.** Config B's location glob is `~/Obsidian/**/*.md`. The `.obsidian/` directory typically contains `.json`, `.css`, plugin files — not `.md` files. Is this exclusion a genuine scope-rule or a no-op? If the latter, remove it from scope-config to minimize the config surface.

- **OQ-R4 — Content-hash as identity cross-reference.** If F3's recommendation (Config B move-with-matching-hash → update path in-place) is adopted, the per-source state needs a content-hash index (hash → source_id mapping) to efficiently detect "same content, different path." Is this a new state structure, or can the existing per-source state be queried efficiently?
