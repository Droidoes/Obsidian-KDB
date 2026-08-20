# Roadmap — Completed Milestones (M0–M4)

Archived verbatim from `docs/CODEBASE_OVERVIEW.md` §11 on 2026-08-19 (Task #146 housekeeping). Forward-looking items (M3+) remain in the overview.

### M0 — Scaffolding (commit `796848b`) ✅
- [x] Vault scaffold: `~/Obsidian/KDB/{raw, wiki/{summaries, concepts, articles}, state/runs, KDB-Compiler-System-Prompt.md}`
- [x] Repo scaffold: `~/Droidoes/Obsidian-KDB/{docs, kdb_compiler/tests/fixtures}`
- [x] `docs/CODEBASE_OVERVIEW.md` (this file)
- [x] `KDB/KDB-Compiler-System-Prompt.md` — kdb_graph_compiler invariants for LLM
- [x] ~~`KDB/wiki/index.md`, `KDB/wiki/log.md` (empty)~~ — dropped by D23/D24
- [x] `KDB/state/manifest.json` (initial empty shape)
- [x] `kdb_compiler/__init__.py` + 8 module stubs
- [x] Initial commit

### M0.1 — Codex review remediation ✅
All M0.1 items landed; system prompt rewritten, shared seams added, schema skeleton + test fixtures committed.

### M1 — Deterministic layer (no LLM yet) ✅
Scanner, manifest updater, validators, call_model + retry, end-to-end dry run all landed. Fixture-based unit tests green throughout.

### M1.7 — Validator + reconciler on real vault ✅
`page_writer`, `manifest_writer`, `kdb_compile.py` kdb_graph_orchestrator (8-stage pipeline — since superseded by `kdb_orchestrate.py`), validate_compile_result with gate/measure split, reconciler for measure findings. Verified live on real vault 2026-04-21.

### M2 — LLM layer + benchmark ✅
- Live LLM kdb_graph_compiler producing `compile_result.json` from real sources
- Per-call response capture (`RespStatsRecord` + `kdb-replay` fixture-driven replay)
- `kdb_benchmark/` engine: runner + scorer + scorecard + CLI (see §7)
- Canonical 5-source corpus + `models.json` registry
- Headline scorecard 2026-05-08 baseline established (haiku-4.5 vs sonnet-4.6)
- See `docs/TASKS.md` for the 30+ tasks closed across this milestone

### M3 — GraphDB-KDB Layer (#63) ✅ DONE — sub-tasks #63.0 through #63.9
Task #63 — refoundation as raw-text → knowledge-graph kdb_graph_compiler. Supersedes #26 + #27. See §8.
- **Architecture deliberation:** D32–D40 locked through 3 rounds of Codex review. D-A1/A2/B1/S0–S3 locked through 3 more rounds during Phase 3 implementation. D-S4/S5/S6 locked through #63.7 live validation (A1→A4 on real vault). Snapshot artifact design (#63.9) Codex-reviewed in 1 round; upgraded "JSONL dump" → "self-verifying JSONL + manifest + schema evidence" pre-implementation.
- **Companion docs:** blueprint, paradigm record, producer contract, extraction roadmap, manifest succession arc, Phase 3 implementation blueprint, snapshot Codex prompt (see §8.5).
- **Sub-tasks shipped:** #63.0 replay-contract verification; #63.1 schema + skeleton; #63.2 ingestion; #63.3 read query API; #63.4 hybrid analytics; #63.5 verifier; #63.5b rename pass (Page→Entity, compile_*→ingest_*); #63.6 B-lite rebuilder + Obsidian adapter; #63.7-pre Stage 9 wiring via adapter + sidecar archival; #63.7 live integration validation (4 scenarios × 3 providers); #63.8 docs (this section); #63.9 snapshot/export — JSONL+manifest+schema.cypher with per-file sha256 row counts; CLI subcommand `graphdb-kdb snapshot`; `latest.json` pointer sidecar.
- **#63.7 live validation arc (2026-05-14):** A1 no-op scan → Stage 9 archives sidecar, 0 entities upserted; A2 haiku-4.5 recompile of EP1 → 1 page (summary only); A3 gemini-3.1-flash-lite recompile of Howard-Marks → 7 pages + 10 edges (new default validated); A4 deepseek-v4-flash recompile of Buffett → JSON gate fail, D38 non-fatal contract held (graph not corrupted). Surfaced bugs fixed inline: D-S4 (`last_run_id` Phase 1 semantic), D-S5 (`KDB_GRAPH_PATH` test isolation). New feature: D-S6 (`--model` flag with shared registry). Deferred follow-ups: `raw_response_text=None` capture bug in alibaba extract-failure path (separate from #63.7 scope); deepseek-v4-flash single-trial regression observation parked for ~2026-05-18 retest.
- **3-tier recovery story now complete:** (1) Kuzu corrupted → `graphdb-kdb rebuild` from journals; (2) journals + Kuzu both lost → restore from snapshot (load-snapshot is a future v2 — write-only is the #63.9 scope cut); (3) all three lost → re-run `kdb-compile` on the live vault.
- **Test surface:** 106 graphdb_kdb tests (96 pre-#63.9 + 10 snapshot tests) + 6 Stage-9 integration tests in kdb_compiler/tests/ (550 total kdb-relevant tests).

### M4 — Canonicalization layer (#74) ✅ DONE — sub-tasks #74.1 through #74.8
Task #74 — Stage [6] canonicalize lands as a top-level compile stage between reconcile and build_source_state; wiki and graph see the same canonical names. Locked decisions D-R5-1..D-R5-13 + D52. See §5 (pipeline), §8.2 (schema delta), §8.3 (adapter alias-write pass), §8.4 (rebuild + snapshot v2), and the full blueprint at `docs/archive/tasks/task74-canonicalization-blueprint.md`.
- **Sub-tasks shipped:** #74.1 schema delta (Entity.canonical_id + ALIAS_OF + migration); #74.2 `aliases.json` ledger loader; #74.3 `canonicalize.run()` algorithm; #74.4 Stage [6] wiring + journal `2.1 → 2.2` bump + `compile_result.schema.json` whitelist; #74.5 adapter Phase 3.5 — writes alias Entity + ALIAS_OF + `canonical_id`; #74.6 `graphdb-kdb verify` Layer 3 (C1–C4 invariants on the live graph); #74.7 snapshot format v2 + canonical_meta replay tests + back-compat tests; #74.8 docs (this section).
- **Round 5 external review:** Antigravity + Codex parallel reviews on the blueprint (see `docs/archive/rounds/round5-external-review-{antigravity,codex,prompt}.md`); locked OQ-E (direct-to-canonical SUPPORTS), OQ-F (canonical-wins + longest + UNION merge), OQ-G (JSON ledger format) before implementation.
- **Test surface delta:** +14 alias-ingestion tests + 11 canonicalization-invariant tests + 3 snapshot-v2 tests + 3 rebuilder canonical_meta tests + 1 schema back-compat test.
- **Half-wire closure:** between #74.4 and #74.5, the adapter accepted v2.2 journals but ignored `canonical_meta`; #74.5 closed this. Wiki ≡ graph at the naming layer (verified by Layer 3 invariants).
