# Problem statement — repo placement & boundaries for the parallel extraction system

> **Status**: draft for external panel review (2026-08-16). Options-free (#125
> precedent): states the problem and questions; does not pre-select a topology.
> Companion brief (internal architecture of the new system — family already
> converged on an extraction ledger; coverage policy decided gate-then-extract):
> [`2026-08-16-gmail-info-search-rank-problem-statement.md`](2026-08-16-gmail-info-search-rank-problem-statement.md).
> **This decision gates all implementation of the parallel system.**

## 1. Joseph's framing (the problem to reason about)

1. The **Obsidian vault is the durable home of all sources** — every external
   corpus arrives as plain markdown in the vault.
2. **Ingestion pipelines** bring external info into the vault (gmail-substack
   feeder shipped as #143; more feeders are candidates, e.g. a model-prompt
   archive).
3. Today those ingestion pipelines live **inside the Obsidian-KDB repo**
   (`ingestion/feeder/`), alongside the knowledge pipeline (`compiler/`,
   `orchestrator/`), the GraphDB (`kdb_graph/`), search (`kdb_search/`), the MCP
   server (`kdb_mcp/`), and `tools/`.
4. Different ingestion pipelines have **different logic and considerations** and
   share little (if any) commonality — so maybe they should be split out. But
   does that imply splitting the ingestion layer out of Obsidian-KDB?
5. The new extraction system for the gmail-substack corpus is **a different
   database in parallel to the GraphDB** — a rank-and-learn ledger, not a
   classify-and-connect graph. It is a **deliberate competing architectural
   experiment**: if it proves more efficient/effective it may later be applied
   to the vault-in-place corpus, and a future harness may combine both systems'
   outputs. Joseph's instinct: this system should live in `~/Droidoes/` as a
   **peer repo**, the way the Obsidian-KDB repo does.

## 2. Context the panel needs

- **Obsidian-KDB repo** (`~/Droidoes/Obsidian-KDB`): Python 3.10+, pip-installable
  (`pip install -e .`), pytest suite (~1,200 non-live tests), `common/` leaf
  package (model pool, `call_model` + retry/telemetry, atomic IO) that imports
  nothing internal; AST-guard-tested layering invariants (`kdb_graph` imports no
  sibling package).
- **The GraphDB itself** lives at `<vault>/KDB/graph` (data in the vault, code in
  the repo). Project state/journals live under `<vault>/KDB/state/`.
- **The new system** (name TBD): SQLite-ledger extraction system over
  `KDB/raw/joseph-ft-public-gmail/` (2,625 rankable articles + weekly inflow).
  Hard write boundary already decided: it never writes the KDB wiki, manifest,
  graph, or pipeline configs. It should reuse the production model pool and
  cost-telemetry discipline (`deepseek-v4-flash` standing model).
- **Single operator** (Joseph), WSL machine. Every added repo is a standing
  operational cost (venv, deps, test suite, conventions).
- The **head-to-head comparison** between the two extraction architectures is a
  planned activity and needs stable exports from both sides.

## 3. Questions the panel should address

1. **Repo topology for the new system.** New package inside Obsidian-KDB vs new
   peer repo under `~/Droidoes/` vs something else. Weigh: independence of the
   experiment, failure/release isolation, single-operator simplicity, ease of the
   head-to-head comparison, and the preserved optionality (apply to
   vault-in-place later; combining harness later).
2. **Shared infrastructure.** If a new repo: what happens to `common/` (model
   pool, `call_model`, retry, telemetry, atomic IO)? Extract into a third shared
   package? pip-depend on Obsidian-KDB? Vendor a copy and accept drift? What
   minimizes long-term coupling cost without forfeiting cost telemetry?
3. **The ingestion layer.** Do feeders stay in Obsidian-KDB, split into their own
   repo, or follow their consumer system? Note: feeders write *sources into the
   vault* — they serve both extraction architectures equally and neither owns
   them.
4. **State placement.** Where does the new system's database/journals live —
   `<vault>/KDB/state/` beside the existing state, repo-local, or elsewhere —
   given the vault is the home of *sources* and GraphDB already keeps its data
   there?
5. **Boundary contract.** Who may read/write what across the two systems and the
   vault? (Raw sources read-only to both? Exports as the only sanctioned
   coupling?)
6. **Convergence path.** If the parallel system wins the head-to-head, what does
   the end-state repo structure look like — does anything move, merge, or retire?

## 4. Constraints

- Single operator; minimize standing operational overhead.
- Obsidian-KDB conventions (dry-run-capable, auditable, reversible; per-package
  tests; layering guards) are the quality bar any new repo must match or adapt.
- The vault's source trees are immutable to both systems.
- Decision needed **before** any implementation of the parallel system begins.

## 5. Out of scope

- The internal architecture of the new system (companion brief + panel round
  already cover it; synthesis in progress).
- Changing the existing knowledge pipeline or GraphDB schema.
- The naming of the new system (Joseph's pick, orthogonal).
