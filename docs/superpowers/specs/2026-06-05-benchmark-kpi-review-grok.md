# Benchmark KPI Enumeration — Panel Review (Grok)

**Reviewer:** Grok · **Date:** 2026-06-05  
**Artifact reviewed:** `docs/superpowers/specs/2026-06-05-benchmark-kpi-enumeration-brief.md`  
**Code baseline:** `main` @ v0.5.3 (read-only verification)

---

## 1. Verdict

**GO-WITH-CHANGES**

The seven-KPI skeleton (four per-run robustness + semantic-pass + two graph signals) is the right shape for a GT-free Borda benchmark, and the M2/M3/M5 kills are mostly justified. Before anchors/weights, fix: (1) link-resolution **measurement source** (cannot be inferred from `LINKS_TO` alone), (2) semantic-pass **definition drift** vs production telemetry, (3) orphan **definition drift** vs Phase-4 code, (4) Pass-1 telemetry contract, and (5) decide explicitly on a **third graph KPI** vs graph up-weighting only.

---

## 2. Findings

### (a) Scored-vs-diagnostic & directionality

| Severity | Cite | Flaw | Why it matters | Suggested change |
|---|---|---|---|---|
| **High** | Brief §2B semantic-pass vs `compiler/validate_source_response.py:58-97` + `compiler/compiler.py:388-391` | Brief defines semantic-pass as duplicate slugs, reserved slugs, summary typing, internal references (`check_compiled_source` family). Production `semantic_ok` uses **`semantic_check` only** (source_name echo, summary_slug ∈ pages, exactly one summary page). Hard-zero types (`duplicate_slug`, `reserved_slug`, …) are enforced in **`check_compiled_source`** (`validate_compile_result.py:85-90`) — used by old **S0** (`scorer.py:178`), **not** by `semantic_ok`. | Scoring `semantic_ok` will **not** measure what the brief claims. Models can diverge on duplicate/reserved slugs without moving this KPI; conversely the KPI moves on benign echo typos. Borda ranks the wrong axis. | **Re-classify or re-spec:** Either (A) narrow the brief definition to match `semantic_check`, or (B) add a scored Pass-2 KPI computed from `check_compiled_source_findings` on final `parsed_json` (post-reconcile), and demote narrow `semantic_ok` to diagnostic. Prefer (B) if “content coherence” is the intent. |
| **Medium** | Brief §2C orphan rate vs `kdb_graph/ingestor.py:649-676` | Brief: orphans = entities with **no incoming/outgoing links**. Code: `orphan_candidate` = canonical entities with **zero SUPPORTS** (LINKS_TO may still exist). | Watched diagnostic will disagree with graph queries/orchestrator semantics; promotion decisions based on wrong definition. | Fix definition to **“canonical entities with zero SUPPORTS edges”**; align `orphan_entities` query docs in the measurement spec. |
| **Medium** | Brief §2A repair-rung ↓ vs ladder narrative | Repair-rung usage is scored **↓** (less repair = better). That is directionally sound, but **coexists** with quarantine ↓ — a source can be `repaired` without quarantine, so both move together on the robustness ladder. | Not wrong alone, but amplifies robustness weight (see §b). | Keep scored, but document that repair-rung is the **graded middle** of the ladder; consider emitting `final_status` histogram as diagnostic. |
| **Low** | Brief §2B signal/noise ⚪ | Correctly non-directional. | — | None. |
| **Low** | Brief §2C domain breadth / density ⚪ | Correctly non-directional (yield / carving). | — | None. |
| **Medium** | Brief §2C BELONGS_TO ↑ vs `ingestor.py:500-501,512-516` | Direction “more entities in domains = better” is defensible, but BELONGS_TO is **derived from Pass-1 `Source.domain` + SUPPORTS**, not per-entity LLM domain emission. | A model with good Pass-2 linking but weak Pass-1 `domain` will score low — **cross-pass coupling** is real but should be explicit in the brief (not purely “graph skill”). | Keep scored; add diagnostic **Pass-1 domain-null rate** on signal sources. Optionally split “graph” vs “provenance” in weights later. |
| **Low** | Diagnostic under-use | Old **S3** hard-zero pass rate (`scorer.py:309-318`) had a defensible ↓ direction and is **folded away** without a replacement scored signal. | Residual quality signal (pre-reconcile pairing/slug integrity) is only indirectly visible via quarantine. | Add **hard-zero / gate-failure rate** as diagnostic (or fold into expanded semantic-pass per High finding above). |

### (b) Double-counting / redundancy

