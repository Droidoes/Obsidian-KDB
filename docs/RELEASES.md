# KDB Release Notes

Backward-looking, **version-keyed** release log. Major releases (`X.0.0`) carry a
running narrative; every point release gets at least one documented entry. Forward
plan: `docs/ROADMAP.md`. Fine-grained date-keyed dev log: `docs/CODEBASE_OVERVIEW.md`
Milestone Changelog.

Versioning + tag policy: see `docs/ROADMAP.md` § Versioning policy. Tags are cut
(and point-release wrapping is evaluated) at each session handoff.

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
