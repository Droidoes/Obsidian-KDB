# Phase B Migration — Panel Code-Review Prompt

> Sent **verbatim** to all 5 CLI reviewers (Codex · Deepseek · Qwen · Gemini · Grok). Only `<OUTPUT_FILE>` differs per reviewer (e.g. `docs/superpowers/specs/2026-06-02-phase-b-review-codex.md`). Repo root: `/home/ftu/Droidoes/Obsidian-KDB`; the branch `refactor/phase-b-package-split` is checked out.

---

You are a senior staff engineer doing a **correctness + quality code review of a completed refactor**. This is **NOT a design review** — the architecture was already ratified by a 5-panel review (unanimous GO). Your job is to scrutinize the **execution**: did the migration preserve behavior, and is it clean? Be skeptical, specific, and cite `file:line`. Finding a real defect the automated gates missed is the whole point.

## HARD GUARDRAIL — read first, non-negotiable
- **Read-only.** Do NOT modify, create, rename, or delete ANY file in the repository **except** the single output file named at the end (`<OUTPUT_FILE>`). Write your entire review there and nowhere else.
- Do NOT run any git command that changes state (no `add`/`commit`/`checkout`/`switch`/`stash`/`restore`/`reset`/`rebase`). Do NOT run `pip install`, formatters, linters-with-autofix, or anything that writes to the tree.
- You MAY read files and run **read-only** commands: `git diff`, `git log`, `git show`, `grep`/`rg`, `cat`, `ls`, `sed -n`.
- If you run tests, use EXACTLY `python3 -m pytest -q -m "not live" <paths>`. **NEVER** run a bare `pytest` or `-m live`: the repo's `.env` auto-loads real API keys and live tests cost real money. (You generally don't need to run tests — they already pass; focus on what tests can't catch.)

## What was done (Phase B)
The flat package `kdb_compiler/` (plus top-level `graphdb_kdb/` and `kdb_benchmark/`) was split into **six peer top-level packages**, **leaf-first**, **move-don't-rewrite** (git-mv + import-rewrites only; no logic rewrites):

| Package | Holds (notable) |
|---|---|
| `common/` (leaf) | atomic_io · call_model(+_retry) · run_context · types · source_io · paths · config/(settings) · **llm_telemetry** (generic half split from resp_stats_writer) · `__version__` |
| `ingestion/` | kdb_scan · enrich/ · config/ (pipeline_registry + vocab data domains.json/source_types.json/scope-config.yaml) |
| `compiler/` | compiler · prompt_builder · response_normalizer · repair · canonicalize · page_writer · validate_compile_result · validate_source_response · context_loader · **resp_summary** (build_parsed_summary, split from resp_stats_writer) · schemas/ |
| `kdb_graph/` | was `graphdb_kdb/` (pure package rename; the **`graphdb-kdb` CLI name is unchanged**) |
| `orchestrator/` | kdb_orchestrate · orchestrator_events · manifest_writer |
| `tools/` | cleanup (was kdb_clean) · replay (was response_replay) · benchmark/ (was kdb_benchmark) · diagnostics/ (validate_last_scan + last_scan.schema.json) · viewer/ |

**Dependency contract (B.3), guard-tested** in `tools/tests/test_package_boundaries.py`: `common`→∅ · `kdb_graph`→`common` · `ingestion`→`common` · `compiler`→`common`+`kdb_graph` · `orchestrator`→all · `tools`→{`common`,`kdb_graph`,`ingestion`,`compiler`}. Nothing depends on `tools` **except** the documented `orchestrator→tools.cleanup` inline-cleanup edge (decoupling deliberately deferred as a behavior change out of move-only scope).

**The one real restructure — `resp_stats_writer` split:** generic telemetry → `common/llm_telemetry`; compiler-specific `build_parsed_summary` → `compiler/resp_summary`. `build_resp_stats` previously called `build_parsed_summary` internally; that call was **lifted** up to `compiler/compiler.py`'s call site (so `common` stays a leaf and never imports `compiler`).

