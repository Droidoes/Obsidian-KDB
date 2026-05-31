# KDB Roadmap

**Status:** Active. Forward-looking release plan. Companion to the backward-looking
release notes (`docs/RELEASES.md`) and the fine-grained dev log
(`docs/CODEBASE_OVERVIEW.md` Milestone Changelog).
**Adopted:** 2026-05-31.

---

## Versioning policy

- **Scheme:** semantic versioning `MAJOR.MINOR.PATCH` (e.g. `0.4.0`).
  - **MAJOR** — a qualitative capability change (e.g. traverse → reason).
  - **MINOR** — a new reliable subsystem / gate reached.
  - **PATCH** — completed increment within a minor line.
- **Git tags:** every release is tagged (`v0.4.0`, `v0.5.0`, `v1.0.0`, …).
- **Release notes** (`docs/RELEASES.md`): **major** releases (`X.0.0`) get a running
  narrative note; **every point release** is at least documented (one entry).
- **Cadence:** at each **session handoff**, evaluate whether the work completed
  warrants wrapping as a point release (tag + RELEASES.md entry).

The release boundary is principled, not cosmetic: the `0.4 → 1.0` arc builds the
reliable **Remember + Relate** infrastructure; `2.0` is the **Learn + reasoning**
leap (the ¶419 line). See `docs/what-is-ontology-for-V1.md` §V1.1 for the
five-rung objective ladder these map onto.

---

## Release map

| Release | Gate / theme | Scope |
|---|---|---|
| **0.4.0** *(current)* | E2E runs; orchestration not yet reliable | run-3 clean E2E once, but the meaning layer is broken (domain coverage bug), Pass-2 carries a leftover per-page domain, no domain-aware retrieval, minimal stdout. Ontology Blueprint V1 ratified (D1-A · D2→2.0 · D3-C). |
| **0.5.0** | **Orchestration pipeline working reliably** | D1 domain fix (derive `BELONGS_TO` from `Source.domain`+`SUPPORTS`, `support_count`, drop page-domain, retire `sub_domain`) · Pass-2 producer rebuild (prompt + schema cleanup implementing D1) · D3 domain-aware retrieval (refined variant D) · stdout / progress messaging · **run-4 clean & repeatable**. |
| **0.6 → 0.9** | **Ingestion pipelines** | Vault-in-place ingestion of the **entire** Obsidian vault (real corpus, at scale) · **1–2 KDB/raw feeder pipelines** (Task #88 family — the multi-source ingestion platform / tunnel-from-both-ends arc). |
| **1.0.0** | **All infrastructure working & ready to go** | Orchestration (0.5) + the full multi-source ingestion stack, reliable end-to-end → a trustworthy **Remember + Relate** knowledge graph over the real corpus. |
| **1.x** | Enhancements on the stable core | Viewer / `kdb-graph-view` CLI (task97) · benchmark redesign · Discover-*lite* (structural holes — already partially ships) · more domains / domain refinements. |
| **2.0.0** | **Learn + reasoning (¶419)** | Claim layer (D2): `Claim` + `EVIDENCES` + `ABOUT` + a controlled `PredicateClass` registry + an offline extraction pilot · belief revision (#83/#84/#85/#86 — `SUPERSEDES`/`CONTRADICTS`/`QUALIFIES`, Hypothesis Promotion) · real Discover (link prediction, contradiction detection) · Create-as-collaboration. |

### Ladder mapping

- **0.4 → 1.0** — the reliable **Remember + Relate** infrastructure (correct domains, full ingestion, reliable orchestration).
- **1.x** — Remember/Relate enhancements + **Discover-lite**.
- **2.0** — **Learn** (belief revision), real **Discover**, and **Create** (collaboration).

---

## Current focus

**Target: 0.5.0 (reliable orchestration).** The active arc is the ontology
meaning-layer fix and producer rebuild, sequenced:

> ontology (ratified — `docs/ontology-blueprint-V1.md`) → **producer (Pass-2) rebuild** → consumer (T2/T3) → stdout messaging → **run-4** (the 0.5.0 gate).

The Claim/Learn layer is explicitly **out of scope until 2.0** — kept in the
schema as designed-but-unwired.
