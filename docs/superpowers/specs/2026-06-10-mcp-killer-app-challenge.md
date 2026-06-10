# Challenge — Name the Killer App for the KDB Graph + MCP Server

**Date:** 2026-06-10
**Type:** Generative ideation challenge (NOT a review)
**Why:** The read-only MCP server (design:
`docs/superpowers/specs/2026-06-10-graph-access-package-design.md`) needs a named,
load-bearing consumer — its own "Gate" query. The placeholder *"what have I
captured about X, and what connects to it?"* is **retrieval**, which lexical
search already does. That is the FLOOR, not the bar. We want the single
highest-value use the graph makes possible that nothing else can.

Save responses to:
`docs/superpowers/specs/reviews/2026-06-10-mcp-killer-app/<MODEL>.md`

---

## What KDB is (so your proposal fits the real asset)

KDB compiles a single user's raw notes/reading (an Obsidian vault) into a
knowledge graph — a *personal* corpus of what one person has read, captured, and
thought, NOT a public web/encyclopedia. The graph is the durable asset; a chat
app / agent is the intended interactive consumer via a read-only MCP server.

**Graph schema (Kuzu):**
- **Nodes:** `Entity` (page_type ∈ summary|concept|article — LLM-extracted ideas),
  `Source` (an ingested document, with `domain`, `author`, `summary`),
  `Domain` (topic bucket), `Claim` (a proposition — schema v2.2, populated by the
  in-progress O1 promotion pipeline #83–86).
- **Edges:** `LINKS_TO` (Entity→Entity, LLM-decided wikilinks in bodies),
  `SUPPORTS` (Source→Entity — which documents ground which idea), `BELONGS_TO`
  (Entity→Domain), `ALIAS_OF` (Entity→Entity), and the Claim layer:
  `EVIDENCES` (Source→Claim), `ABOUT` (Claim→Entity), `SUPERSEDES` /
  `CONTRADICTS` / `QUALIFIES` (Claim→Claim).
- **Thin nodes:** bodies are NOT in the graph; they live in a wiki/ content store,
  joined on demand via `get_body(slug)`.
- **Analytics ALREADY built** (`kdb_graph/analytics.py`): `pagerank`,
  `communities` (Louvain), `structural_holes`.

**Two horizons:**
- **1.0 (live now):** Entity / Source / Domain / LINKS_TO / SUPPORTS / BELONGS_TO
  + the three analytics above.
- **2.0 (being built):** the Claim layer (CONTRADICTS / SUPERSEDES / QUALIFIES /
  EVIDENCES / ABOUT).

## The task

Propose **ONE killer app/query** — your single best, defended — that justifies the
MCP server's existence. Not a list of ten; the one you'd stake the design on.

## Quality bar (this is what we're judging on)

A strong proposal is:
1. **Graph-native** — name *why lexical/full-text search fundamentally cannot do
   it*. If grep over the bodies answers it, it's the floor — discard it.
2. **Metacognitive or generative over retrieval** — it should tell the user
   something about *their own knowledge* (gaps, tensions, ungrounded beliefs,
   latent bridges, how their thinking moved) or *generate new connections/ideas*,
   not just fetch what's already explicit. Retrieval is table stakes.
3. **Specific to the schema** — name the exact nodes/edges/analytics it traverses
   (e.g. "low SUPPORTS-degree on high-LINKS_TO-indegree entities", "a single
   bridge edge between two Louvain communities", "CONTRADICTS chains").
4. **Recurring + real** — a single user would reach for it repeatedly, not once.
5. **Honest about horizon** — answerable on the **1.0** graph today, or clearly
   name what **2.0** capability it needs and why it's worth waiting for.

## Floor examples (do NOT propose these — beat them)

- "What have I captured about X?" / "What connects to X?" — retrieval.
- "Summarize my notes on Y." — the LLM + search already does this.
- Anything a `grep` + an LLM read of the hits would answer.

## Required output (keep it tight — no preamble)

1. **The app, in one sentence** (the user-facing question or action).
2. **Why search can't do it** (the graph-native justification).
3. **The mechanism** — exact nodes/edges/analytics + the MCP tools it composes
   (and any new tool it implies beyond the day-one six + `get_body`).
4. **Horizon** — 1.0-now or 2.0-needs-Claim-layer.
5. **Why it's the highest-value one** — what it changes for the user.
6. *(optional)* a second-best runner-up in one line.

## Output rules (strict)

- Do NOT modify any repo file, run any build, or touch git. Ideation only.
- Write your ENTIRE response to exactly one file:
  `docs/superpowers/specs/reviews/2026-06-10-mcp-killer-app/<MODEL>.md`
- Nothing outside that file.

---

## Prompt (copy-paste; swap `<MODEL>` per model)

```
You are a senior systems thinker proposing the killer app for a personal
knowledge graph + read-only MCP server.

READ (do not modify):
  docs/superpowers/specs/2026-06-10-mcp-killer-app-challenge.md
For grounding, you may also read (read-only):
  kdb_graph/schema.py, kdb_graph/queries.py, kdb_graph/analytics.py,
  compiler/context_loader.py

TASK: Follow the challenge brief. Propose ONE killer app/query — your single best,
defended — that justifies the MCP server. Meet the 5-point quality bar; the
load-bearing test is graph-native + metacognitive/generative OVER retrieval.
"What connects to X?" is the FLOOR — beat it decisively. Use the brief's required
6-part output format.

OUTPUT RULES (strict):
- Do NOT modify any repo file, run any build, or touch git. Ideation only.
- Write your ENTIRE response to exactly one file:
    docs/superpowers/specs/reviews/2026-06-10-mcp-killer-app/<MODEL>.md
- Nothing outside that file. Keep it tight — the 6 parts, no preamble.
```

For chat models (no filesystem): paste the full brief contents inline; save the
returned prose manually to the `<MODEL>.md` path above.
