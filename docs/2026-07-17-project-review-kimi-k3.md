# Project Review — Kimi K3 (2026-07-17)

> Independent full-project review (docs + code + external data dirs), requested by Joseph
> and executed against `main` @ `cd5c9a2`. Method: four parallel read-only inspection
> threads — documentation/intent, code architecture, engineering hygiene (tests/packaging/
> ops), and external data-directory inventory — synthesized into the evaluation below.
> Companion to `docs/2026-07-07-state-of-the-system.md` (self-assessment); this doc is the
> *external read* on the same system. Where the two disagree, the discrepancy is flagged.

## TL;DR

The engineering core is ahead of its documentation perimeter. The architecture needs no
intervention — every load-bearing claim verified true in code. The real problems are
doc/config drift (`AGENTS.md`, `requirements.txt`, North Star §5/§8.3), zero CI, and the
unsettled ingestion preconditions. Nothing found contradicts the 2026-07-07 state doc's
self-assessment; the disk inspection *sharpened* it (two new material facts: the OneNote
swamp and the OneDrive mount).

One correction to the 2026-07-07 handoff: the "open commit gate" is mostly closed —
`docs/session-handoff-2026-07-07.md` and the `CODEBASE_OVERVIEW.md` changelog entry are
already committed (`cd5c9a2`). Only 3 untracked files remain:
`docs/session-handoff-2026-06-10.md`, `docs/session-handoff-2026-06-11.md`,
`docs/reference/Karpathy-llm-wiki.md`.

---

## 1. Intent & objectives

**The intent is coherent, well-articulated, and honestly tracked.** A Karpathy-style
LLM-compiled knowledge base: the LLM is a stateless compiler emitting structured JSON;
deterministic Python owns every path, frontmatter byte, and filesystem write. Since the
May reframe (#63), the deeper bet is a **raw-text → knowledge-graph compiler** — the Kuzu
graph is the live ontology authority (D51), the wiki merely a rendering.

**The objectives are realistic *because* the project course-corrected.** The 2026-07-07
pivot is the strongest evidence of project health: before building `stress_test`, a
precondition check on the live 248-entity graph found the metacognitive analytics
degenerate at personal scale (214/218 single-source entities; 2/486 cross-community
edges), and the idea was abandoned *on the merits* rather than shipped as
correct-but-unvalidatable code. The current objective — **build a comprehensive graph via
vault-in-place ingestion (~44×), then re-test the operations thesis** — is the right one.

**Risk on intent:** the aspirational operations/metacognition tier may never arrive at
single-user scale (the docs say so themselves). The long-run value case rests on
canonicalization + retrieval being worth it on their own — a load-bearing premise worth
restating whenever the 2.0 tier is re-evaluated.

## 2. Software architecture

**Strongest aspect of the project. Verified, not assumed:**

- **Layering is enforced, not aspirational.** Seven packages (`common` leaf →
  `ingestion`/`compiler`/`orchestrator` → `kdb_graph` substrate → `kdb_mcp`/`tools`
  interface) with AST-based import-contract tests (`tools/tests/test_package_boundaries.py`).
  `kdb_graph`'s zero-sibling-dependency invariant holds (guard test permits `common`, but
  the stricter zero-`common` state is real — held by convention, not test; see §3.8).
- **Controller discipline is real.** `json_mode` on both LLM passes; schema + semantic
  gates before any write; `compile_source` writes NOTHING (produce-don't-write,
  `compiler/compiler.py:637-644`); all mutation via `page_writer` / `manifest_writer` /
  `frontmatter_embedder` / `intake` with atomic I/O.
- **Failure engineering is better than most production systems.** β commit model (page →
  graph → manifest *last*) with a 3-class failure taxonomy and self-heal semantics
  (`orchestrator/kdb_orchestrate.py:58-87`); quarantine-and-continue; exactly-one
  telemetry record per compile via `finally`; retry honors `Retry-After` with typed SDK
  exceptions only (`common/call_model_retry.py:28-37`); `last_orchestrate.json` written
  on every exit path including crashes.
- **Graph layer is genuinely producer-agnostic and recoverable.** Adapter protocol,
  journal-version gating, whole-DB rebuild from run journals, and a verifier that replays
  into a temp Kuzu and structural-diffs against live. The #112 `read_only` fix is real and
  complete (write methods guarded at `kdb_graph/graphdb.py:219-242`; read-only consumers
  cannot trigger a migration).
