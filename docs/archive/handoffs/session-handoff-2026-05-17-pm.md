# Session Handoff — 2026-05-17 (afternoon)

A pure design / deliberation session. **No code changes, no commits.** Two new
docs, two memories.

## What happened

Started the **ingestion-subsystem brainstorm** ("grow the ontology" needs
harvesters that feed `raw/`). Mid-brainstorm, the real foundational question
surfaced — *"what is the ontology for?"* — and the session pivoted to resolving
it.

## New docs

| Doc | Purpose |
|-----|---------|
| `docs/ingestion-subsystem-brainstorm.md` | Working agenda for the ingestion subsystem — framework + 3 harvesters (Droidoes-docs, Obsidian-vault, LLM-chats). Codex-reviewed. |
| `docs/what-is-ontology-for-V1.md` | The kernel-question discussion, captured verbatim — 4 exchanges (X6 clarification, Philosophy A/B, Joseph↔Codex on `raw/` structure, "what is knowledge"). |

## Key resolutions

- **Vocabulary** — harvester (source→`raw/`) / compiler (`raw/`→ontology) /
  graph-ingestor (existing). "Ingestor" was already taken by `graphdb_kdb`.
- **Build order = concrete-first, extract-later.** No upfront framework/ABC.
  Build ≥2 concrete harvesters, then extract the shared framework. Rule of Three.
- **Source removal from `raw/` is soft + two-step** — scan `DELETED` → source
  tombstoned, graph `Source`→`deleted` + SUPPORTS dropped → orphan detection
  flags now-unsupported pages `orphan_candidate`; wiki files survive until
  `kdb-clean orphans`. Don't remove `CODEBASE_OVERVIEW.md`; exclude the
  Obsidian-KDB repo from the harvester instead.
- **Kernel question A/B — RESOLVED.** The graph is an **executable substrate an
  LLM runs operations over** (Option C — GraphRAG global/sensemaking queries,
  HippoRAG associative recall), not a static map (A) and not a hopeful soup (B).
  Ingestion = **B + X6**: broad intake, mechanical role-exclusion only, no KDB
  value-curation gate — community detection self-partitions signal from noise at
  query time. "Ontology" is a misnomer; it's a knowledge **topology**.

## Research grounding (commissioned this session)

GraphRAG (`arXiv:2404.16130`), LazyGraphRAG, HippoRAG (`arXiv:2405.14831` /
`2502.14802`), Pan et al. roadmap (`arXiv:2306.08302`), GraphRAG-vs-vector eval
(`arXiv:2502.11371`). Verdict: *a graph you look at is worthless; a graph you
run algorithms on is the whole point.* Full synthesis + citations in
`what-is-ontology-for-V1.md` §6.2.

## The open fork — next session (Round 5)

> Does KDB need a **domain / schema** to be powerful — typed entities + a
> controlled relationship vocabulary, the way 10x-Learning-Engine's "Adaptive
> Synthetic Munger Engine" draws its power from an *investing* schema? Or can a
> **domain-general** knowledge topology still carry GraphRAG/HippoRAG-class
> operations?
>
> Is KDB the **generalization** of the 10x engine, or should it commit to a
> domain the way 10x did?

Relevant prior art: `~/Droidoes/10x-Learning-Engine/docs/GraphRAG for Adaptive
KB - {Opus4.6,GPT5.2,Gemini3.1,Grok4.2}.md` — already a complete answer to "what
is the ontology for", scoped to investing.

## After Round 5

Resume the ingestion brainstorm at **DD1** (and unblock F2/F3 — `raw/` structure
— which were parked on the kernel question). The agenda lives in
`ingestion-subsystem-brainstorm.md`.

## Code / graph state

Unchanged from the morning handoff — 68 entities, 6 sources, 104 links, 63
supports; verify clean (10 known-benign D39 tax). No code touched this session.
