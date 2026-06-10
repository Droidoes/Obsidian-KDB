# Session handoff — 2026-06-08

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## ⏩ END OF SESSION — graph viewer enhanced; sandbox automation built; 2.0 architecture framed; strategic fork open

Evening session. No code merged — all changes uncommitted (see commit gate below). Primary output: `scripts/sandbox-run.sh` + graph viewer entity-type colors + `docs/reference/graph-nodes-edges-logic.md` stub. Ended in a 2.0 design discussion — strategic decision deferred to next session.

### What happened

1. **RentCafe Google Task closed.** 2.95% fee = $50+/month; continuing to mail check at $0.78/stamp. Task marked completed in Google Tasks.

2. **2.0 Claim layer architecture framed.** Reviewed what 1.0 gives (structural topology: entities exist, sources reference them, concepts link to concepts) vs. what 2.0 adds (propositional knowledge: what sources *assert* about entities). Key gap: `LINKS_TO` says X references Z, but not what X claims about Z. 2.0 adds:
   - `Claim` nodes — discrete propositions extracted from source body
   - `ABOUT` edge (Claim → Entity) — LLM-identified
   - `EVIDENCED_BY` edge (Claim → Source) — code-derived
   - `CONTRADICTS` edge (Claim ↔ Claim) — detection TBD

3. **Node/edge logic clarified and documented.** Key insight surfaced:
   - LLM decides: which entities exist + which entities link to which (via wikilinks → LINKS_TO)
   - Code decides: all provenance edges (SUPPORTS, BELONGS_TO, ALIAS_OF) — fully deterministic
   - Stub at `docs/reference/graph-nodes-edges-logic.md` (2.0 section TBD)

4. **kdb-orchestrate run (gpt-5.4-mini, sandbox vault).** 30 sources, 0 quarantined, clean. graph-view.html stored in `benchmark/runs/gpt-5.4-mini-2026-06-08T22-29-44_EDT/`.

5. **Graph viewer enhanced — entity node type colors.**
   - `Entity:summary` → green (Source's former color)
   - `Entity:concept` → sky blue (unchanged)
   - `Entity:article` → medium blue
   - `Source` → purple
   - `Domain` → orange/amber (unchanged)
   - Exporter now sets `type` to `"Entity:{page_type}"` for Entity nodes; template `getNodeColor()` handles subtypes. Legend and filter panel auto-update.

6. **`scripts/sandbox-run.sh` built.** 7-step automation:
   1. Pause OneDrive — prompt Y/n
   2. Reset sandbox — wipe graph/wiki/state, keep config
   3. Setup venv
   4. Run `kdb-orchestrate --pipeline vault-test --emit-kpis` (always on)
   5. Add to leaderboard — finds latest run dir automatically, prompt Y/n
   6. Generate graph viewer HTML — stored in per-run dir
   7. Resume OneDrive reminder
   - Usage: `bash scripts/sandbox-run.sh [--model <id>]` (default: deepseek-v4-flash)

7. **Lessons learned (architecture):**
   - Always verify CLI flags (`--help` or grep) before presenting a command
   - `GraphDB-KDB` at `/home/ftu/Droidoes/GraphDB-KDB` is a 26MB flat FILE, not a Kuzu directory — this blocked `graphdb-kdb rebuild` and needs investigation
   - Bash tool runs outside `.venv` — always prefix Python/CLI diagnostics with venv activation

---

## OPEN — pick up here

- [ ] **Strategic decision (Joseph's call):** build 2.0 Claim extraction into pipeline FIRST (one vault pass = entity + Claim graph), OR do 0.6→1.0 entity-only ingest first then Option-B Claim sweep at 2.0?
  - **Lean: 1.0 first** — 2.0 design unproven; Option B sweep is ~$0.10–0.20 at deepseek rates; validate ingest-at-scale before layering Claim complexity
  - **Lean for 2.0 first:** avoid double LLM cost; richer graph from day one

- [ ] **Flesh out `docs/reference/graph-nodes-edges-logic.md`** — especially 2.0 Claim section: prompt design, Claim schema (granularity, confidence, claim type), pipeline wiring

- [ ] **Investigate `GraphDB-KDB` file/directory issue** — `/home/ftu/Droidoes/GraphDB-KDB` is a flat file (26MB); Kuzu requires a directory. Root-cause + fix needed before `graphdb-kdb rebuild` works

- [ ] **0.6 → 1.0 ingestion arc** — `ingestion/feeder/` is empty; design the Obsidian vault feeder (#88/#91 family)

- [ ] **#107** — deferred Phase-B polish

---

## Housekeeping / commit gate

**Uncommitted changes (awaiting Joseph's go):**
- `M tools/viewer/kdb_graph_viewer.py` — entity subtype split
- `M tools/viewer/kdb_graph_viewer_template.html` — color scheme + getNodeColor()
- `?? docs/reference/graph-nodes-edges-logic.md` — new stub
- `?? docs/session-handoff-2026-06-07-night.md` — from last night (carried over)
- `?? scripts/sandbox-run.sh` — new automation script
- `?? docs/session-handoff-2026-06-08.md` — this file

Also: `main` @ `853a66d`, still 1 ahead of origin from last night's #109 closure.

---

## Pointers

- **Resume artifact:** `docs/reference/graph-nodes-edges-logic.md` — open this first; the 2.0 design discussion picks up here
- **Strategic fork:** 1.0 before 2.0 is the lean; Joseph decides
- **Graph viewer (latest):** `benchmark/runs/gpt-5.4-mini-2026-06-08T22-29-44_EDT/graph-view.html`
- **Sandbox run script:** `bash scripts/sandbox-run.sh --model <id>`
- **Task ledger:** `docs/TASKS.md`
- **North Star:** `docs/CODEBASE_OVERVIEW.md`
