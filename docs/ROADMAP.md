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
leap (the ¶419 line). See `docs/reference/what-is-ontology-for-V1.md` §V1.1 for the
five-rung objective ladder these map onto.

---

## Release map

| Release | Gate / theme | Scope |
|---|---|---|
| **0.4.0** | E2E runs; orchestration not yet reliable | run-3 clean E2E once, but the meaning layer is broken (domain coverage bug), Pass-2 carries a leftover per-page domain, no domain-aware retrieval, minimal stdout. Ontology Blueprint V1 ratified (D1-A · D2→2.0 · D3-C). |
| **0.5.0** ✅ *(shipped — tagged `v0.5.0`, 2026-05-31)* | **Orchestration pipeline working reliably** | D1-A domain derivation · #96 quarantine-and-continue · #102 live stdout progress · #103 domain-scoped Pass-2 context · Pass-1 coercion + Pass-2 retry (run-4 findings) · #97 GraphDB viewer. **Gate: run-5 clean E2E** (29 compiled / 0 quarantined / 0 invariant). |
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

**0.5.0 shipped 2026-05-31** (tagged `v0.5.0`) — reliable orchestration, gated on a clean
run-5. The full arc landed: ontology (ratified) → D1-A producer rebuild → consumer (T2/T3
domain-scoping) → #102 stdout progress → run-4 (surfaced findings) → Pass-1 coercion +
Pass-2 retry → **run-5 clean** (the gate).

**0.5.1 shipped 2026-06-02** (tagged `v0.5.1`) — **codebase realignment, Phase A** (Task #105):
an internal, zero-behavior-change refactor so the implementation reflects the decided architecture
(retire the legacy `kdb_compile` driver, honest renames, single Kuzu door, layering fix, North Star
rewrite); gated on a clean **run-6** ≡ run-5. The terminology+structure debt is paid down *before*
building 0.6 on top of it.

**Since then:** realignment Phase B shipped (`v0.5.2`), and the line ran through **`v0.5.6`**
(2026-06-07) — Pass-2 robustness ladder (#106, `v0.5.3`), user-owned model pool (#110),
benchmark calibration (#109/#111). The #112/#113 graph-access arc (`kdb_graph` package +
7-tool read-only `kdb_mcp` MCP server) is on `main` **untagged**, past `v0.5.6`.

**2026-07-07 pivot:** the LLM-operations tier proved data-gated at personal scale — #113
Phase 3b (`stress_test`) abandoned, #83–#87 (Claim/Learn 2.0 tier) parked. The binding
constraint has moved from code quality to corpus scale. See
`docs/2026-07-07-state-of-the-system.md` and the 2026-07-17 project review
(`docs/2026-07-17-project-review-kimi-k3.md`).

**Immediate next (as of 2026-07-17): the ingestion arc — 0.6 → 1.0.** Vault-in-place
ingestion of the entire Obsidian vault at scale + 1–2 KDB/raw feeder pipelines (Task #88
family / tunnel-from-both-ends).

The Claim/Learn layer is explicitly **out of scope until 2.0** — kept in the
schema as designed-but-unwired.
