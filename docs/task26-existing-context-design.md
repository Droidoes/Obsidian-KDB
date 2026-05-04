# Task #26 — EXISTING CONTEXT List Design Review

**Status:** Stub — surfaced from Task #19 Phase 2 dialogue (2026-04-30). To be filled in when Task #26 is worked.
**Reference:** [`docs/TASKS.md`](TASKS.md) → Task #26 (`open`)
**Companion:** [`docs/task19-kpi-design.md`](task19-kpi-design.md) — surfaced this gap when defining M2 (`existing_context_reuse_rate`)

## Why this doc exists

During Task #19 Phase 2 KPI design, M2 (`existing_context_reuse_rate`) was identified as the highest-signal KB-compounding KPI. Defining M2 precisely required understanding *exactly* how the EXISTING CONTEXT list is constructed, what it's *for*, and whether the construction algorithm is well-grounded.

Investigating revealed that **the rationale and effectiveness criteria for the EXISTING CONTEXT list are not documented**. The algorithm exists in code (`kdb_compiler/context_loader.py`) but its design intent, success metrics, and alignment with industry practice have never been written down. Until they are, M2 measures a moving target — we'd be evaluating LLM behavior against an undocumented, unverified design.

This task fills that gap **before** the benchmark scorer goes live. Otherwise we'd build a benchmark that scores against an unproven mechanism.

## Questions this doc must answer

### 1 — What is the objective of the EXISTING CONTEXT list?

What problem does this list solve? What does "good performance" of this mechanism look like in production?

Working hypothesis (to be validated): the list exists to **enable KB compounding** — the LLM can reuse prior slugs verbatim instead of minting near-duplicates, so concepts accumulate rather than fragment. But this is hypothesis, not documented intent. Need to:

- State the design intent precisely (in terms of system-level outcomes, not LLM-level instructions)
- Identify the failure mode the list is meant to prevent
- Articulate what "the list works well" means observationally

### 2 — How is the manifest constructed, and why does it serve as the data source for this list?

The EXISTING CONTEXT list is built from `manifest.json`. Before evaluating the list itself, we need to understand its substrate:

- What does manifest record? What does it NOT record? (Body-free — bodies live in `.md` files.)
- How is manifest updated (when, by which stage)?
- What invariants does manifest maintain?
- Why is manifest the right source for this list (vs. e.g., a vector index, a tag index, full-text search)?

### 3 — Step-by-step: how is the EXISTING CONTEXT list built?

The current algorithm (from `kdb_compiler/context_loader.py:10-17`):

> *"Seeds = (a) pages whose source_refs[].source_id == current_source_id ∪ (b) pages whose slug appears as a whole-word token in source_text. Depth-1 expansion = targets of seeds' outgoing_links[]. Concatenate seeds (sorted by slug) then depth-1 (sorted by slug, seeds excluded). First-seen wins on duplicates. Truncate to page_cap. Seeds placed first."*

To document properly:

- **Step 1 — Seed selection.** Source-match seeds vs. token-match seeds. Why both? What does each contribute?
- **Step 2 — Depth-1 expansion.** Why this depth and not 2, 0, or full transitive? What's the design assumption?
- **Step 3 — Ordering.** Why slug-sort? Why seeds-first?
- **Step 4 — Cap (default 50).** Why this number? What's the LLM context-window justification? What gets dropped first?
- **Edge cases:** how does the algorithm behave for cold-start sources (empty manifest)? For sources with very few token-matches? For sources with hundreds of token-matches?

### 4 — How do we know the list is effective?

What observable, measurable evidence would confirm the list is doing its job?

- **Direct measures** (require ground truth or human judgment): does the list contain the slugs the LLM *should* reuse? What fraction of "should reuse" cases actually have the slug in the context?
- **Indirect measures** (computable without ground truth): vault graph density / connectivity over time, slug-fragmentation rate, average outgoing_links per page, etc.
- **Failure indicators:** what would tell us the list is NOT effective? E.g., chronic slug fragmentation, stable outgoing_links growth despite KB growth, low context-list hit rate.

This question is critical because **M2 in Task #19 cannot be defined precisely until "effective" is defined here.**

### 5 — Industry standard / best practice — are we following them?

Knowledge-graph and retrieval-augmented-generation (RAG) literature has matured significantly. Survey questions:

- **Retrieval architecture for context selection:** what do RAG systems use? BM25? Dense vector retrieval? Hybrid? Where does our token-match heuristic fit?
- **Context window utilization:** is `page_cap=50` aligned with practice? How do production RAG systems decide what to include?
- **Slug-as-token matching:** is this approach (matching the slug literal, not the title or content embedding) common, or is it a homegrown shortcut?
- **Knowledge graph compounding patterns:** do other KB systems use a "reuse existing identifier" instruction to LLMs? What's the standard practice?

Specific systems to reference (preliminary list):
- LangChain / LlamaIndex retrieval pipelines
- Notion AI / Mem.ai / Reflect (consumer-facing KB AIs, if their architecture is public)
- Academic literature on knowledge-graph construction with LLMs (2023+)

### 6 — Are we following them? If not, why? What should change?

Comparison + recommendation:

- Where does our approach align with best practice?
- Where does it diverge? Is the divergence intentional (constraints, simplicity, cost) or accidental (ignorance of better approaches)?
- What changes would bring us closer to best practice? What's the cost-benefit?
- What's the recommendation: stay as-is (with documented justification), incremental refinement, or a redesign?

## Out of scope for Task #26

- Implementing any algorithmic changes (this is a design review, not implementation)
- Re-running benchmarks (Task #19 may re-evaluate M2 once this design review concludes)
- Changing the manifest data structure (Task #27 covers manifest scalability; this task covers context-list logic)

## Dependencies & sequencing

- **Blocks:** Task #19 final M2 definition (cannot lock M2 weight or threshold until "effective" is defined here).
- **Depends on:** none — can be worked anytime after Task #19 Phase 2 review of M1/M3 closes (which is when we identified this gap).
- **Related:** Task #27 (manifest scalability) — separate concern but adjacent. Findings may cross-reference.

## How to fill this doc

When Task #26 is picked up, the worker should:
1. Read all six questions above.
2. Survey relevant code (`context_loader.py`, `planner.py`, `manifest_update.py`).
3. Survey 3–5 industry references (start with LangChain / LlamaIndex / academic survey).
4. Draft answers, fill in this doc.
5. Land a commit; if the conclusion changes M2 design, also edit `docs/task19-kpi-design.md`.
