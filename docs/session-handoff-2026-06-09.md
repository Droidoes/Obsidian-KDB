# Session handoff — 2026-06-09

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ⏩ END OF SESSION — pass1/ + benchmark-record code shipped; thin-node storage architecture reconfirmed + documented; one open gate for tomorrow

Daytime session. Two code commits **merged + pushed**; one architecture discussion
captured in a new durable reference doc. Tomorrow opens on a single, well-scoped
design task: name the concrete consumer question for the GraphDB.

### What happened

1. **Code shipped (2 commits, pushed to origin/main):**
   - `dcc844b` — **Pass-1 sidecars → `pass1/` subdir** (mirrors `pass2/`). All write/read
     sites updated: `replay_archive.write_sidecar()`, `measurement.load_run_measurements()`,
     `emit_kpis._gather_pass1_search_keys()`, `dump_run_passes.load_pass1()`. Plus the
     earlier carried-over uncommitted set (viewer colors, graph-nodes-edges-logic.md,
     sandbox-run.sh, prior handoffs, docs/tutorial → docs/reference). 1252 tests pass.
   - `b498fff` — **`--emit-kpis` now copies a self-contained benchmark record** into
     `benchmark/runs/<model>-<run_id>/`: `run_state/` (pass1/ + pass2/ + measurement_header.json),
     `compile_result.json`, and `wiki/`. Threaded `vault_root` through
     `maybe_emit_kpis`/`emit_run_kpis`. Copy failures log a warning, never abort the run.

2. **GraphDB architecture discussion (the meat of the session):**
   - **[1] Thin nodes — confirmed.** Graph stores topology + metadata, not bodies. Bodies
     live in one canonical home. Refinement: the canonical home is the **wiki/ filesystem**
     (per-page, slug-addressable), with `compile_result.json` as the *combined run artifact*.
   - **[2] Kuzu vs Neo4j vs Neptune — reconfirmed Kuzu.** Decision is load-bearing on one
     fact: KDB is **embedded + single-user**. Neptune = wrong (cloud). Neo4j = overweight
     (server/JVM). Kuzu = right (embedded, no daemon, Cypher-compatible). Flip condition:
     only if KDB becomes a hosted multi-user service.
   - **[3] Is `compile_result.json` the right store at scale? — reframed.** It's an
     **audit/replay artifact**, not a serving store. The **wiki/ tree is already the sharded,
     slug-addressable content store** (point lookups never touch the monolith). Don't migrate
     to a DB pre-emptively; add **SQLite FTS5 as a derived index** only when a lexical query
     demands it.
   - **[4] How we use it — the graph earns its keep only on _relational_ queries.** Killer
     app = **GraphRAG-style retrieval** (find entry entities → traverse → assemble connected
     neighborhood → feed LLM). Interface = an **MCP server** exposing `graph_neighborhood`,
     `find_path`, `fts_search`, `get_body`; Claude becomes the query engine.

3. **New durable doc:** `docs/reference/kdb-storage-architecture.md` — the **three coordinated
   stores** mental model (GraphDB / Content store / FTS index), engine rationale, the MCP-as-
   interface model, and **The Gate** (consumer-purpose test for the whole GraphDB).

---

## OPEN — pick up here

- [ ] **THE GATE (tomorrow's primary task): name ONE concrete real-world question** you wish
      you could ask your vault today — e.g. *"What have I captured about X, and what does it
      connect to?"* Use it as the North Star to validate the full stack end-to-end:
      `query → graph traversal → assembled context → answer`. This single decision shapes
      (b) the MCP/query layer and (c) real use cases more than any further infrastructure.
      → Once named, write the **JOURNEY.md** entry that's currently deferred.

- [ ] **Then (b):** design the MCP server tool set (`graph_neighborhood(slug)`,
      `find_path(a,b)`, `fts_search(text)`, `get_body(slug)`) against that one question.

- [ ] **FTS index** — add SQLite FTS5 (derived from content store) *if/when* the concrete
      question needs lexical entry. Not before.

- [ ] **Carried over (unchanged):** investigate `GraphDB-KDB` 26MB flat-file-vs-directory
      issue; 0.6→1.0 ingestion arc (`ingestion/feeder/` empty, #88/#91 family); #107 Phase-B polish.

- [ ] **Strategic fork still parked:** 2.0 Claim layer before or after 0.6→1.0 ingest. Lean:
      1.0 first. (Not re-litigated this session.)

---

## Housekeeping / commit gate

**Uncommitted (awaiting Joseph's go) — this session's doc work:**
- `?? docs/reference/kdb-storage-architecture.md` — new (three-store mental model)
- `?? docs/session-handoff-2026-06-09.md` — this file
- `M  docs/reference/graph-nodes-edges-logic.md` — added "Node Properties — Stored vs. Externalized" section + Design Rule bullet
- `M  docs/reference/graphdb-tutorial.html` — added "What a node stores (and what it doesn't)" subsection

`main` is at `b498fff`, pushed (origin/main even). The two code commits are already up;
only the doc edits above are pending the gate.

---

## Pointers

- **Resume artifact:** `docs/reference/kdb-storage-architecture.md` → open this first; "The Gate" section is tomorrow's task.
- **Companion:** `docs/reference/graph-nodes-edges-logic.md` (node/edge mechanics + node-property storage).
- **Tutorial:** `docs/reference/graphdb-tutorial.html` (teaching surface, defers to the two above).
- **Task ledger:** `docs/TASKS.md` · **North Star:** `docs/CODEBASE_OVERVIEW.md` · **Journey:** `docs/JOURNEY.md`