| Severity | Cite | Flaw | Why it matters | Suggested change |
|---|---|---|---|---|
| **High** | Brief §2A (4 scored robustness) + §2B semantic-pass | **Robustness cluster:** quarantine, retry load, repair-rung, token-overrun share variance (overrun → retry → repair → quarantine). Old engine kept retry/overrun as **weight-0** (`scorer.py:467-486`). Promoting **all four** to scored while graph has **two** risks ~71% of Borda ranks coming from correlated processing stress. | A model that retries often looks bad on 3–4 KPIs for one underlying behavior; graph quality underrepresented unless weights are extreme. | **Pick two scored robustness KPIs** (recommend: **quarantine rate** + **repair-rung usage**); keep retry load + token-overrun as diagnostics. Or keep four but cap combined robustness weight in fork-2. |
| **Medium** | semantic-pass vs `final_status` (`compiler.py:480-491`) | `semantic_ok=False` often coincides with `final_status=quarantined` or repair flags; after #106, second attempt can clear semantic before `clean`. | Partial double-count with quarantine/repair-rung — not identical (semantic can fail then coerce). | Acceptable if semantic-pass is re-specified to `check_compiled_source`; else demote to diagnostic when robustness quartet stays scored. |
| **Low** | link-resolution vs orphan (brief §2C rationale) | Brief correctly avoids scoring both. | — | None. |

### (c) Kills & M1 migration

| Severity | Cite | Flaw | Why it matters | Suggested change |
|---|---|---|---|---|
| **High** | M1 migration §2C / §3 vs `kdb_graph/ingestor.py:316-337` | Companion directions say dangling links over **`LINKS_TO`**; ingestor **silently skips** edges when target Entity missing (`CREATE` requires both endpoints). **Dangling body links leave no trace in the graph.** | Measuring dangling rate from `links_to_edges` alone yields **0** always — false “perfect” models. | **M1 migration is right at graph family, wrong on data source.** Compute from **compiled bodies** (all `body_wikilink_slugs` in committed `compile_result` / vault) vs `active_entity_slugs(conn)` — not from `LINKS_TO` edge list. Brief §2C definition (body wikilinks / total) is correct; fix the “Data source” column and align with `2026-06-03-benchmark-redesign-directions.md` line 30. |
| **Medium** | M1 old `scorer.py:221-255` vs new definition | Old M1: **`outgoing_links`** resolved within **same-response** entity slug union. New: body wikilinks vs **corpus-wide** entity set. Post-`reconcile_body_links` (`repair.py:242-265`) outgoing_links = body links anyway — but **cross-source** targets are the meaningful upgrade. | Not a blocker, but **not comparable** to historical M1; document generational break. | Proceed; name KPI `body_dangling_link_rate` in spec to avoid false continuity with old M1. |
| **Low** | M2/M3 kill §3 vs `validate_compile_result.py:180-230`, `repair.py:268-275` | Pairing commission/omission still exist pre-reconcile but **`reconcile_slug_lists` pages-wins** removes them before commit. | Jaccard on declared↔emitted pairs **post-reconcile** ≈ tautology. Kill is correct for **scored**. | Optional diagnostic: **pre-reconcile pairing delta** from measure findings if persisted — not scored. |
| **Low** | M5 kill §3 vs `repair.py:242-265` | M5 rewarded body links covering declared slug lists. After body-wins reconciliation, **vanity vs graph** argument holds for declared-set coverage. | Kill correct. Residual cross-page integration signal is absorbed by **link-resolution** (corpus entity set). | None. |

### (d) Graph-set completeness

| Severity | Cite | Flaw | Why it matters | Suggested change |
|---|---|---|---|---|
| **Medium** | Brief §4 fork 5 (two graph KPIs) | Two sharp signals are defensible, but **`kdb_graph/verifier.py:463-480`** already defines **GT-free canonicalization invariants** (ALIAS_OF completeness, flat aliases, LINKS_TO→canonical targets). | Third axis: **alias/canonical hygiene** — directional (↑ fewer invariant violations), model-discriminating, not correlated with link-resolution or BELONGS_TO. | Add scored or watched diagnostic **`canonicalization_invariant_pass_rate`** (entities or checks passing C1–C4 / total checks). Promote if multi-model spread. |
| **Low** | ALIAS_OF / `queries.py:344-400` | No scored measure of alias resolution quality for `entity_search_keys` / merge behavior. | Blind spot for Task #74-era graph. | Diagnostic only unless spread shown. |
| **Low** | Claim layer empty (`schema.py:13-17`) | Brief silent on Claim nodes — correct for now. | Future KPI family. | Note in blind-spot appendix. |

### (e) Classification & normalization

| Severity | Cite | Flaw | Why it matters | Suggested change |
|---|---|---|---|---|
| **High** | §2A per-run aggregate vs Pass denominators (`orchestrator/kdb_orchestrate.py:659-671`) | Pass-1 processes **all scanned** sources; Pass-2 only **`pass1_gate_signal`**. Aggregating quarantine/retry/repair/token **per 1M tokens across passes** requires a defined token pool: sum(P1 tokens on scanned + P2 tokens on signal) with events tagged by pass. | Naïve sum can **dilute** P1 failures with P2-only tokens or double-count sources that appear in both pools. | Spec measurement as **`Σ pass_events / Σ pass_tokens`** with per-pass breakdown diagnostic; do not average pass-level rates. |
| **Medium** | §4 fork 4: retry load “per-token” | **Retry load** is inherently a **bounded ratio** (`scorer.py:467-477`: Σ min(attempts−1, MAX) / (|R|×MAX)). Tagging it per-1M-tokens is dimensionally odd. | Distorts cross-model comparison if forced into token denominator. | **Ratio pass-through** for retry load (and token-overrun if defined as \|{overrun}\|/\|R\|); per-token only for quarantine count and repair-rung **event counts**. |
| **Low** | link-resolution & BELONGS_TO | Both are natural **ratios** in [0,1]. | — | Confirm ratio pass-through in anchors spec; no per-token. |
| **Medium** | semantic-pass scope | Pass-2-only denominator = signal sources only. | Correct scope; must not use all-scanned denominator. | Lock denominator in spec. |

