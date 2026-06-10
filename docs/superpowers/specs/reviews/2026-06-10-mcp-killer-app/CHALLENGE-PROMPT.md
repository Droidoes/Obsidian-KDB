# Challenge Prompt — Killer App for the KDB Graph + MCP Server (2026-06-10)

Challenge brief: `docs/superpowers/specs/2026-06-10-mcp-killer-app-challenge.md`
Save responses to: `docs/superpowers/specs/reviews/2026-06-10-mcp-killer-app/<MODEL>.md`

---

## Prompt (swap `<MODEL>` per model)

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

---

## For chat models (no filesystem access)

Paste the full contents of the challenge brief inline; save the returned prose
manually to `docs/superpowers/specs/reviews/2026-06-10-mcp-killer-app/<MODEL>.md`.
