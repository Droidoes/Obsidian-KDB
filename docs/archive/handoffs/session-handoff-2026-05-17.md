# Session Handoff — 2026-05-17 (morning)

## What shipped

| Commit | What |
|--------|------|
| `315f0fa` | feat(D50-G): replay-to-temp structural equality verifier |
| `4f4ae37` | docs: Task #73 done — D50 manifest ontology removal complete (Phases B→H) |
| `3588a98` | docs(D51): GraphDB is live ontology authority; runs are reconstruction material |
| `b7a9ffb` | docs: close Task #5 (LLM benchmarking) + #33 (orchestrator) |
| `6c9f7e5` | docs: close Task #65 — already implemented |

## Key decisions

- **D51:** GraphDB is the live ontology authority. `state/runs/` = audit + reconstruction backup. Primary path: `kdb-compile → Stage 9 → GraphDB`. No event-sourcing framing, no `ontology_sources/` layer.
- **Rebuild resolved 7 replay divergences** in the live graph (historical drift from prior code version + Kuzu `NOT EXISTS` edge case).

## Current graph state

```
entities: 68 | sources: 6 | links: 104 | supports: 63
verify: 0 replay divergences, 10 known-benign D39 preflight tax
```

## Open tasks (priority order)

1. **Grow ontology** — add new raw sources, compile them (most impactful)
2. **#25** — capture exception type in resp-stats (small patch, 30 min)
3. **#20** — ground-truth source decision (thinking-work)
4. **Open-1..8** — CODEBASE_OVERVIEW housekeeping
5. **#16** — close the meta task (TASKS.md IS the deliverable)
6. **#2** — scalability discussion (deferred, no urgency)

## Architectural state

The system is settled:
- D50/D51: manifest is source metadata only; GraphDB owns ontology
- D49: GraphDB is sole context authority (no manifest fallback)
- D48: graph context loader handles cold-start natively (title widening + 2-hop)
- D45: pairing_type_mismatch reconcilable (slug lists derived from pages[])
- Verify proves consistency; rebuild is the recovery path
- Benchmark track closed (5 candidates, Borda scorecard, outlier penalty)

No architectural work pending. Next value comes from growing the corpus.
