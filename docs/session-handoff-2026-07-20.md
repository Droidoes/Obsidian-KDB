# Session handoff — 2026-07-20

> Richest single catch-up artifact for the next session. Written deliberately as the resume point before a `/clear` — a fresh session should be able to restart from this file alone.

## ⏩ END OF SESSION — vault-in-place brainstorm + full orchestration re-walk; the 11-section workflow doc shipped; design decisions locked; next = WS1 benchmark refresh

A design + documentation session (Kimi Code), continuing the 2026-07-17 "TOMORROW" agenda. **No production code changed.** Two docs commits pushed (`6997a0f`, `718e75d`); working tree clean. The session did three things: (1) re-walked the entire orchestration pipeline end-to-end as a refresher (scan → Pass-1 → Pass-2 → validate/repair/canonicalize → β commit → finalize); (2) built and fully reviewed `docs/reference/orchestration-workflow.html`; (3) ran the vault-in-place brainstorm to a set of locked decisions + a sequenced workstream stack.

### Shipped
- **`docs/reference/orchestration-workflow.html`** (`718e75d`) — self-contained (no CDN), dark/light mode, 11 sections with 10 hand-drawn SVG diagrams: big-picture loop, pipelines & scan scope, hashes & manifest, Pass-1, Pass-2, gauntlet, β commit, intake phases, finalize, state model, failure semantics. Includes real rendered prompt samples for both passes, the LLM call contract, and a 9-term plain-language glossary. **Reviewed section-by-section by Joseph — all 11 signed off.**
- **`6997a0f`** — the 2026-07-17 handoff's late-evening amendments (rode along as planned).
- **Vault-side (untracked, outside repo):** `~/Obsidian/Projects/Obsidian-KDB/Sample-Prompt-Pass-2.md` — full untruncated Pass-2 prompt for the Buddy source, rendered **offline, zero API cost** via the real code path (`parse_source_file` → `build_context_snapshot` on the read-only sandbox graph → `prompt_builder.build_prompt`). Pairs with the pre-existing `Sample-Prompt-Pass-1.md`. The same render recipe is the prototype for the offline re-render tool (below).

---

## Locked decisions (ratified this session)

