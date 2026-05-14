# Session Handoff — 2026-05-14 → 2026-05-15

**Topic:** GraphDB-KDB sub-task **#63.6 (Rebuilder)** — needs care + further discussion before coding.

---

## Where today landed

| Sub-task | Commit  | Tests | Notes |
|----------|---------|-------|-------|
| #63.3 queries  | `d1a3641` | 29 | neighbors / shortest_path / provenance / orphans / cypher |
| #63.4 analytics| `09e4130` | 13 | hybrid PageRank + Louvain + structural_holes (NetworkX/python-louvain); added `scipy>=1.10` dep |
| #63.5 verifier | `7edf2c4` | 11 | `verify_against_manifest` + CLI; overlap-only per L4 |
| Ledger updates | `7244458`, `315e061`, `e5d484b` | — | |

Full graphdb_kdb suite: **76/76 green**.

---

## What #63.6 actually has to do

From blueprint §8.2 + §11 + §13.1 Q3:

1. **Drop all Kuzu tables**, recreate schema (idempotent re-init).
2. **Iterate `state/runs/*.json`** chronologically.
3. **Apply D39 eligibility filter**: `success=true AND dry_run=false AND payload_present`.
4. **For each eligible run**, load that run's `compile_result.json` + `last_scan.json` payload and call `apply_compile_result(cr, scan, run_id)`.
5. **Independence proof** — must not read `manifest.json` at any point.
6. CLI: `graphdb-kdb rebuild --vault-root <path>`. Print summary (runs replayed / skipped / failed).

## The two reasons this needs care

### (1) Payload-archive shape decision — going-forward path

Per #63.0 outcome **(c.ii)**: run journals do NOT embed the compile_result inline. Going forward, **#63.7 (Stage 9 wiring)** will write per-run sidecar archives at:

```
state/runs/<run_id>/
├── compile_result.json
└── last_scan.json
```

But: **#63.6 lands BEFORE #63.7.** Which means at the moment #63.6 ships, no sidecars exist yet. The rebuilder needs a way to be testable now and useful later.

**Open question to discuss:** does #63.6 just define the `payload_present` predicate against the sidecar shape (and report "0 eligible runs" cleanly), or does it also include a one-shot bootstrap step? Two reasonable shapes:

- **Shape A (minimal):** #63.6 only handles the steady-state case. Sidecar absent → run is `payload_present=false` → skip. Tests use synthetic sidecars in tmp dirs. Real-world use unblocked once #63.7 starts writing them.
- **Shape B (with backfill):** #63.6 also implements outcome **(d)** — the one-off backfill of the latest pre-#63 run from the current `state/compile_result.json` + `state/last_scan.json` baton. This is the migration entry point.

Shape B is what §13.1 Q3 outcome (d) implies; Shape A is simpler but pushes the migration to either #63.7 or a manual step.

### (2) Run-journal field discovery — what does `state/runs/*.json` actually look like?

The verifier work hit the manifest schema; the rebuilder hits the **run journal** schema. Per #63.0 audit, top-level fields are: `success`, `dry_run`, `journal_written`, `manifest_written`, `compile_success`, plus `artifacts.compile_result_path` / `artifacts.last_scan_path` (which point at OVERWRITTEN baton files — not per-run archives).

Need to confirm before coding:
- What's the `run_id` field name in the journal? (`run_id`? top-level? nested?)
- Filename pattern in `state/runs/`? (Looks like `2026-04-20T02-00-45Z.json` based on `last_run_id` formats.)
- Chronological ordering — by filename or by a `started_at` field?
- Any pre-#63 historical runs that should be deliberately skipped vs the one designated as backfill source?

These are quick to answer with one `cat` of a journal in `~/Obsidian/KDB/state/runs/` — do this at the top of tomorrow's session.

---

## Suggested opening moves for next session

1. `ls -la ~/Obsidian/KDB/state/runs/` — see what's actually there.
2. Read one journal end-to-end. Confirm the eligibility-field names and the chronological key.
3. Decide Shape A vs Shape B for #63.6.
4. Decide on the test fixture strategy (synthetic `state/runs/` tree in `tmp_path`).
5. Then plan + implement.

---

## Memory pointers (already saved)

- `project_graphdb_kdb_refoundation.md` — paradigm + scope
- `project_graphdb_kdb_vs_kdb_graph_distinction.md` — naming guardrail
- `feedback_graph_over_vector_for_kdb.md` — anti-vector lean
- Task ledger `docs/TASKS.md` is authoritative for #63.* status

No new memory needed for this handoff — the open questions are scoped to one sub-task and don't generalize.
