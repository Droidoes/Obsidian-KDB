# Benchmark KPI Enumeration — Candidate List

**Date:** 2026-06-05 · **Status:** 🟢 v0.2 — post-panel-review (5/5 reviewers folded)
**Version history:** v0.1 (sent to panel) → **v0.2** (this — reshaped after the 5-reviewer convergence; see §7 appendix for every finding's disposition).
**Companion:** `2026-06-03-benchmark-redesign-directions.md` (architecture + vocabulary — converged; read its `⭐ Convergence 2026-06-04` block).
**Reviews:** `2026-06-05-benchmark-kpi-review-{codex,deepseek,qwen,gemini,grok}.md`.

---

## 0. What this is

The complete proposed KPI list for the redesigned KDB benchmark, reshaped after external panel review. The benchmark is **GT-free**, runs the full sandbox corpus (36 sources) per model, and produces a cross-model **Borda** score over a small **scored** subset; everything else is **emitted as diagnostics** (measured every run, not in Borda).

- **Settled, do not re-open** (§6): GT-free, per-token normalization, Borda, two-family separation, run-vehicle/scoring-script architecture.
- **Next** (after this list): the anchors/weights + framework spec, then implementation. The framework has **blocking prerequisites** (§4) that must land before the scored robustness/latency KPIs are accurate.

**Purpose lock (2026-06-05):** model selection is settled on **cost** — `deepseek-v4-flash` wins on asymmetric per-run cost regardless. So this benchmark measures **quality only**: "among these models, which builds the best graph?" Cost is therefore a diagnostic (scoring it re-measures the settled axis). **Latency is scored** — with cost off the table it is the one live operational axis, and responsiveness is a real quality-of-use differentiator (caveat in §5).

---

## 1. Roles & families

- **Family:** *processing* (LLM call producing usable output; sources touched this run) vs *graph* (properties of the resulting Kuzu graph; full-corpus runs only). Never blended into one number.
- **Scope:** *per-run* (pass-agnostic, aggregated to one number) vs *pass-specific* (intrinsic to Pass-1 or Pass-2). All graph KPIs are per-run.
- **Role:** 🟢 **scored** (directional, enters Borda) · 🟡 **watched** (diagnostic now; promote to scored if the first multi-model run shows real spread) · ⚪ **diagnostic** (emitted for context, not promotable — non-directional or pipeline-deterministic).

The scored set is deliberately lean: a Borda-scored KPI must have a defensible GT-free direction *and* plausibly discriminate models. The panel's hard lesson (BELONGS_TO coverage, §7) — **verify variance before scoring** — is why the graph axis ships mostly as watched diagnostics that the first 3-model run promotes from.

---

## 2. The KPI list

### 2A. Processing — per-run
| KPI | role | dir | norm | definition / source |
|---|---|---|---|---|
| **quarantine_rate** | 🟢 | ↓ | per-1M-tok | sources failing all repair rungs + retries (`final_status='quarantined'`) / orchestrator quarantine events |
| **intervention_burden** | 🟢 | ↓ | per-1M-tok | graded composite — "how hard did the pipeline fight the model": rolls up retry + repair-rung + token-overrun into one scored signal (avoids over-counting one failure ladder as 3–4 ranks) |
| retry load | ⚪ | ↓ | ratio (cap) | `attempts > 1`; breakdown under intervention_burden |
| token-overrun rate | ⚪ | ↓ | per-1M-tok | `token_overrun` (`max_tokens`/`length`); breakdown |
| repair-rung usage | ⚪ | ↓ | per-1M-tok | `syntax_repaired ∨ slug_coerced`; breakdown (P2 today; P1 after #108) |
| cost | ⚪ | — | per source-word | $ to process input; per-token just re-derives price (settled axis) |
| latency | 🟢 | ↓ | per-1M-tok | throughput; **scored** per purpose lock — see §5 caveat |
| *pass / denominator split* | ⚪ | — | — | scanned/to_compile · P1-attempted · signal · noise · P2-attempted — **required** so the per-run aggregates and the signal/noise gate can't mask compile quality |

### 2B. Processing — pass-specific
| KPI | role | dir | note |
|---|---|---|---|
| signal/noise gate ratio (P1) | ⚪ | — | descriptive; only Pass-1 classifies; shifts which sources reach Pass-2 |
| semantic-pass rate (P2) | ⚪ | ↑ | **demoted.** Actual `semantic_ok` (`validate_source_response.py:58-93`) only checks source_name echo + summary-page integrity — NOT the coherence the v0.1 brief claimed. The real coherence checks (duplicate/reserved slug, `check_compiled_source`) are *hard gates* → already fold into quarantine. Nothing independent left to score. |
| entity_search_key_resolution_rate (P1) | 🟡 | ↑ | Pass-1 anchors resolving to active entities during context load; don't score (novel sources legitimately introduce unresolved concepts) |

### 2C. Graph — per-run (whole graph; full-corpus runs only)
| KPI | role | dir | norm | definition / source |
|---|---|---|---|---|
| **dangling_link_rate** (dangling-link) | 🟢 | ↓ | ratio | body `[[wikilinks]]` / emitted `outgoing_links` that resolve to no entity. **Hybrid compute**: emitted links from `compile_result.json` vs `queries.active_entity_slugs` — NOT from `LINKS_TO` (the ingestor silently drops dangling targets, `ingestor.py:316-337`, so graph-only would always read 0) |
| entity reuse / fragmentation | 🟡 | ↑ reuse | ratio | share of canonical non-summary entities supported by ≥2 sources; or SUPPORTS-per-canonical distribution. *The* central graph-quality axis once robustness is solved (codex) |
| graph connectivity | 🟡 | ↑ | ratio | largest connected-component ratio over LINKS_TO; topological coherence (qwen) |
| orphan / unsupported-entity rate | 🟡 | ↓ | per-1M-tok | from finalize artifacts (`orphans_marked`/`reaped`/`retracted`), NOT live graph (orphans are reaped pre-finalize → live read would false-zero). Def = canonical entities with zero SUPPORTS, not "no links" |
| BELONGS_TO coverage | ⚪ | ↑ | ratio | **demoted — dead.** ~100% by construction: every entity is SUPPORTED by a source, `domain` is a required Pass-1 enum, so coverage = (1 − domain-null rate) ≈ 1.0, near-zero variance |
| domain-null rate | ⚪ | ↓ | ratio | the part of domain that actually varies (signal sources whose `Source.domain` is null/empty) |
| link / SUPPORTS density | ⚪ | — | — | entity yield per source; non-directional |
| domain breadth (÷23) | ⚪ | — | ratio | how the model carves the corpus across the taxonomy; non-directional |
| alias / canonicalization metrics | ⚪ | — | — | ALIAS_OF rate, canon-invariant pass — **never scored**: canonicalization is deterministic + ledger-driven, so these reward ledger coverage / source mix, not model skill (codex) |

### 2D. Normalization summary (resolves fork 4)
- **per-1M-tokens:** quarantine, intervention_burden (+ token-overrun / repair-rung event counts), latency. Failures scale with volume processed.
- **ratio pass-through:** link_resolution, semantic-pass, BELONGS_TO coverage, retry load (bounded cap-fraction, per old `scorer.py:467-477`), connectivity, reuse — already 0–1.
- **per source-word:** cost.

---

## 3. Disposition of the old metrics (S0/M1–M7)
| Old | Verdict | Why |
|---|---|---|
| **S0** pipeline_success | reframe → `quarantine_rate` | post-#106 the gate chain is the repair ladder; outcome is `final_status` |
| **S1/S2/S3** parse/schema/hard-zero | fold → diagnostic breakdown of `final_status` | were weight-0 diagnostics |
| **M1** link target resolution | **migrate → graph** `dangling_link_rate` | reframed to dangling-link over the corpus entity set; rename to avoid false continuity with old per-response M1 |
| **M2 / M3** slug-pairing Jaccard | **kill** | declared concept/article lists are rebuilt from `pages[].page_type`; pairing findings are reconcilable measure-severity → no graded signal left |
| **M4** semantic_pass | demote → diagnostic | see §2B (narrow + hard-gated) |
| **M5** body-wikilink emit-set coverage | **kill** (rationale corrected) | declared emit-set coverage is the wrong quality target + redundant with `link_resolution`. *NOT* "wikilinks have no role" — `reconcile_body_links` does derive `outgoing_links` from body wikilinks (codex catch) |
| **M6 cost / M7 latency** | cost → diagnostic; **latency → scored** | purpose lock §0 (cost settled; latency is the live operational axis) |
| diagnostics: retry_load, token_overrun, pages_per_1k | retained as diagnostics | retry/overrun fold under intervention_burden; pages-per-1k = entity-yield context |

---

## 4. Framework prerequisites (blocking — not KPIs)
These must land before the scored robustness/latency KPIs are *accurate*:
1. **Aggregate discarded-attempt telemetry.** Pass-2 `compile_one()` overwrites `model_response` each attempt and persists only the winning attempt's tokens/latency (`compiler.py` + `common/llm_telemetry.py`). A model needing a 2nd full Pass-2 call has its discarded cost/latency *lost* → retry/cost/latency/intervention **undercount exactly the models that struggle**. Add `total_compile_calls`, total tokens/latency across attempts, `final_attempt_index`. *(codex, g-High)*
2. **Unified `PassCallMeasurement` record (P1 + P2).** Pass-1 already persists call telemetry in its sidecar (`enrich.py:139` — `input/output_tokens`, `latency_ms`, `attempts`); define one adapter shape over P1 sidecars + P2 `RespStatsRecord` so the KPI layer reads both. #108 later adds P1 repair-rung fields without redesign.
3. **Per-pass denominator metadata** in every record (so combined per-run aggregates are honest and noise-gating can't hide compile quality).

---

## 5. Forks — resolved + remaining
| Fork | Resolution |
|---|---|
| 1. Pass-1 telemetry / #108 | **(a) contract-first.** Telemetry already in the Pass-1 sidecar — read it now via the unified record (§4.2); #108 adds repair fields later. Do NOT block the benchmark on #108. |
| 2. Weights & graph/processing balance | Scored split is now 3-processing : 1-graph — **more** tilted. The fix is **not** weight inflation nor a forced weak 3rd graph KPI; it's **promotion-on-data**: the watched graph diagnostics (connectivity, reuse) get scored after the first multi-model run proves spread. Weights set in the next spec. |
| 3. Promotion criteria | Promote a watched diagnostic → scored if, on the first ≥3-model run, cross-model CoV exceeds a threshold **and** it's not redundant with an existing scored KPI (Spearman ρ low). Exact threshold set in the weights spec (candidates floated: CoV>0.15–0.25). |
| 4. Normalization | Resolved — see §2D. |
| 5. Scored graph too lean at two? | **Resolved: don't force a third now.** After demoting BELONGS_TO, scored graph = `link_resolution` only for v1; the rest are watched, promoted on evidence (codex + deepseek over qwen/gemini/grok's "add one now"). Honors the BELONGS_TO lesson. |
| **Latency caveat (new, for weights)** | latency↓ assumes faster = better, but a careful slow model may build a better graph. **Watch latency↔graph-quality correlation on run-1**; if the slowest model is the best builder, down-weight latency / treat as tiebreaker rather than letting it fight the quality signal. |

---

## 6. Settled — do NOT re-open
GT-free · per-token normalization (ratio pass-through for 0–1) · Borda for the cross-model score · two families kept separate · `kdb-orchestrate` emits per-run `measurements.json` (processing inline, graph via opt-in post-process); `tools/benchmark/` scores only · benchmark = full-corpus sandbox runs, latest run per model, no historical averaging.

---

## 7. Convergence appendix (n=5: codex · deepseek · qwen · gemini · grok)
Verdicts: **4× GO-WITH-CHANGES, 1× REWORK (gemini)**.

| Finding | Conv. | Verified | Disposition |
|---|---|---|---|
| link_resolution uncomputable from `LINKS_TO` (ingestor drops dangling) | **5/5** | ✅ code | scored, hybrid compute (§2C) |
| scored robustness cluster over-counts the same failure ladder | **5/5** | — | → `quarantine_rate` + composite `intervention_burden`; rest diagnostic (§2A) |
| Pass-1 contract-first (telemetry already in sidecar) | **5/5** | ✅ code | unified `PassCallMeasurement` (§4.2); fork 1 = (a) |
| BELONGS_TO coverage trivially ~100% → dead | 2/5 explicit | ✅ code | demoted to diagnostic; score domain-null rate (§2C) |
| semantic-pass narrow / redundant with quarantine | 2/5 | ✅ code | demoted (§2B) |
| don't force a 3rd scored graph KPI; promote on data | codex+deepseek | — | scored graph = link_resolution only; rest watched (fork 5) |
| alias/canon deterministic → never scored | codex (+qwen noted) | — | diagnostic only (§2C) |
| orphan def-drift + reaped pre-finalize → false-zero | grok+codex | — | diagnostic from finalize artifacts (§2C) |
| cross-pass denominator metadata needed | gemini+grok+codex | — | required (§4.3) |
| discarded-attempt telemetry undercount | codex (new) | — | blocking prerequisite (§4.1) |
| retry-load normalization = ratio not per-token | qwen+grok | matches scorer | ratio (§2D) |
| M2/M3/M5 kills correct (M5 rationale corrected) | 5/5 | ✅ code | §3 |
| Claim-layer blind spot | deepseek+gemini | empty in 0.5.3 | future family; noted, no KPI yet |

---

## 8. Summary count
🟢 **4 scored:** quarantine_rate · intervention_burden · dangling_link_rate · latency
🟡 **4 watched** (promote on run-1): entity reuse/fragmentation · graph connectivity · orphan/unsupported rate · entity_search_key_resolution
⚪ **~10 diagnostic:** retry · token-overrun · repair-rung · cost · signal/noise · semantic-pass · BELONGS_TO coverage · domain-null · density · domain-breadth · alias/canon
**Killed:** M2 · M3 · M5
**Prerequisites:** discarded-attempt telemetry · unified PassCallMeasurement · per-pass denominators