1. **Uniform full pipeline for vault ingest (Option B).** Every in-scope `.md` gets Pass-1 + Pass-2; noise verdicts are the built-in cost brake. Cost is not prohibitive: ≈$3 (deepseek-v4-flash) / ≈$20–40 (gpt-5.4-mini class) / $40–80 (frontier) for ~1,986 sources; 6–12h wall clock. Tiered/Pass-1-only options dropped.
2. **Vault-in-place is a GENERAL pipeline — no special-casing.** Verified in code: `type` in pipelines.json is validated but behaviorally inert; behavior comes entirely from `root` + `excludes` + globs. `KDB/` belongs in **`excludes`** (walk-time prune), NOT `force_noise` (which still scans/hashes/records). Main-vault entry will be: `root: /home/ftu/Obsidian`, `excludes: ["KDB/"]`, `force_noise: ["Daily Notes/**", "Projects/**"]`.
3. **DEPRECATE the in-place vs raw concept entirely.** There are only pipelines, each an absolute `root`; "raw" pipelines survive only as the convention `root: <vault>/KDB/raw/<pipeline-id>`. Companion guard: **exclude-aware overlap-root audit** when pipelines.json is written/loaded (naive prefix check would false-positive on vault-root containing `KDB/raw/*` while `excludes: ["KDB/"]` — must compute effective scopes).
4. **Graph data location: `~/Droidoes/GraphDB-KDB` — RATIFIED.** Supersedes the 7-17 deferred question AND the current code default (`<vault>/KDB/graph`). Rationale (Joseph): standalone subsystem — Obsidian-KDB is merely one producer into it; portability (e.g. GCP/BQ migration) requires living outside both vault and repo. Sync-avoidance is NOT the reason. Implementation (WS3): flip the default (3-line change per 7-17 handoff) or `KDB_GRAPH_PATH`. **Precondition: inspect + archive the stray 26.8 MB schema-2.3 file currently at that path** (D35-era leftover, mtime 2026-06-08) before the official run builds there.
5. **GraphDB-KDB package extraction (Stage 1) is AFTER MCP work — low priority.** The roadmap exists (`docs/reference/graphdb-kdb-extraction-roadmap.md`; Stage 0 = monorepo today, Stage-1 trigger fired but never executed). No `~/Droidoes/GraphDB-KDB-package/` exists.
6. **Vocabulary provenance (Joseph's correction, recorded):** domains.json / source_types.json came from **multi-frontier-model deliberation** (NW-4/NW-7 arcs), NOT from sandbox curation. But they've only been *exercised* against curated publication-form content — OneNote bulk is a new distribution; WS2 measures before any tuning.

## Discoveries (all feed WS3 design)

- **D39 REBUILD CONTRACT IS BROKEN for orchestrator-era runs.** `graphdb-kdb rebuild` discovers runs via `state/runs/<run_id>.json` + per-run `compile_result.json` + `last_scan.json` — and the orchestrator writes NONE of them in the normal path (compile_result goes to state root only, overwritten each run; journal only on orphan-reaping). On the sandbox today, rebuild finds zero eligible runs. **Converges with #94** (fix option b: restore per-run sidecars) — ONE sidecar-restoration work item closes both the #94 resume path AND the D39 rebuild path. Deserves its own task-ledger entry at WS3. #94 itself remains the pre-production gate.
- **`pass2_prompt_version` is EMPTY in run telemetry** (Pass-1 has `1.2.0`). The Pass-2 system prompt is vault-owned/operator-editable, so edits are currently invisible. Rule: **version stamp FIRST (plus file-SHA anchor per run, the canonicalize-ledger pattern), THEN prompt edits.**
- **Pass-2 prompt hygiene (Joseph-directed):** drop the entire slug-space/source-id-space paragraph from `KDB-Compiler-System-Prompt.md` §1 + the matching self-check bullet + the same jargon in `compiled_source_response.schema.json` descriptions. Precedent: Task #95 (Pass-1 never asks about code-owned fields). Enforcement is already mechanical (`additionalProperties: false` + runner injection at `compiler/compiler.py:474-528`, Task #41 — no new code needed). Validate via benchmark cohort (quarantine/retry KPIs shouldn't move).
- **Prompt-capture direction: SYMMETRIC MINIMALISM** (reversed mid-session from "close the gap"). Bodies become opt-in via `KDB_RESP_CAPTURE_FULL` for BOTH passes (Pass-1 currently always records); outputs + hashes stay always-on; run-level anchors recorded (template SHA + vocab SHAs + versions); offline re-render tool for on-demand prompts. Open decision: Pass-2 context-snapshot exception — **lean: record it** (see next).
- **Context snapshots: capture as TELEMETRY, not logs, not reconstruction sidecar.** Proposed `state/runs/<run_id>/context_snapshots.jsonl` — one line per source: `source_id, domain, cold_start, {slug: tier}, entity_search_keys hit/miss`, ~1–2KB/line, always-on. It's the measurement substrate for entity_reuse / #92 (domain-scoped T2) / cold-start behavior on the big run. Note: today's `ContextSnapshot` FLATTENS tiers — capturing tier provenance means hooking the loader's tier-assignment stage (small change).
- **Retry/failure contract (documented in the HTML):** transport 3 attempts w/ backoff (`call_model_retry.py`); content 2 attempts per pass, free repair rungs (backslash escape, slug coercion); failure declared after 2nd → **quarantine, loop continues** (both passes — per-source content failures never abort); only run-fatal/invariant aborts (D-91-8). `last_orchestrate.json` written regardless.
- **Pass-1-only runs are already supported, zero code:** `kdb-enrich --vault <root> --include 'glob/**' --model <id>` (standalone, writes frontmatter + sidecars/journal only; sample is disposable — official run re-enriches). Basis of WS2.
- **Run size is a design variable:** finalize is once-per-invocation → for the ~2k-source ingest prefer **chunked runs** (`--limit N`, repeated) over one monolith: bounds finalize cost/memory, per-chunk checkpoints, caps #94 blast radius.
- **Layout unification:** make `runs/<run_id>/pass2/` the single RespStatsRecord convention (retire/redirect the `llm_resp/` default); target runs/ layout sketched in session (per-run `last_scan.json` + `compile_result.json` restored, `context_snapshots.jsonl`, optional `prompt_system.md`, `pass1/`, `pass2/`, events jsonl, `retraction.json`).
- **`scripts/benchmark_regression.sh` is STALE** (drives the retired `kdb-benchmark --models/--sources` CLI — would fail today).
- **Pass-1 sidecar asymmetry explained:** Pass-1 sidecars always record full prompt (that's where the Pass-1 sample came from); Pass-2 RespStatsRecords gate bodies behind `KDB_RESP_CAPTURE_FULL`.

## The stack (ordered; each gates the next)

1. **WS1 — model benchmark refresh (NEXT).** OPEN QUESTION (Joseph hasn't answered): cohort = **A** (agent researches post-June releases across the 6 keyed providers, proposes ~4–6 models incl. quality anchor; user approves; config-only `common/models.json` additions; runbook `docs/reference/benchmark-cohort-procedure.md`; user fires runs, ~$1–2/cohort) / **B** (Joseph names models) / **C** (existing pool only + score the pending Jun 8 gpt-5.4-mini run — that scoring is free either way). Sub-questions if A: per-model budget cap? local Ollama as zero-cost baseline?
2. **WS2 — OneNote preflight.** `kdb-enrich` over every ~12th of 1,258 OneNote files (~100-file sample), analyze signal/noise ratio, domain + source_type distributions, `other_reason` texts, confidence; tune vocab ONLY if the sample says so (config-only edits). Feeds OneNote scope policy + real cost model for WS3.
3. **WS3 — vault-in-place rollout design (max-effort planning).** Scope: #94 fix + D39 sidecar restoration (one work item); main-vault pipelines.json; graph default flip to `~/Droidoes/GraphDB-KDB` (+ stray archive); deprecate in-place/raw + overlap audit; chunked-run sizing; prompt-capture minimalism + `context_snapshots.jsonl`; llm_resp→pass2 unification; Pass-2 prompt hygiene (version first, then deletions); `~/Obsidian/KDB` stale-partial reset (precondition from 7-17); file task-ledger entries for the new work items. Also: OneDrive→Google Drive migration absorbed (vault local on C:, Drive live-sync, D: snapshot; refresh snapshot before big run; graph binaries stay OUT of the vault per decision #4).
4. **WS4 — MCP server revisit, possibly start fresh.** Current: 7 read-only structural tools (#113). Gaps recorded: no content search (no FTS/embeddings anywhere), analytics unexposed (pagerank/communities/structural-holes/orphans exist in `kdb_graph` but no MCP route), no domain-scoped browsing, Source metadata (summary/author/domain) unqueryable, dormant Claim layer.
5. **WS5 — GraphDB-KDB extraction Stage 1** (after MCP).

## Housekeeping

- Working tree clean; both commits on `origin/main`. Docs-only commits — no test suite run needed.
- The HTML doc's section 10 (state model) describes the CONTRACT layout; revisit after WS3 ratifies the target runs/ layout.
- Benchmark leaderboard: last updated 2026-06-07 (gpt-5.4-mini 84.67 leads; 4 models scored of 9 in pool); Jun 8 gpt-5.4-mini run unscored (free to score in).

## Pointers

- **The doc:** `docs/reference/orchestration-workflow.html` (open in any browser).
- **This session's design substance:** all in this handoff; the HTML doc has the workflow mechanics.
- **Ledger:** `docs/TASKS.md` — #94 blocker (pre-production), #93 proposed (kdb-audit — Joseph lean: minimal pre/post-run check yes, full auditor no), #92 hypothesis (domain-scoped T2 — the big run's context_snapshots.jsonl is its evidence source).
- **Runbook:** `docs/reference/benchmark-cohort-procedure.md`.
- **Prior handoffs:** `docs/session-handoff-2026-07-17.md` (project review + v0.5.7), `docs/2026-07-07-state-of-the-system.md` §7 (ingestion readiness).
