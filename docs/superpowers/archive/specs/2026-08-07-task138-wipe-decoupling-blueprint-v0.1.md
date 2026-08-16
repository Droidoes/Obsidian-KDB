# Task #138 Blueprint v0.1 — Decouple wipe from run: `--cold`/`--yes` → `--wipe`

Status: **SHIPPED 2026-08-07** (suite 3207 green; live sandbox gate passed —
see §9).

Date: 2026-08-07. Author: Kimi K3, from a design discussion with Joseph (same day).
Supersedes: the `--cold` half of #135 (its wipe machinery survives, relocated).
Absorbs: #137 (Joseph picked option (a) — journals archived on wipe).

## 1. Problem

#135 shipped `--cold` as a run flag: wipe derived state, then run, in one
invocation. Joseph's architectural call 2026-08-07: **cold vs warm is not a real
distinction** — it is a reflection of derived state, not a run mode. Warm-out-of-
nothing *is* cold: with no manifest every source is new, and the graph / wiki
tree / manifest are created on demand. The first-ever run and every test in the
suite run warm against empty state. The only real operation `--cold` adds on top
of a plain run is the wipe — so the wipe stands alone and the run keeps one
behavior.

Two corollaries Joseph ratified in the same discussion:

- **`--yes` dies.** Wipe is the system's one irreversible operation; it is
  always manually confirmed. A bare `--yes` flag does not indicate what it
  belongs to, which invites misuse down the road.