- ~43.7k LOC Python (incl. ~20k test LOC); **1,291 tests collect clean**; per-test graph
  isolation via autouse `KDB_GRAPH_PATH` fixture (root `conftest.py`).

**Verified end-to-end flow** (corrects the stale doc flow): `kdb-orchestrate` → scan →
per-source [enrich (Pass-1 LLM) → compile_source (Pass-2: context snapshot → LLM
json_mode → schema/semantic gates → repair → canonicalize) → commit: page_writer →
Kuzu txn → manifest-last] → reconcile → finalize (wire_links, detect_orphans) →
kdb-clean orphans. Exactly two LLM call sites: `ingestion/enrich/pass1_caller.py:176`,
`compiler/compiler.py:312`.

## 3. Issues

Ranked by consequence:

1. **`requirements.txt` is stale and dangerous.** Header claims "mirrored from
   pyproject.toml" but lists 6 of 12 runtime deps (missing `kuzu`, `jinja2`,
   `google-genai`, `pyyaml`, `networkx`, `python-louvain`). Installing from it yields a
   broken environment. Delete or regenerate.
2. **Two conflicting graph-path defaults — silent split-brain.** `kdb_graph/__init__.py:47`
   still defaults to `~/Droidoes/GraphDB-KDB` (the "dead stray" — see §5), while
   `kdb_mcp/config.py:16-25` derives `<vault>/KDB/graph`. The `graphdb-kdb` CLI and the
   MCP server silently point at different stores.