### (f) Pass-1 / #108 coupling

| Severity | Cite | Flaw | Why it matters | Suggested change |
|---|---|---|---|---|
| **High** | §4 fork 1 vs `pass1_caller.py:24-33,101-110` | `Pass1CallResult` carries `attempts`/tokens/`latency_ms` but **nothing persists** to `llm_resp/` (only Pass-2 uses `RespStatsRecord` — `common/llm_telemetry.py:196`). P1 quarantine only via `orchestrator_events.jsonl` (`kdb_orchestrate.py:610-611`). | Until #108, **3 of 4 robustness KPIs are Pass-2-only** while brief implies P1+P2. Cross-model P1 comparison is broken. | **Fork 1: (a) contract now** — define `Pass1StatsRecord` path mirroring `RespStatsRecord`; scorer consumes when present. Do not block KPI list on #108 implementation. |
| **Medium** | Pass-1 quality | Beyond signal/noise, no scored Pass-1 content KPI. | Arguably correct GT-free — domain/summary quality lacks monotone direction. | Optional diagnostics: **domain enum validity rate**, **entity_search_keys count distribution** (non-scored). |
| **Low** | #108 repair ladder | Pass-1 has retry but no `syntax_repaired`/`slug_coerced` yet. | repair-rung P1 component = 0 until shipped. | Document P1=0 baseline in first benchmark run notes. |

### (g) Blind spots / omissions

| Severity | Cite | Flaw | Why it matters | Suggested change |
|---|---|---|---|---|
| **Medium** | S0 fold §3 vs `scorer.py:164-189` | Old **S0** = parse ∧ schema ∧ **no hard-zero** — stricter than quarantine rate alone. | Sources failing hard-zero may be quarantined without a distinct scored signal (see semantic-pass drift). | See (a): add gate-failure diagnostic or expanded coherence KPI. |
| **Medium** | Cross-run stability | Brief § corpus = latest run only (settled §5). | Intentional — not a blind spot for v1. | None. |
| **Low** | Summary / entity merge quality | No KPI for summary page body quality or erroneous entity merges. | Hard to make GT-free + directional. | Defer; graph + coherence proxies suffice for v1. |
| **Low** | `pages_per_1k_source_words` (`scorer.py:1002-1021`) | Old diagnostic dropped from new list. | Useful yield context. | Keep as optional graph-adjacent diagnostic (entity yield). |

---

## 3. Open forks — panel read

| Fork | Recommendation |
|---|---|
| **1. Pass-1 telemetry (#108)** | **(a) Contract now:** spec `Pass1StatsRecord` + file layout; implement #108/retry persistence on its own track. KPI framework must read P1+P2 with pass-tagged breakdown. |
| **2. Weights vs graph/processing balance** | Do **not** rely on weight alone to fix 5:2 scored count with robustness correlation. **Reduce scored processing to 3** (quarantine, repair-rung, semantic-pass/coherence) and **either** add 3rd graph KPI **or** weight graph 2× processing per KPI in Borda. Prefer **third graph KPI** (canonicalization) over extreme weights. |
| **3. Promotion criteria** | Principled rule: promote watched diagnostic → scored if **CoV > 0.15** across ≥3 models on first sandbox run **and** Spearman ρ < 0.7 vs each existing scored KPI. orphan rate is the first candidate. |
| **4. Normalization** | Ratios: link-resolution, BELONGS_TO, semantic-pass/coherence, retry load, token-overrun (if \|overrun\|/\|R\|). Per-token: quarantine count, repair-rung **events** (numerator events, denominator run tokens). |
| **5. Two graph KPIs enough?** | **Not quite — add a third or demote robustness.** Two is enough only if processing scored set is trimmed; otherwise graph is underrepresented in rank dimensions. Best third: **canonicalization invariant pass rate** (verifier-backed). |

---

## 4. Bottom line

The KPI list is **sound enough to proceed** to anchors/weights **after** a short spec patch: fix link-resolution to read **bodies vs entity set** (not `LINKS_TO`), align semantic-pass with **actual or expanded** validation, fix orphan definition, contract Pass-1 stats, and resolve the **robustness quartet vs two graph scores** imbalance.

**Position on “scored graph set too lean at two”:** **Yes, it is too lean given five correlated processing scores** — not because link-resolution or BELONGS_TO are weak, but because Borda counts **KPIs**, not intuitions. Recommend **three graph scored KPIs** (add canonicalization invariant pass rate) **and** **three processing scored KPIs** (quarantine, repair-rung, content-coherence gate), with retry/overrun/cost/latency/signal-noise/orphan/density as diagnostics. Weighting alone cannot substitute for missing graph dimensions when processing supplies five rankable axes.