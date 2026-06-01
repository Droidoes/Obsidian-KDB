# KDB Release Notes

Backward-looking, **version-keyed** release log. Major releases (`X.0.0`) carry a
running narrative; every point release gets at least one documented entry. Forward
plan: `docs/ROADMAP.md`. Fine-grained date-keyed dev log: `docs/CODEBASE_OVERVIEW.md`
Milestone Changelog.

Versioning + tag policy: see `docs/ROADMAP.md` § Versioning policy. Tags are cut
(and point-release wrapping is evaluated) at each session handoff.

---

## 0.5.0 — Reliable orchestration (tagged `v0.5.0`, 2026-05-31)

**Theme:** the end-to-end `kdb-orchestrate` pipeline runs reliably, observably, and
gracefully — the 0.5.0 gate.

**Gate — run-5 clean E2E** (`2026-05-31T21-05-23`): `exit_code=0`, `exit_reason="ok"` —
36 scanned / 36 enriched / **29 compiled / 7 noise / 0 failed / 0 quarantined / 0
invariant / 0 warnings**; finalize wired 449 links, 0 orphans. Graph (schema **v2.4**):
181 Entity · 29 Source · **10 Domain** · 444 LINKS_TO · 183 SUPPORTS · 181 BELONGS_TO.

**What landed since 0.4.1:**
- **#96 — quarantine-and-continue** error-handling: severity taxonomy + structured
  `orchestrator_events.jsonl`, production invariant checks, source-local quarantine
  (run continues; `run_fatal`/`invariant` still abort), finalize-always-over-committed-set.
- **#102 — live stdout progress**: default-on, blow-by-blow per-stage narrative
  (`[n/total] ▸ source`, `pass-1`/`pass-2` with elapsed, running counts, inline `⚠`),
  `--quiet` opt-out, console decoupled from JSONL verbosity (supersedes #101's stderr tee).
- **#103 — domain-scoped Pass-2 context** (D3 → hard same-domain gate): the context
  snapshot is pulled only from the source's Pass-1 domain (anti-entropy).
- **D1-A derived domains** (from 0.4.1): `BELONGS_TO` derived from `Source.domain`+`SUPPORTS`;
  10 domains live in run-5 (vs 4 pre-backfill).
- **Pass-1 coercion + Pass-2 retry** (run-4 findings, `docs/run-4-findings.md`): Pass-1
  coerces >10 `entity_search_keys` to 10 and lets `source_type='other'` pass without
  `other_reason` (don't reject benign deviations); Pass-2 retries on a recoverable bad-JSON
  emission (parse/schema), mirroring Pass-1 — which recovered run-4's lone quarantine
  (a LaTeX `\(…\)` JSON-escape slip) in run-5.
- **#97 — GraphDB viewer**: multi-model bake-off → official single-command D3 viewer
  (`tools/viewer/kdb_graph_viewer.py`).

**Run history:** run-4 surfaced the findings (1 quarantine from a stochastic LLM
JSON-escape defect, handled gracefully); the fixes landed; **run-5 came back clean** → gate
met. 1219 non-live tests green. Next: **0.6 → 1.0** (ingestion pipelines). See `docs/ROADMAP.md`.

---

## 0.4.1 — Domain derivation, D1-A producer slice (tagged `v0.4.1`, 2026-05-31)

**Theme:** first slice toward 0.5.0 — fixes the domain meaning layer.

`Entity BELONGS_TO Domain` is now a **derived projection** from `Source.domain` +
`SUPPORTS` (an entity belongs to the domains of the sources that support it),
replacing the broken per-page LLM `domain`. Edges carry `support_count` (distinct
supporting sources); `sub_domain` retired. Pass-2 no longer emits page
`domain`/`sub_domain`. Schema → **v2.4** (destructive REL change; rebuild-only).
Snapshot → **v6**.

**Validated on run-3 data (zero LLM cost):** domains 4 → **11**; `value-investing`
0 → **66 entities** (now the top domain); canonical-entity domain coverage
16% → **100%**.

Implements ratified decision **D1-A** (`docs/ontology-blueprint-V1.md` v0.2). Plan:
`docs/superpowers/plans/2026-05-31-task-0.5.0-producer-domain-rebuild.md`. 1010
non-live tests green; final code review (opus) cleared it to ship.

**Still pending for 0.5.0:** D3 domain-scoped T2/T3 retrieval · stdout/progress
messaging · **run-4** (the orchestration-reliability gate).

---

## 0.4.0 — baseline (tagged `v0.4.0`, 2026-05-31)

**State:** the end-to-end pipeline runs (`feeder → ingestion/Pass-1 → compiler/Pass-2
→ GraphDB`). Run-3 (2026-05-30) was the first clean E2E run — 36 scanned / 29 compiled
/ 7 noise / 0 quarantined; graph: 178 Entity · 29 Source · 4 Domain · 0 Claim.

**Known limitation (the 0.5 target):** the domain meaning layer is broken —
`BELONGS_TO` is built from a leftover Pass-2 per-page LLM `domain` that under-emits
(24/147 concept pages, 4 values; `value-investing` never emitted). Orchestration is
not yet reliable.

**Planning landed this line:** Ontology Blueprint V1 ratified after a 5-model panel
review — D1→A (derive domain), D2→deferred to 2.0 (Claim/Learn layer), D3→C
(domain as retrieval coordinate). Release versioning + roadmap adopted.

→ Next: **0.5.0** (reliable orchestration). See `docs/ROADMAP.md`.