## Already-passed verification (so spend your effort ELSEWHERE)
- **1191 non-live tests pass** (was 1175; +16 new guard/split/render/gate tests; verified dual-mode that none were lost).
- The **dependency-contract guard** asserts the actual import graph ≡ B.3.
- All **9 CLI entry points** resolve; vocab/schema/template data files load.
- **run-7** (live E2E) clean: `exit_reason=ok`, graph 193 Entity / 29 Source / 10 Domain / 195 BELONGS_TO / 202 SUPPORTS / 468 LINKS_TO — matching the run-6/v0.5.1 standard.

## Hunt where the automated gates are weakest
1. **Behavior drift hidden in a "move".** For any migrated module, `git diff main..refactor/phase-b-package-split -- <file>` should show a rename (~R100) plus import-line edits only. Flag any logic change, reordered statement, altered default, or dropped branch sneaking in under a "move".
2. **The resp_stats split.** Is `common/llm_telemetry` truly a leaf (no `compiler`/`ingestion`/`orchestrator`/`tools` import, including under `TYPE_CHECKING`)? Is the lifted `parsed_summary` gate in `compiler/compiler.py` **byte-identical in condition** to the old internal gate (`parse_ok and isinstance(parsed_json, dict)`)? Any telemetry field/value now subtly different (hashes, capture-full behavior, stop_reason, token fields)?
3. **Vacuous / false-green tests.** Two were already found and fixed (a `parsed_summary` default-arg test; the D34 producer-agnostic guard that still named the removed `kdb_compiler`). **Are there OTHERS?** — guard/assert tests still checking for the removed names `kdb_compiler`/`graphdb_kdb` as string literals, or tests that now pass trivially because what they checked no longer exists.
4. **Data-file / path resolution that only bites at real runtime.** Schema paths (`compiler/schemas/*`, `tools/diagnostics/last_scan.schema.json`), vocab paths (`ingestion/config/*`), the `pass1_prompt.j2` Jinja template (FileSystemLoader), `tools/benchmark/models.json` + its `REPO_ROOT` depth. Note: `pip install -e .` does **not** exercise `[tool.setuptools.package-data]` globs — are those globs actually correct/complete for a real (non-editable) wheel build, or would a wheel ship missing data files?
5. **Packaging.** `pyproject` `[project.scripts]` targets, `[tool.setuptools.packages.find]` include/exclude, `package-data`, `[tool.pytest.ini_options].testpaths` — anything stale, missing, or now-dead (e.g. a leftover `kdb_compiler` package-data line).
6. **Import hygiene.** Leftover `kdb_compiler`/`graphdb_kdb` references in code, comments, or docstrings; any circular-import risk the split introduced; grouped `from kdb_compiler import (...)` lines split correctly across their new packages.
7. **The `orchestrator→tools.cleanup` exception.** Is deferring the decoupling acceptable, or does it signal a deeper layering problem worth fixing now?
8. **Anything the 1191-test suite structurally cannot catch** — your judgment.

## Where to look
- Diff: `git -C /home/ftu/Droidoes/Obsidian-KDB log --oneline main..refactor/phase-b-package-split` then `git diff main..refactor/phase-b-package-split`.
- Intent: `docs/superpowers/specs/2026-06-01-codebase-realignment-panel-brief.md` (§B) and the plan `docs/superpowers/plans/2026-06-02-phase-b-package-split.md`.

## Output — write ONLY to `<OUTPUT_FILE>`
1. **Verdict:** `GO` / `GO-WITH-FIXES` / `NO-GO`.
2. **Findings**, each as: `[Severity: Critical | High | Medium | Low]` · `file:line` · what's wrong · why it matters · suggested fix. Be concrete and verifiable — no vague "consider reviewing X".
3. Group findings under: **(a) correctness bugs**, **(b) test-fidelity gaps** (vacuous/false-green/lost coverage), **(c) packaging & data-file risks**, **(d) cleanliness/naming nits**. If a group is empty, say "none found" — do not pad.
4. One-paragraph **bottom line**: is this safe to merge + tag `v0.5.2`, and what (if anything) must be fixed first.
