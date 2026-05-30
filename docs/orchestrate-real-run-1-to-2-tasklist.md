# Orchestrator: Real-Run-1 → Real-Run-2 Task List

> **✅ ARC CLOSED 2026-05-30.** Run-2 fired; analyzed; Pass-2 `json_mode` fix
> shipped (`1d668bf`). Gating items A/B/C done, D moot (graph-setup verified
> clean — code only creates the parent; Kuzu makes the store), F (#98) deferred.
> Next work tracked under **run-3** (see Re-run gate at the bottom). E (#97
> viewer) is non-gating and still open. This doc is now historical.

**Objective:** complete every gating item below before firing **real-run-2**.

**Context.** Real-run-1 (2026-05-29, `deepseek-v4-flash`, test sandbox) processed
**20 of 36 sources** (15 compiled + 5 noise, 79 wiki pages, valid partial graph)
then **fail-fasted** on source #21 (`Life-Health-Wellbeing/How Not to Age.md`)
when the model emitted a null `override.llm_original`. The run surfaced two
classes of problem — a **wrong Pass-1 contract** and a **brittle failure policy**
— plus several smaller fixes. This list gates the next real fire.

> Live runs are ⚡ — fired by Joseph (per ledger convention).

---

> **Methodology lock (Joseph, 2026-05-29):** the invalid-result *handling policy*
> (all-or-nothing vs. per-field repair) is **DATA-GATED** — not decidable in the
> abstract. Sequence: **A (review prompt/schema together) → F (build + run the
> Pass-1 benchmark across all models; observe HOW models fail + HOW OFTEN each
> way) → THEN the handling-policy decision** (the #95/#96 invalid-result rules).
> Per [[feedback_concrete_first_extract_later]]. Three things done *together*
> with Joseph; assistant does not pre-commit a principle.
>
> **Empirical update (2026-05-29 night):** audit of the 20 real-run-1 responses
> (one model, deepseek-v4-flash) shows it was **20/20 clean** on the code-owned
> fields (`override.llm_original`==`kdb_signal`, `schema_version`==1,
> `model_to_be_filled` literal, `prompt_version`==1.1.0). The override null on
> source #21 was an **outlier we cannot inspect** (body discarded — see #96).
> Two consequences: (1) the #95 contract fix is justified by **fragility/tail-risk**,
> NOT "model can't comply"; (2) **Joseph re-confirmed F (benchmark) stays a GATE**
> (2026-05-29 night) — n=20/one-model is too thin to set the handling policy on;
> the cross-model failure-rate data is required. **Panel review of the prompt +
> the 20 responses is the immediate next step** (full 5-model; our own findings
> withheld for independent convergence).

## A — [#95 ✅ DONE 2026-05-30] Pass-1 prompt/schema contract review (TOGETHER)  **(GATING — do first)**

> **CLOSED 2026-05-30.** Filed as Task #95 (done in `docs/TASKS.md`). Two-stage
> validation shipped (`validate_llm_content` Stage 1 + `validate_envelope` Stage 2);
> 4 code-owned fields dropped from the prompt; `build_override_block` single producer;
> arrow→prose boundaries (DeepSeek #4); prompt 1.1.0→1.2.0. 754 passed/1 live-skip.
> The *handling-policy* half (per-field repair) remains DATA-GATED on F (#98).


**Root finding (systemic, not a one-off).** Code-owned metadata fields leak into
the LLM's output contract: `model`, `prompt_version`, `schema_version`,
`override`. `pass1_caller.py:65-66` stamps only `prompt_version` + `model` before
validating; `schema_version` + `override` are trusted from the model. `override`
broke real-run-1; `schema_version` is the same latent bug. `build_json_schema()`
is **validation-only — never sent to the model** (the contract is the prompt text;
`json_mode=True` is a soft hint, not enforcement).

- [ ] **Review prompt + schema together, field by field** (`pass1_prompt.j2` +
      `pass1_schema.py`). For each field: who should own it (LLM-content vs
      code-stamped) + what "invalid" looks like for it.
- [ ] **Contract correction (mechanical part, low-controversy):** stop asking the
      LLM for code-owned fields (`override`/`llm_original`, `schema_version`,
      and the already-stamped `model`/`prompt_version`).
- [ ] **Validation placement** — Joseph [4] open: a dedicated pre-post-processing
      `pass1_validation` boundary vs. keeping it in post-processing. **Decide
      AFTER the review + benchmark data.** Either way: log + assert.
- [ ] **Per-field handling rules** (the all-or-nothing question) — **DEFERRED to
      after F** (benchmark failure data drives it).
- [ ] Review rigor TBD (systemic contract → external-panel candidate).

## B — [#96 BLUEPRINTED 2026-05-30] Orchestrator error-handling architecture  **(GATING)**

Joseph: circuit-breaker is *downstream* of severity — design the foundation first.

- [x] **Severity taxonomy** for every failure point (`debug`/`info`/`warning`/
      `source_quarantine`/`run_fatal`/`invariant_violation`). [B1]
- [x] **Comprehensive structured logging** at each failure point (assert-grade
      `OrchestratorEvent` JSONL + always-on typed invariant checks). [B1-B4,B7]
- [x] **Alarm / summary surface** — failures visible, not silent (`last_orchestrate.json`
      counts + CLI quarantine alarm). [B5]
- [~] **Circuit-breaker policy derived from severities** — **DEFERRED 2026-05-30**
      (C3): attended runs + `--limit N` cap blast radius; thresholds need a measured
      baseline. Revisit on first real multi-source run or unattended scheduling.
- [x] Subsumes the observability fix: **persist the raw model response on
      failure** (Pass-1 sidecar + Pass-2 resp_stats + `raw_response_unavailable`). [B6]
- [x] **Architecture path selected:** B then C — structured observability first,
      quarantine-and-continue second. Blueprint:
      `docs/archive/tasks/task96-orchestrator-error-handling-blueprint.md`.
- [x] **Implementation plan drafted:**
      `docs/superpowers/plans/2026-05-30-task96-orchestrator-error-handling.md`.

## C — [#94] Resilience redesign: quarantine-and-continue  **(GATING)**

Replaces fail-fast (D-91-8). One bad source must not kill the batch.

- [x] A failed source (enrich OR compile) is logged + quarantined; the loop
      **continues**. Finalize runs over everything that succeeded.
- [x] **Dissolves #94 stranding** — finalize always runs → `wire_links` always
      runs over the committed set → no orphaned `LINKS_TO`.
- [x] Depends on **B** (severity decides skip-vs-abort). [C1 uses B's severity model]
- [x] Revises ratified D-91-8 → recorded as **D-96-1**: source-local failures
      (`source_quarantine`) no longer abort; the loop continues and finalize runs
      over the committed set. `run_fatal` + `invariant_violation` still abort —
      D-91-8 fail-fast is *narrowed to run-fatal scope*, not removed.

## D — Graph-setup fix  **(GATING, small — fold into #91)**

- [ ] Don't pre-create the graph as a directory; Kuzu creates the DB **file**
      itself (this version: single file, not a folder).
- [ ] Fix the stale `graphdb.py:39` comment ("Kuzu creates the directory itself").
- [ ] Setup scaffolding creates only the parent.

---

## D.1 — [propose #99] Orchestrator `--limit N` (batch-size cap)  *(small, gating-adjacent)*

Joseph 2026-05-29: a source repo of 1000 files should be processable 50 at a
time. The orchestrator's strength is that it can **stop anywhere** (per-source
commits) — expose that.

- [ ] `--limit N`: process at most N to-compile sources this run, then stop
      cleanly (finalize over what was done; remainder picked up next run).
- [ ] Interacts with #94 quarantine-and-continue + finalize-always-runs: the
      limit is a clean stop, not an abort — `wire_links` still runs over the
      committed batch.
- [ ] Decide: does `--limit` count enriched sources, compiled sources, or all
      scanned? (lean: to-compile sources actually processed.)

## E — [propose #97] GraphDB viewer — multi-model bake-off  *(parallel, non-gating)*

- [x] Opus version built + renamed → `tools/kdb_graph_viewer-opus.py`
      (read-only Kuzu dump → self-contained Cytoscape.js HTML).
- [ ] **Co-author a distributable spec/prompt** (Joseph + assistant) to hand to
      other models for their own versions. Requirement: **D3.js force-directed**
      rendering. CLI-reviewer guardrail applies if any model has FS access.
- [ ] Generate competing versions; compare; pick the best.
- [ ] Promote winner to a `kdb-graph-view` CLI; commit.

## A.1 — [✅ DONE 2026-05-30] Panel review of the Pass-1 prompt + real responses  **(sub-step of A)**

- [x] Full 5-model panel (Codex + Deepseek + Qwen + Grok + Gemini) reviewed the
      rendered prompt + 20 real responses + `pass1_schema.py`. Outputs +
      synthesis at `docs/task95-pass1-review/`.
- [x] **Findings withheld** for independent convergence; combined at synthesis.
      C-1 (4 code-owned fields) 5/5 CRITICAL; C-2 (no full JSON exemplar) 5/5;
      C-3 (`software`-over-`ai-ml`) 5/5; C-4 (`entity_search_keys` over-production) 4/5.
- [x] CLI-reviewer no-repo-mod guardrail honored; one output file per reviewer.

## F — [#98 DEFERRED 2026-05-30] Pass-1 benchmark (NW-5 revival)  **(NO LONGER GATING)**

> **DEFERRED 2026-05-30 (Joseph).** Stay on `deepseek-v4-flash:direct` as the
> standing Pass-1 model; no benchmark gate, no API-cost runs until revived. This
> **un-gates real-run-2** — the benchmark is no longer a precondition. Knock-on:
> the #95 handling-policy half (per-field repair vs all-or-nothing), which was
> DATA-GATED on this benchmark, also stays deferred → current two-stage
> all-or-nothing validation stands. Trigger to revive: appetite to compare models,
> or a concrete quality complaint on Pass-1 output. Filed as Task #98 (deferred)
> in `docs/TASKS.md`. Original scope notes retained below for revival.

**Scope: DECIDE AFTER PANEL (Joseph 2026-05-29 night).** What re-confirmed this
as the gate was a *classification-quality* lean (`software` vs `ai-ml` on
Claude/Obsidian content), NOT a failure — deepseek was 20/20 clean. Whether the
benchmark leads with classification-quality vs robustness vs both is **held until
the panel feedback lands** (their findings on classification may sharpen what's
worth measuring). Candidate axes to choose among:

- classification quality (model agreement / vs Joseph labels on `domain`,
  `source_type`, `kdb_signal` — surfaces the `software`-over-`ai-ml` class)
- `entity_search_keys` quality (the T2 consumer)
- robustness (invalid/unparseable rate per model — the override-null class; rare)
- [ ] Ground-truth labeled set (real-run-1 corpus + outputs as a seed); pass bar.
- [ ] ⚡ Model runs are API-cost → Joseph fires.
- [ ] **Output feeds the #95/#96 handling-policy decision.**

---

## Re-run gate

- [x] G — nuked the test graph before run-2 (do NOT resume onto it).
- [x] H — ⚡ **real-run-2 fired 2026-05-30** (`deepseek-v4-flash`, sandbox
      `~/Obsidian/Vault-in-place-test-run`). **Did NOT complete** — see below.
- [x] I — push gate cleared; all commits pushed (remote `main` = `1d668bf`).

### Run-2 result + analysis (2026-05-30) — ARC CLOSED, → run-3

Run `2026-05-30T11-14-35_EDT`: scanned 36, enriched 11, **compiled 9**, noise 1,
**failed 1** → `exit_code=1`, fail-fast at **Pass-2 compile** of the largest
source (`Canonical Ontology for Financial Reports GPT5.2`, 95 KB / 11.3k words).

**Root cause** (`state/llm_resp/.../*.b4f2171a.json`): deepseek emitted
structurally-invalid JSON — `JSONDecodeError "Expecting ',' delimiter" @ char
7296`. **Not truncation** (`stop_reason=stop`, `token_overrun=false`),
`attempts=1`. The compile call free-formed JSON while **Pass-1, on the same
model, already requests `json_mode=True`** and never hit this class.

**Fix shipped** (`1d668bf`): `json_mode=True` on the Pass-2 `ModelRequest`
(`compiler.py`) → provider constrains output to valid JSON. TDD test
`test_compile_source_requests_json_mode`. **Parse-retry deliberately NOT added**
— across both sandbox runs every source was `attempts=1`, and the one observed
retry (Pass-1 `How_Not_to_Age`, 2 attempts) did not recover; no evidence a retry
is warranted ([[data-before-principle]], [[feedback_no_imaginary_risk]]).

**Also note:** #96 (shipped after run-2) now turns this Pass-2 failure from a
batch-killer into a single-source **quarantine** (`error_compile`) and captures
the raw corrupt response (B6) — so run-3 completes even if a source still fails.

**This `real-run-1 → real-run-2` arc is CLOSED.** Next: **run-3** as the clean
diagnostic run (json_mode on + #96 quarantine/observability) — Joseph fires.

## Dependencies

```
A (review together) ──► F (benchmark: how/how-often models fail)
                              │
                              ▼
                     handling-policy decision (the #95/#96 invalid-result rules)
                              │
                              ▼
                     #95 contract fix  ──►  B (#96 error-handling) ──► C (#94 quarantine)

D (graph-setup fix), E (viewer bake-off)  parallel (independent)
G nuke graph after A–D green;  H ⚡ real-run-2 after G;  I push gate
```

**Note:** the *mechanical* contract correction in A (stop asking LLM for
code-owned fields) is low-controversy and can land early; the *handling-policy*
half waits for F's failure data.
