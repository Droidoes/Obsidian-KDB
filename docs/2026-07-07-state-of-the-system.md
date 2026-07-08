# KDB — State of the System (2026-07-07)

> A state-of-the-system review taken at the pivot point *before* the vault-in-place
> ingestion push. Purpose: establish an honest, current picture of what is built,
> what runs, what is parked, and what is realistic — as the launchpad for building
> a comprehensive graph. Companion to the North Star (`docs/CODEBASE_OVERVIEW.md`)
> and the ledger (`docs/TASKS.md`); this doc is the *assessment*, those are the
> *architecture* and the *index*.

## TL;DR

The **compile pipeline is mature and reliable** at sandbox scale (36 sources →
~250 entities, many clean end-to-end runs). The **graph, canonicalization,
domain-scoping, repair ladders, benchmark, viewer, and a read-only MCP server all
exist and work.** What we do **not** have is **scale**: everything has been proven
on a 36-note test vault, and the real Obsidian vault is **1,586 notes (~44×)**.

This session established the load-bearing realization: the graph's exciting
**"LLM-operations" tier is data-gated and degenerate at personal scale** (the
ratified *scale hedge* firing — see `project_ontology_purpose_kernel_question`),
so the **realistic present value of the graph is canonicalization + retrieval**,
and the **binding constraint is now corpus scale, not code.** The next move is to
**ingest the full vault and build a comprehensive graph**, then re-test the
operations thesis against real density.

---

## 1. Version reality (clear up "0.6")

There is **no `0.6`.** The tagged line runs `v0.4.0 → v0.5.6` (2026-06-07). "0.6"
was always the *name of the ingestion arc* — the thing we are about to start, not
something completed.

