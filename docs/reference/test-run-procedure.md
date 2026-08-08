# Test-Run Procedure — `kdb-orchestrate` on the in-place test vault

Operational runbook for a clean orchestrator test run (e.g. run-4) against the
disposable in-place test vault. Pipeline `vault-test`, root
`~/Obsidian/Vault-in-place-test-run`.

> Running a **multi-model benchmark cohort** (per-model `--emit-kpis` runs →
> `kdb-benchmark score` leaderboard)? See
> **`docs/reference/benchmark-cohort-procedure.md`** — it reuses the §0 Google Drive
> pause and §1 reset below.

> **These are API-cost steps — Joseph fires them himself** (see
> [[feedback_user_fires_api_cost_runs]]).

---

## 0. Pause Google Drive sync (REQUIRED — do this first)

`~/Obsidian` is a symlink to `…/Google Drive/Documents/Obsidian Vault/` — the test
vault **and its Kuzu graph (`KDB/graph`) live inside a Google-Drive-synced folder.**
A run writes binary Kuzu files and embeds frontmatter in-place; if Google Drive syncs
mid-write it can **corrupt the graph or notes** (the D35 binary-corruption hazard —
provider-agnostic; it was OneDrive until 2026-08, Google Drive since).

- **Pause it** via the Windows Google Drive tray icon → *Pause syncing*, or
  quit Google Drive entirely, before the reset/run.
- **Resume** only after the run completes and you've inspected the output.

## 1. Reset (wipe KDB outputs, keep config)

**Preferred (#138):** `kdb-orchestrate --wipe --vault-root <vault>` — a
dedicated wipe operation, decoupled from the run (the run has no modes). It
erases derived state (the `wiki/` tree, `graph/`, `state/manifest.json`, and
the `canonicalization/aliases.json` ledger), **archives `state/runs/` to
`state/pre-wipe-runs/<ts>/` first** (the #132 replay-journal audit trail
survives; replay/verify over the post-wipe replay root stays clean — #137),
appends one line to the wipe ledger `state/wipes.jsonl`, and exits. The
confirmation gate is unbypassable: it prints exactly what dies (paths, file
counts, the archive plan) and waits for a typed `yes` — there is no skip
flag; non-interactive stdin refuses. Then run the pipeline normally (§2) —
against the empty world every source is new. This is also the only mechanism
that removes cold-run-orphaned wiki files (no graph node ⇒ invisible to the
in-loop lifecycle — the #134 measurement).

The manual equivalent (also deletes `state/runs/` — use only when the journal
history should go too):

```bash
cd ~/Obsidian/Vault-in-place-test-run/KDB && rm -rf \
  graph graph-view.html wiki \
  state/runs state/pre-wipe-runs state/wipes.jsonl \
  state/manifest.json state/compile_result.json state/last_orchestrate.json
```

| Wiped | Kept |
|---|---|
| `graph`, `graph-view.html` | `state/pipelines.json` (pipeline `vault-test` config) |
| `wiki/` (articles/concepts/summaries) | `KDB-Compiler-System-Prompt.md` |
| `state/{runs,pre-wipe-runs,wipes.jsonl,manifest,compile_result,last_orchestrate}` | the source notes (`AIML/`, `Value Investing/`, …) |

The source notes are **not** touched — Pass-1 re-enrich strips and replaces
their frontmatter idempotently (enrich sends the LLM the frontmatter-stripped
body; the content hash is body-based), so already-enriched notes re-run clean.

A full wipe (vs `graphdb-kdb rebuild`) is the genuine end-to-end gate and **inits a
fresh graph at the current schema** — no rebuild, no schema-version mismatch.
**Do not `rm -rf KDB`** — that would delete `pipelines.json` and the system prompt.

## 2. Run

```bash
kdb-orchestrate \
  --pipeline vault-test \
  --vault-root ~/Obsidian/Vault-in-place-test-run
```
(Defaults `--provider deepseek --model deepseek-v4-flash` = what run-3 used.)

- **Model: the defaults work — no override needed.** The CLI defaults `deepseek` /
  `deepseek-v4-flash` are exactly what run-3 used (29 sources compiled, ~$0.14).
  The model's "dropped" note ([[project_deepseek_v4_flash_dropped]]) was a
  *benchmark*-candidate concern (no `response_format`); the orchestrator drives it
  via `json_mode` (the `1d668bf` Pass-2 fix), so it works here. Pass `--provider`/
  `--model` only if you deliberately want a different model.
- **Live progress streams to stdout by default** (Task #102): a `[n/total] ▸ source`
  header, `pass-1 enrich…` / `pass-2 compile…` with elapsed, running counts, inline
  `⚠` alarms. `--quiet` silences it; `--log-level {info,debug}` adds JSONL detail.
- **Pass-2 context is domain-scoped** (Task #103): each source's compile sees only
  same-domain existing entities.
- Optional `--limit N` caps how many signal sources compile (noise is free); the
  remainder is picked up next run.

## 3. Verify after the run

- **Summary:** `KDB/state/last_orchestrate.json` — `exit_code`, `exit_reason`,
  counts, and any `quarantined_sources` / alarm counts.
- **Event log:** `KDB/state/runs/<run_id>/orchestrator_events.jsonl` for the full
  per-event record.
- **Graph (optional):** build the viewer —
  `python3 tools/viewer/kdb_graph_viewer.py --graph-path ~/Obsidian/Vault-in-place-test-run/KDB/graph`
  — and open the HTML.

## 4. Resume Google Drive sync

Re-enable Google Drive syncing once the run is done and inspected.

---

**Run-4 = the 0.5.0 gate.** A clean run-4 (no run-fatal/invariant aborts; expected
scanned/compiled/noise counts; domain-scoped context confirmed) promotes 0.4.x →
**tag `v0.5.0`** + a `RELEASES.md` entry. See [[project_release_versioning_scheme]],
[[project_run3_next_sandbox_vault]].