- **The wipe owns the journals question (#137 option (a)).** Before deleting,
  the wipe moves `state/runs/` aside so the replay tape left behind is clean —
  verify/rebuild over post-wipe history then match live with no scoping tricks.

## 2. Decisions (ratified 2026-08-07, Joseph)

- **D-138-1 — the run has no modes.** `--cold` and `run(cold=...)` are deleted.
  `kdb-orchestrate` with no wipe flag always means: incremental run against
  whatever state exists.
- **D-138-2 — `--wipe` is wipe-and-exit.** It never runs the pipeline and needs
  neither `--pipeline` nor model resolution (works with no API keys). It
  executes before pipeline listing / model resolution in `main()`.
- **D-138-3 — confirmation is unbypassable.** `--yes` is deleted from
  `kdb-orchestrate`. `--wipe` without `--dry-run` prints exactly what dies
  (paths + counts + archive plan) and requires typing `yes`. Non-interactive
  stdin (EOF) refuses loudly with guidance that mentions no bypass (there is
  none). Decline/refusal exits 1.
- **D-138-4 — the wipe archives journals first.** Non-dry-run, non-empty
  `state/runs/` is moved to `state/pre-wipe-runs/<ts>/` (ts = local timestamp in
  run-id style, `%Y-%m-%dT%H-%M-%S_%Z`), and an empty `runs/` is recreated.
  Archives live *outside* the replayer's scan root
  (`kdb_graph/rebuilder.py:138` — `adapter.discover_runs(journals_dir)` only
  ever receives `state/runs/`), so no replayer/verifier changes are needed.
  Every executed wipe appends one line to a permanent ledger,
  `state/wipes.jsonl` — `{ts, archive_dir, stats…}` — the audit record that
  replaces the run-attached `cold_wipe` event (a wipe no longer has a run to
  attach events to).
- **D-138-5 — `--dry-run` is run-only.** It keeps its run meaning (scan + print
  the plan; no writes, no API). `--wipe --dry-run` is rejected (mutually
  exclusive): the wipe's confirmation gate already prints the identical
  preview — paths, counts, archive plan — and declining is one keystroke away,
  so a separate wipe-preview flag is a redundant second surface.
- **D-138-6 — `graphdb-kdb rebuild --yes` is untouched.** Separate subcommand,
  scoped, recovery tooling (`kdb_graph/cli.py:627`). Out of scope.

Non-goals: replayer/verifier changes (obviated by D-138-4); a wipe-horizon
journal marker (option (b), rejected); prod-vault wipes; any change to what the
wipe deletes (wiki tree, graph file/dir, manifest, alias ledger — as #135).

## 3. Design

CLI shape:

```
kdb-orchestrate --pipeline X --vault-root V [run flags]   # the only run behavior
kdb-orchestrate --vault-root V --wipe                     # wipe + exit
```

`--wipe` and `--dry-run` are mutually exclusive (parser-enforced) — the wipe's
confirmation gate is the only preview surface (D-138-5).

`main()` flow: parse → resolve vault/state/graph paths → **`--wipe` branch**
(preview → confirm → execute → print report → return) → pipeline listing →
model resolution → run. The wipe branch precedes everything it doesn't need.

`_wipe_derived_state(vault_root, state_root, graph_path, dry_run)` — renamed
from `_cold_wipe`, same deletion logic, plus:

- stats gains `run_dirs_archived: int` and `archive_dir: str | None`;
- archive step (non-dry-run, `runs/` exists and non-empty): move the whole
  `runs/` dir to `pre-wipe-runs/<ts>/` (one `shutil.move`), recreate empty
  `runs/`;
- ledger: append one JSON line to `state/wipes.jsonl` on every executed wipe
  (including nothing-to-archive wipes — `archive_dir: null`);
- `dry_run=True` is now internal-only: `main()` uses it to render the
  confirmation gate's preview (stats + archive plan, nothing touched); the CLI
  exposes no wipe-preview flag (D-138-5).

`run()`: the `cold` kwarg, the `cold_stats` plumbing, and the `cold_wipe` event
record are deleted; docstring updated. Nothing else in `run()` changes.

## 4. Implementation plan (single phase)

1. **Tests first** — rewrite the `#135` block in
   `orchestrator/tests/test_kdb_orchestrate.py` (lines ~2001-2277) against the
   new contract (failing).
2. **Implement** — helper rename + archive + ledger; parser swap; `main()`
   restructure; `run()` cleanup.
3. Suite green.
4. **Live sandbox gate** — wipe the sandbox vault (typed confirmation), run,
   then `graphdb-kdb verify` clean over post-wipe journals with no scoping
   tricks. This is #137's live money proof.
5. Docs closure.

## 5. TDD test plan

Rewrite of the `#135` block (~11 tests):

1. `test_wipe_removes_derived_state` — four targets gone; **journals archived**:
   `runs/` exists and is empty, `pre-wipe-runs/<ts>/` holds the former run dirs,
   `wipes.jsonl` has one line with the archive path.
2. `test_wipe_removes_single_file_graph` — Kuzu single-file layout regression
   (the #135 post-ship crash).
3. `test_wipe_dry_run_reports_without_deleting` — nothing deleted, **no archive
   created, no ledger line**, archive plan present in stats.
4. `test_wipe_idempotent_on_missing` — no targets, no `runs/` → stats all
   zero/absent, `archive_dir is None`, ledger still records the executed wipe.
5. `test_main_wipe_prompts_and_decline_aborts` — nothing deleted, `runs/`
   intact, no ledger, exit 1.
6. `test_main_wipe_yes_proceeds` — wipe + archive executed, exit 0, **and the
   pipeline never runs**: no `last_orchestrate.json`, scan/enrich/compile never
   invoked (monkeypatched to explode).
7. `test_main_wipe_needs_neither_pipeline_nor_model` — no `--pipeline` arg and
   `resolve_models_json` monkeypatched to explode; wipe still succeeds.
8. `test_main_wipe_noninteractive_refuses` — EOF on stdin → nonzero exit,
   stderr guidance with **no `--yes` mention**.
9. `test_main_wipe_dry_run_rejected` — parser refuses `--wipe --dry-run`
   (SystemExit; the confirmation gate is the only preview, D-138-5).
10. `test_cold_and_yes_flags_removed` — parser exits (SystemExit) on `--cold`
    and on `--yes`.
11. `test_run_signature_has_no_cold` — `inspect.signature(run)` has no `cold`;
    the two former `run(cold=True)` integration tests are rewritten as
    wipe-helper-then-run (same assertions about rebuilding from sources).
12. **#137 regression (integration)** — using the #132 E2E harness: run A over
    3 sources → wipe via the helper → run B → assert `runs/` contains only run
    B's journal, then rebuild-verify over `state/runs/` matches live with zero
    divergences (previously: 561 `missing_in_live`).

## 6. Verification gates

- `pytest orchestrator/tests/test_kdb_orchestrate.py` green; full suite green.
- Live: sandbox wipe (typed `yes`) → run → `graphdb-kdb verify` clean.
- `kdb-orchestrate --cold` / `--yes` rejected by the parser.

## 7. Blast radius

- `orchestrator/kdb_orchestrate.py` — `_cold_wipe` → `_wipe_derived_state`
  (+archive/ledger), `run()` signature/docstring/plumbing, parser, `main()`.
- `orchestrator/tests/test_kdb_orchestrate.py` — the `#135` block rewritten;
  the #132 E2E's "cold" wording is descriptive only (first run from nothing)
  and stays.
- Docs: `docs/TASKS.md` (#138 row; #137 → closed-absorbed; #135 superseded-in-
  part note), `docs/CODEBASE_OVERVIEW.md` (§211 cold-start paragraph rewritten;
  milestone entry), `AGENTS.md` (entry-point note), `docs/JOURNEY.md` (short
  lesson at closure).
- Verified clean: `scripts/` and `README.md` carry no `--cold`/`--yes`
  references.

## 8. Success criteria

1. Wipe never requires — and never triggers — a run.
2. Confirmation is unbypassable; no bypass flag exists.
3. After wipe + run, `graphdb-kdb verify` over `state/runs/` matches live with
   no manual journal scoping (#137 closed).
4. Suite green; live sandbox gate green.

## 9. Implementation record (2026-08-07)

TDD order as planned: the `#135` block rewritten red (10 failures), then the
implementation to green. Orchestrator module 72/72; full suite **3207 green,
0 failures** (3208 → 3207, net −1 from the test merges below). Deviations
from §5's test plan, all fidelity-preserving:

1. Blueprint tests 6+7 merged into
   `test_main_wipe_yes_proceeds_needs_neither_pipeline_nor_model` (one test
   proves both: `resolve_models_json` and `run` monkeypatched to explode, no
   `--pipeline` passed). Blueprint tests 9+10 merged into
   `test_retired_and_redundant_wipe_flags_rejected` (one parser test loops
   `--wipe --dry-run` / `--cold` / `--yes`).
2. `test_run_cold_dry_run_wipes_nothing` has no post-#138 equivalent and was
   dropped: the wipe×dry-run combination no longer exists (D-138-5 mutex).
   Its "nothing is touched" coverage lives in
   `test_wipe_dry_run_reports_without_touching` (the helper preview) plus the
   mutex rejection.
3. The confirmation gate's preview prints the archive *parent*
   (`pre-wipe-runs/<wipe timestamp>`) rather than an exact path — execution
   mints its own timestamp, so an exact preview path could drift by a second
   and mislead.
4. `test_wipe_then_run_rebuilds_from_sources`'s no-wipe-event assertion is
   conditional on the event log existing: post-#138 a clean run records
   nothing at warning level, so the file isn't created — previously the
   deleted `cold_wipe` warning event was the only thing creating it on clean
   runs (the tell recorded in JOURNEY §8).

Live sandbox gate (2026-08-07, gpt-5.4-mini): wipe — 241 wiki files removed,
graph + manifest gone, 17 journal entries archived to
`pre-wipe-runs/2026-08-07T13-24-41_EDT`, ledger line written → run
`2026-08-07T13-25-12_EDT` (28 compiled / 7 noise / 1 quarantine) →
`graphdb-kdb verify` over **unscoped** `state/runs/`: **ok — replay and live
graph agree, zero divergences** (249 entities / 28 sources / 396 links / 266
supports / 10 domains / 250 belongs_to; `missing_in_live` 0,
`missing_in_replay` 0, replayed = 1 — the post-wipe journal only). The
561-false-`missing_in_live` class (#137) is dead. All §8 criteria met.