| Tag | Date | What |
|-----|------|------|
| `v0.5.0` | 2026-05-31 | Reliable orchestration (clean run-5) |
| `v0.5.1` / `v0.5.2` | 2026-06-02 | Codebase realignment (fix-in-place / six-package split) |
| `v0.5.3` | 2026-06-02 | Pass-2 repair ladder (#106) |
| `v0.5.4`–`v0.5.6` | 2026-06-07 | Benchmark framework + baselines (#109/#110/#111) |
| *(untagged)* | 2026-06-10/11 | **#112 + #113 graph-access package + MCP server — on `main`, never tagged** |

**Version debt:** the MCP work (`#112`/`#113`) sits on `main` at `a9ffb12`
unversioned. When the ingestion arc opens, the first move should either tag the
MCP work (e.g. `v0.5.7`) or fold it into the ingestion release — so the version
story stops lying.

---

## 2. Architecture as-built

Seven Python packages (six peers + the MCP sibling), one CLI surface, three data
stores. This is real and current.

**Packages** (`pyproject` members):
`common` (leaf: paths, telemetry, models pool, `wiki_io`) · `ingestion`
(Pass-1 enrich, scan, feeder-stub) · `compiler` (Pass-2 compile, context loader,
repair, KPIs) · `kdb_graph` (Kuzu graph-access contract — schema, queries,
intake, ops, analytics, CLI; **zero `common` dependency**) · `orchestrator`
(`kdb-orchestrate` conductor, manifest writer, events, KPI emit) · `tools`
(cleanup, replay, benchmark, viewer) · `kdb_mcp` (read-only MCP stdio server).

**The pipeline** (`kdb-orchestrate` conducts it):
```
kdb-scan → kdb-enrich (Pass-1) → kdb-compile (Pass-2) → canonicalize → graph-sync → finalize → kdb-clean orphans
```
- **Pass-1 (enrich):** per-source LLM classification → signal/noise verdict,
  domain (23-vocab), source_type (21-vocab), `entity_search_keys`, summary,
  author → written as frontmatter. Deterministic layer owns provenance.
- **Pass-2 (compile):** LLM extracts entities + wikilinks + pages, primed with a
  **domain-scoped T1/T2/T3 context snapshot** (existing entities from the source's
  own domain, for reuse/anti-entropy).
- **Canonicalization:** alias collapse (`canonical_id` + `ALIAS_OF`) so wiki ≡
  graph on entity names.
- **Graph-sync + finalize:** entities/edges written to Kuzu via the adapter;
  finalize wires cross-source `LINKS_TO` over the committed set.
- **Robustness:** quarantine-and-continue (`#96`) + a deterministic Pass-2 repair
  ladder (`#106`: JSON-escape → slug-coerce, re-validation-gated).

**Stores:** the **Kuzu graph** (schema v2.4 — Entity/Source/Domain nodes;
LINKS_TO/SUPPORTS/BELONGS_TO/ALIAS_OF edges; the **Claim layer + 5 edges are
present-but-unwired**, parked for 2.0) · the **wiki/ content store** (page bodies,
thin-node: bodies live here, not in the graph) · **manifest.json** (source-file
metadata ledger only, D50) + `state/` journals.

**Model selection is settled:** `deepseek-v4-flash` is the default **on cost**
(~$0.05/run at sandbox scale; 7.2× cheaper than the quality leader `gpt-5.4-mini`,
also 0-quarantine). Quality is the only open benchmark axis.

---

## 3. What's live and validated

Proven by repeated clean end-to-end runs on the 36-source sandbox
(`~/Obsidian/Vault-in-place-test-run`):

- **Full compile pipeline + orchestrator** — run-3 through run-9 clean
  (`exit_reason=ok`, 0 quarantined). `#94`'s stranded-`LINKS_TO` class dissolved
  by `#96`.
- **Graph** — ~250 entities, Kuzu v2.4, canonicalized, 100% BELONGS_TO coverage.
- **Benchmark** (`#109`/`#110`/`#111`) — GT-free two-family KPIs (processing +
  graph) via `kdb-orchestrate --emit-kpis` → `kdb-benchmark score`; baseline-1
  4-model cohort locked.
- **Viewer** (`#97`) — single-command D3 force-directed HTML from the live graph.
- **MCP server** (`#113`) — 7 read-only tools, per-call reopen, stable Pydantic
  shapes; validated end-to-end through the protocol. *(But see §4 — it serves a
  degenerate graph today.)*
- **Test suite** — ~1290 non-live tests green.

---

## 4. Built-but-parked (real investment, deliberately dormant)

| What | Status | Why parked |
|------|--------|-----------|
| **Read-only MCP server** (`#113` Ph 1/2/3a) | Shipped, works | The intended **front door for querying the graph** — but there is no comprehensive graph yet. **Re-prioritize after ingestion.** Not abandoned. |
| **O1 promotion pipeline + Claim layer** (`#83`/`#84`) | Built, 15/15 probes GREEN (late May) | The whole Claim/Learn tier was **deferred to Release 2.0** by the ontology blueprint (2026-05-31). Schema tables present, **unwired in production**. Data-gated like the stress test. |
| **Ingestion *platform*** (`#88` feeders: RSS/PDF/YouTube/web) | **Designed (v0.4 ratified), largely unbuilt** | `ingestion/feeder/` is an empty stub. Only the **manual-`.md`-drop path** exists — which is exactly what the vault ingestion uses. The multi-source platform is future work. |
| **Learn slots 2.0** (`#85`/`#86`/`#87`) | Designed/ratified, unbuilt | Belief-revision / identity-refinement / abstraction — the 2.0 metacognition tier. Same data-gating. |

---

## 5. Abandoned this session

- **`stress_test` / the "Epistemic Load-Bearing Stress Test" (`#113` Phase 3b, the
  Named Gate).** A precondition check on the live 248-entity graph showed the
  metacognitive analytics are **degenerate at personal scale**: grounding has **no
  variance** (214/218 canonical entities have exactly 1 source) and only **2 of
  486 LINKS_TO edges cross a community boundary** (4 bridge entities total). With
  no ground truth, the tool would be correct-but-unvalidatable code against an
  untunable formula. This is the ratified *scale hedge* firing — and it generalizes
  beyond the stress test (GraphRAG/HippoRAG operations would be equally degenerate
  on this topology). **The IDEA is abandoned; the MCP server is not.**

---

## 6. The strategic reframe (this session's core output)

1. **"What is the ontology for?"** — ratified answer (Round 5): an executable
   substrate for LLM operations; value = the *operations*, with an explicit
   **scale hedge** ("unverified at personal scale").
2. **The hedge fired.** We ran the operations; they are degenerate at ~250 nodes.
3. **Two layers of value, separated honestly:**
   - **Real / delivered / scale-tolerant** — **canonicalization + reuse** (the
     compiler's Pass-2 substrate, earns its keep at any scale) and **retrieval +
     navigation** (MCP tools, viewer).
   - **Aspirational / scale-gated** — the operations/metacognition tier
     (stress test, GraphRAG/HippoRAG, Learn/Claim). Lever = **corpus scale**, not
     code. May never fully arrive at single-user scale.
4. **Binding constraint moved** — from code quality (sharply diminishing returns
   now) to **corpus scale.** Hence: **build a comprehensive graph.**

---

## 7. Readiness for the vault-in-place ingestion push

The goal: ingest the real vault → comprehensive graph. Honest gap analysis.

**The scale jump:** 36 sources → **1,586 notes (~44×)** across ~20 domains
(AIML, Value Investing, Equity Research, History, Science & Tech, Literature… plus
personal: Daily Notes, Life-Health, Retirement, Food).

**What's ready:** the built path (`kdb-scan → kdb-enrich → kdb-compile →
kdb-clean` via `kdb-orchestrate`) works clean and is the exact tool for the job.

**What is NOT yet proven / decided (the real work before firing a run):**

1. **Scale robustness.** The pipeline has never run past ~tens of sources. 1,586
   two-pass LLM compiles is likely **hours**; rate limits, resume-after-failure,
   and quarantine *volume* all bite here. `#94` was *dissolved* by finalize-over-
   committed-set, but the resume path is untested at this scale. **Design the
   long-run failure mode out first.**
2. **Selection (the B+X6 question).** Ratified posture is **broad ingestion,
   mechanical-role exclusion only.** Pointed at 1,586 notes including daily notes,
   grocery-tier captures, and image stubs, we must verify **X6 actually filters the
   chaff before we spend tokens.** (Daily Notes have a `force_noise` path via
   `#89`/D-89-14 — needs a real-vault spot-check.)
3. **Target data-dir + version story.** The official `~/Obsidian/KDB` dir is in a
   **stale partial state** (`raw=8, wiki=83, no graph`) from an earlier run — reset
   or reconcile before a clean comprehensive build. Confirm the graph's OneDrive-
   synced location is intended for a 1,586-note Kuzu DB.
4. **Cost is not the blocker** (~$2–3 at 44× of ~$0.05), **but one-shot fragility
   is.** A multi-hour run that dies at note 900 with no clean resume is the failure
   to prevent.
5. **Cross-store audit** (`#93 kdb-audit`) is **proposed, not built** — the
   pre-run/post-run consistency gate for a big ingest doesn't exist yet.

**Recommendation:** treat this as the ingestion arc and **scope it in a short
brainstorm** (selection/X6 verification against real notes · at-scale robustness
& resume · data-dir reset), *then* fire the run. Too long and too one-shot to wing.

---

## 8. Open-ledger triage (surfaced for the full review, not yet actioned)

The ledger splits cleanly along the pivot:

- **Parked 2.0 metacognition** — `#83`, `#84`, `#85`, `#86`, `#87` (Claim layer /
  Learn slots / their eval criteria). Same data-gating as the abandoned stress
  test. **Recommend: mark explicitly "parked — data-gated (2.0)"** so they stop
  reading as near-term open work.
- **The revived ingestion arc** — `#88` (Ingestion System), `#91` (kdb-orchestrate,
  `v0.2 ratified` — core built, platform/feeders not), `#93` (kdb-audit, proposed),
  `#94` (resume-correctness, dissolved-but-untested-at-scale). **Now front-and-
  center.**
- **Polish / housekeeping** — `#107` (Phase-B follow-ups: viewer packaging,
  `compiler.compiler` double-name, orchestrator→tools decoupling). Plus dead code:
  **`knowledge_graph/`** (legacy single-file, excluded from packaging — deletable)
  and the stray untracked handoffs / `Karpathy-llm-wiki.md`.
- **Perpetual / meta** — `#2` (scalability thinking-work, low priority), `#16`
  (this ledger).

## 9. Recommended next moves

1. **Sync the docs to the pivot** (small): status-banner the graph-access design
   spec (Phase 3b abandoned); update memory (`project_113_graph_access_mcp` says
   "Phase 3b next"); the `#113` ledger edit is done.
2. **Triage the 2.0 tasks** (`#83`–`#87`) to "parked — data-gated" per §8.
3. **Open the ingestion arc** — brainstorm the at-scale run (§7), verify selection
   on real notes, settle the data-dir, then Joseph fires the comprehensive run.
4. **After the comprehensive graph exists** — re-test the operations thesis with
   predeclared criteria, and re-prioritize the MCP server as the query front door.
