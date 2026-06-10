# Panel Review Prompt — Graph-Access Package + MCP Server (2026-06-10)

Brief under review: `docs/superpowers/specs/2026-06-10-graph-access-package-design.md`
Save reviews to: `docs/superpowers/specs/reviews/2026-06-10-graph-access/<MODEL>-review.md`

---

## Prompt (copy-paste; swap `<MODEL>` per reviewer)

```
You are a senior architect doing an independent design review.

READ (do not modify):
  docs/superpowers/specs/2026-06-10-graph-access-package-design.md
For grounding, you may also read (read-only):
  kdb_graph/, compiler/context_loader.py, kdb_graph/queries.py, kdb_graph/graphdb.py

TASK — review the brief and give a verdict:
1. Is the producer/consumer/durable-asset framing sound, or is there a reason the
   GraphDB access contract should stay coupled to the compiler? (§1)
2. For each open fork F1–F5 (§4): AGREE or DISAGREE with the stated lean, with
   one-paragraph reasoning. If DISAGREE, give the alternative and its tradeoff.
3. What does the brief MISS — any consumer, failure mode, or risk not listed
   (e.g. schema versioning across the package boundary, multi-process Kuzu lock
   semantics, test-fixture coupling)?
4. Is "extract now, triggered by the second consumer" the right timing, or
   premature?

OUTPUT RULES (strict):
- Do NOT modify any repo file, run any build, or touch git. Review only.
- Write your ENTIRE response to exactly one file:
    docs/superpowers/specs/reviews/2026-06-10-graph-access/<MODEL>-review.md
- Nothing outside that file. Keep it tight — verdict + reasoning, no preamble.
```

---

## For chat models (no filesystem access)

Drop the READ/OUTPUT-path lines above and paste the full contents of the brief
inline. They return prose; save it manually to
`docs/superpowers/specs/reviews/2026-06-10-graph-access/<MODEL>-review.md`.