3. **Perimeter docs describe a repo that no longer exists.** `AGENTS.md` references
   `kdb_compiler/`/`graphdb_kdb`/`kdb_benchmark/`, phantom commands `kdb-plan`/`kdb-compile`,
   wrong coverage flags, and a wrong pipeline stage list. `README.md` is frozen at M0.
   `QWEN.md`, `benchmark/README.md` (claims engine lives in `kdb_benchmark/`), `ROADMAP.md`
   (stuck at 2026-06-02), and `.gitignore` comments are all stale. North Star drift:
   §5 stage order (code does graph-sync *before* manifest, the β model), §8.3's D-S0
   invariant (obsoleted by #91 — `kdb_orchestrate.py:28-31` imports `GraphDB` directly),
   `ingestor.py` → `intake.py`, plus several broken cross-references
   (`docs/what-is-ontology-for-V1.md`, `docs/run-4-findings.md`, round-5 review paths).
4. **Dead/misleading code residue.** `sync_current_run` (`kdb_graph/adapters/obsidian_runs.py:202`)
   has no production caller while its docstring claims the orchestrator calls it;
   `knowledge_graph/` (831 LOC) confirmed dead (packaging-excluded, zero inbound refs) but
   still present and still advertised in README; `requests` and `scipy` are declared deps
   with zero imports anywhere.
5. **`graphdb-kdb` read subcommands open the DB writable** (`kdb_graph/cli.py:50-122`) —
   a `stats` command can silently trigger a schema migration; the #112 read-only
   discipline was not extended to the CLI.
6. **Data-dir sprawl, confirmed on disk.** Three Kuzu files across three roots (26 MB
   stray in `~/Droidoes`; 1 MB stale under `~/Obsidian/KDB/state/` + 2 snapshots; 19.8 MB
   live sandbox). The official `~/Obsidian/KDB` has been silent since 2026-05-23
   (raw=8, wiki=83 as claimed — but "no graph" is imprecise: a stale `state/graph` +
   snapshots exist).
7. **Version story still lies.** `pyproject version = "0.1.0"` never bumped;
   `common/__init__.py` stuck at 0.5.2 (flagged in RELEASES.md, never fixed); `main` is
   43 commits past `v0.5.6` with all MCP work untagged. `TASKS.md` violates its own
   conventions (~30 `done` rows never moved to Closed; status vocabulary drifted beyond
   the documented `open/in-progress/closed`).
8. **Minor.** `kdb_mcp` absent from the boundary-test guard (`tools/tests/test_package_boundaries.py:4-42`);
   the stricter zero-`common` invariant for `kdb_graph` is not test-enforced; Pass-1 has
   no backoff retry (Pass-2 does — undocumented asymmetry, `pass1_caller.py:176`);
   vestigial `uses_real_graph_context` marker (zero references); duplicate `venv/` +
   `.venv/`; committed debug dumps in `tools/diagnostics/`; historical one-shot migration
   scripts self-labeled but still in `scripts/`; ~30 broad-except sites (mostly justified;
   `tools/cleanup.py:219` masks programming errors).

## 4. What's missing that should be there

- **Any CI whatsoever.** No GitHub Actions, no lint, no type check, no pre-commit, no
  coverage config (despite `pytest-cov` dev dep). 1,291 green tests that nothing runs
  automatically — one broken push to `main` would go unnoticed. For a project this
  disciplined, this is the strangest gap.
- **The at-scale ingestion preconditions** (state doc §7 lists them; none are done):
  resume-after-failure proven at scale (#94 dissolved-but-untested — one-shot fragility
  is *the* blocker for a multi-hour run), X6/`force_noise` selection spot-check on real
  notes, official data-dir reset.
- **`#93 kdb-audit`** — cross-store consistency gate (graph ↔ manifest ↔ wiki),
  proposed-not-built; exactly what is wanted before and after the big run.
- **Snapshot *restore*.** Recovery tiers 1 (rebuild) and 3 (recompile) exist, but
  snapshots are write-only — `load-snapshot` was cut from #63.9. The 3-tier recovery
  story has a hole in the middle.
- **Version hygiene.** Tag `v0.5.7` (or fold MCP into the ingestion release); make
  `git describe` genuinely authoritative as RELEASES.md claims.
- **Ingestion-relevant facts the plan hasn't absorbed yet** (from disk inspection):
  the vault is a **OneDrive-synced Windows mount** (`~/Obsidian` → OneDrive via WSL 9p)
  — I/O latency + sync-conflict risk for a Kuzu DB living there, and `find` without `-L`
  returns 0 notes (script-killer). And **79% of the vault is OneNote imports** (1,259 of
  1,593 notes); the curated vault is ~334 notes across ~19 dirs. The "1,586 notes across
  ~20 domains" framing both overstates and understates the selection problem — the chaff
  *must* be filtered or the run pays for ~1,259 junk compiles.

## 5. `~/Droidoes/GraphDB-KDB`

Checked directly (file-level inspection only; no DB opened). The handoff's description is
**wrong in an interesting way**:

- It is a **single 26 MB file**, not a directory — a valid Kuzu single-file DB (`KUZU'`
  magic, same storage version as the live sandbox graph).
- mtime is **2026-06-08 21:54** — the *same evening* as the sandbox run (finished 23:38).
  It is **not** a 2.3-era relic; plausibly written ~2.5 hours before the sandbox run by a
  graph-ingest test pointed at the wrong output path. Cleanly closed (no `.wal`/`.lock`),
  untouched since.
- **Why it matters beyond housekeeping:** it is still the *default graph path* in
  `kdb_graph/__init__.py:47`. The "dead stray" is one absent `KDB_GRAPH_PATH` env var away
  from silently becoming the live store again. Change the default (vault-derived, or fail
  loud) *before* deleting the file. After that, it is a safe deletion candidate.

### External data-dir inventory (verified 2026-07-17)

| Location | Finding |
|---|---|
| `~/Droidoes/GraphDB-KDB` | 26 MB single-file Kuzu DB, mtime 2026-06-08 21:54, orphan; still referenced as package default |
| `~/Obsidian/KDB` | Official dir: raw=8, wiki=83, manifest + 52 run-journal entries, last write 2026-05-23; stale `state/graph` (1 MB, 2026-05-17) + 2 snapshots |
| `~/Obsidian/Vault-in-place-test-run/KDB` | Sandbox: 19.8 MB graph (2026-06-08 23:38), wiki=248 pages, state + journals intact |
| `~/Obsidian` | Symlink → OneDrive Windows mount; 1,593 `.md` excl. KDB dirs (claim 1,586 ✓); 1,259 (79%) under `OneNote/`; ~334 curated across ~19 top-level dirs |

## 6. Overall

A well-architected, unusually honest project whose engineering core is ahead of its
documentation perimeter. The architecture needs no intervention; the doc/config drift,
the missing CI, and the unsettled ingestion preconditions do. The state doc's "binding
constraint is corpus scale, not code quality" is confirmed by this read — with the
addition that the ingestion brainstorm should absorb the OneNote-swamp and OneDrive-mount
facts before scoping the run.

---

*Reviewer: Kimi K3 (Kimi Code CLI). Evidence base: four read-only inspection threads over
`main` @ `cd5c9a2`; all file:line citations verified at review time.*
