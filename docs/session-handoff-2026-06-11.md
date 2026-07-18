# Session handoff — 2026-06-11

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ⏩ END OF SESSION — #113 Phase 2 AND Phase 3a both shipped; read-only MCP server is live

Long build session. Shipped **two** #113 phases end-to-end (design → plan → subagent-driven TDD → review → merge → push): **Phase 2** (`get_body` content tool) and **Phase 3a** (the `kdb_mcp/` read-only MCP stdio server, 7 tools). Both merged to `main` and pushed (`origin` even at `a9ffb12`). The MCP server is real and was driven end-to-end through the protocol against the live 2.4 sandbox graph. Also took a hard rigor critique from Joseph mid-session (the `get_body` hour) — captured as durable feedback.

### What happened / what converged
- **🏁 Phase 2 — `get_body`** (merge `0f1fbd3`): `common/wiki_io.py::get_body(slug, page_type, *, root)` + `ContentNotFoundError`; thin reader composing `paths.slug_to_abspath` + `source_io.parse_existing_frontmatter`, body-only/frontmatter-stripped. **Placement A: lives in `common/`, NOT `kdb_graph`** — it's a *tool* with two consumers (MCP + viewer), so it sits in the shared layer; putting it in the package would break `kdb_graph`'s zero-`common` invariant (F3, stores stay separate). 9 unit tests + live smoke. The placement took ~an hour to land — see the critique below.
- **🏁 Phase 3a — `kdb_mcp/`** (merge `a9ffb12`): new **in-repo sibling package** (outside `kdb_graph`, same-repo per F2 — the panel consensus; no separate repo). `FastMCP` server, **7 read tools**, each a thin wrapper over a pure adapter that opens `GraphDB(…, read_only=True)` **per call** (F5 reopen) and returns a stable **Pydantic** shape; errors → `isError` envelope. 19 kdb_mcp tests, full suite **1290 green**.
- **SDK verified before coding** (Context7, the gate): caught `from mcp import Client` does NOT exist in the installed **`mcp` 1.27.2`** → in-memory test uses `create_connected_server_and_client_session(app._mcp_server)`. The implementer correctly escalated rather than guessing.
- **Two findings folded mid-build:** (1) **`resolve_search_keys` slugifies inputs** so human names ("Amortization" → `amortization`) resolve — the underlying resolver is exact-slug-only; my first test used a bare slug and masked it (advisor catch). (2) **`config.default_graph_path()` now derives from the vault root** (`<vault>/KDB/graph`) so graph + wiki come from ONE KDB instance via `OBSIDIAN_VAULT_PATH` alone — the old `~/Droidoes/GraphDB-KDB` default was a stale 2.3 stray (Joseph: "there is no `~/Droidoes/GraphDB-KDB`").
- **Data-dir architecture (Joseph corrected):** official = `~/Obsidian/KDB` (has `raw/`/`state/`/`wiki/` but **no graph yet**); sandbox = `~/Obsidian/Vault-in-place-test-run/KDB/graph` (2.4, populated — 248 entities). `~/Droidoes/GraphDB-KDB` (2.3 file) is dead/unreferenced.
- **Rigor critique (the meat of the morning):** the trivial `get_body` took an hour because I sprayed option-menus/jargon instead of reasoning to a conclusion — Joseph graded it a D vs peer models, warned about being shut down. Lesson: conclusion-first, reason from the system not local convenience, do the synthesis before speaking → [[feedback_think_before_speaking_no_option_spray]].

## OPEN — pick up here
- [ ] **Phase 3b — the `stress_test` analytics composite (the Named Gate):** compose `analytics.py` (pagerank × structural_holes × communities × SUPPORTS-degree) into the load-bearing-weak-points report; add 2 new `queries.py` primitives (`indegree`, `entity_list`) + a `StressReport` Pydantic model + register it as the 8th `kdb_mcp` tool. Same subagent-driven TDD. This is the server's *reason to exist* (retrieval floor graded D; the Gate graded A).
- [ ] **Build the official-vault graph** — `~/Obsidian/KDB/graph` doesn't exist; an orchestrate run against the official vault is needed before the MCP server serves official data with no env override.
- [ ] **Smaller carry-overs:** `graph_neighborhood` missing-center asymmetry (returns `[]` while `get_entity` raises — track for 3b); a `[project.scripts]` `kdb-mcp-server` entry point exists now; viewer-as-`get_body`-consumer not yet wired.

## Housekeeping / open loops
- [ ] **Commit gate:** `main` is clean + pushed (`a9ffb12`). **This handoff doc + today's daily note are the only new uncommitted items**, plus the stale untracked `docs/session-handoff-2026-06-10.md` (yesterday's, never committed). Joseph's call whether to commit the handoffs.
- [ ] **Deletable stray:** `~/Droidoes/GraphDB-KDB` (2.3 file) is unreferenced by code — safe to `rm` (Joseph's call; it's outside the repo).
- [ ] Parked: 2.0 Claim layer before/after 0.6→1.0 ingestion (lean: 1.0 first).

## Pointers
- **Resume artifact:** `docs/superpowers/specs/2026-06-10-graph-access-package-design.md` (v0.3 §3.5(c) analytics composite + §1.5 Named Gate) — the Phase 3b spec basis. Then write the Phase 3b plan.
- **How to test the MCP server now:** `OBSIDIAN_VAULT_PATH=~/Obsidian/Vault-in-place-test-run` then `.venv/bin/mcp dev kdb_mcp/server.py` (needs `pip install "mcp[cli]"`), or `claude mcp add kdb-graph -e OBSIDIAN_VAULT_PATH=… -- .venv/bin/python -m kdb_mcp.server`.
- **Plans:** Phase 2 `…/plans/2026-06-11-get-body-content-tool.md`; Phase 3a `…/plans/2026-06-11-phase3a-mcp-read-server.md`; SDK verification `…/specs/2026-06-11-phase3-mcp-sdk-verification.md`.
- **Ledger:** `docs/TASKS.md` #113 (Phase 1/2/3a done; 3b next) · **North Star:** `docs/CODEBASE_OVERVIEW.md` (two 2026-06-11 changelog entries).
- Memory: [[project_113_graph_access_mcp]] · [[feedback_think_before_speaking_no_option_spray]] · [[feedback_interrogate_anchored_premise]] · [[feedback_terse_signals_clear_thinking]].
