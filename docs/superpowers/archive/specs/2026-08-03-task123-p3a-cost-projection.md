# Task #123 P3a.0 — Pre-run cost projection: Pass-1.5 selector seat

**Date:** 2026-08-03 · **Blueprint:** `2026-08-03-task123-p3a-blueprint-v0.3.md` §4.7 / §8 (P3a.0 row) · **Spec:** `2026-07-25-task123-semantic-graph-search-spec.md` (R4, D3, D5, D9, D-123-A…H)
**Script:** `scripts/task123_p3a_cost_projection.py` (read-only; `.venv/bin/python scripts/task123_p3a_cost_projection.py`) · **Paid LLM calls made:** 0

Purpose: R-P3a-5 leaves the Pass-1.5 selector seat open between `deepseek-v4-flash`
($0.14/$0.28 per 1M) and `qwen3.7-flash` ($0.03/$0.13 per 1M). Blueprint §4.7
requires a measured projection **before** the seat is chosen. Every number below
comes from the corpus (sandbox vault + its Kuzu graph), the repo constants, the
D5 calibration artifact, and `common/models.json`.

## 1. Cost model

Per compiled source, one semantic graph search runs in two stages (spec R4):

- **THIN:** the model sees one rendered line per entity of the **entire eligible
  identity space N** for that source — `render_thin_line` (`kdb_search/projection.py:108`:
  `- slug: …  title: …  type: …`) — and picks candidate slugs. M (=150) is the
  retention ceiling, **not** the input ceiling (D-123-A).
- **FAT:** the stage-2 pool (thin's validated retention, capped by M and by the
  0.8-budget fill, D-123-B/D) of **whole bodies** — read via
  `common/wiki_io.get_body`, the same read the production `body_reader` will do.

Terminal branches accounted separately (not two paid calls per source):

- **Empty eligible space → `abstain_empty_space`, zero calls.** This includes a
  **missing Pass-1 domain**: `kdb_search/contracts.py:109-110` — "Missing pass-1
  domain lands here with `domain_missing`, **never a silent whole-graph
  fallback**." (The P3a.0 task brief's "sources without Pass-1 domain metadata
  search the whole active graph" is **contradicted by the code**; the projection
  follows the code.)
- **Thin retains zero candidates → thin-only, no fat call** (D3, applies at
  every N since D-123-G removed `small_space`).

**Graph growth across compile order.** N per source is a function of compile
order (`intra_run_order` exists for this reason), so the current-graph
measurement is **not** multiplied by the source count. Per domain d with n_d
sources and net contribution r entities/source: source j of the domain searches
N_j = r·(j−1) (its own ~5.6 supported entities are created *by* its compile, so
the `source_supported_slugs` subtraction is ≈ 0 for a first compile). The
per-domain run total is r·n_d·(n_d−1)/2 — **independent of interleaving** under
linear growth, so no assumption about the compile interleave is needed.

**Fat pool bound.** `fat_input_byte_allowance` for both seats (1M ctx × 0.8 −
26,000 fat output reserve) × 4 B/token = **3,096,000 B** ≈ 4,536 mean bodies ≫
M=150 — the stage-2 pool is **M-bound, never budget-bound** at these windows.

## 2. Measured inputs

Corpus: sandbox vault `~/Obsidian/Vault-in-place-test-run` + its graph
(`KDB/graph`, opened `GraphDB(..., read_only=True)` — the Task #112 read-only
path; no lock, no migration, no writes). The production graph
(`~/Obsidian/KDB/graph`) is **empty (0 entities)** — verified; the sandbox graph
is the only live measurement corpus. All 166 bodies were read (no sampling
needed; 0 missing).

| input | value | source |
|---|---|---|
| active entities | **166** | sandbox graph |
| compiled sources in graph | **31** | sandbox graph |
| net entities / compiled source | **5.35** | 166 / 31 (measured dedup) |
| raw SUPPORTS / source (authored) | **5.58** (median 6, max 12) | sandbox graph |
| domain entity counts | value-investing 54, software 35, ai-ml 27, health-wellbeing 22, geopolitics 6, quotes 6, math 5, psychology 5, personal-finance 3, history 3 | sandbox graph |
| domain source counts (shares used) | VI 10, SW 7, AI 5, HW 3, six domains × 1 | sandbox graph `Source.domain` |
| **thin line, mean rendered bytes** (+`\n`) | **88.4 B** | `render_thin_line` over all 166 (spec §7.1 measured 88 B — matches) |
| **fat block, mean rendered bytes** (+`\n`) | **682.5 B** | `render_fat_block` + `get_body` over all 166 (spec §7.1 measured 691 B — matches) |
| slug mean bytes | 25.2 B | graph |
| query block, mean rendered bytes | **1,222 B** | `render_query_block` per graph Source with its real summary (mean 424 B)/domain/author + synthesized 5×40 B themes, 8×50 B keys (graph stores no themes/keys — stated) |
| system + template | 4,096 B | `SYSTEM_TEMPLATE_BUDGET_BYTES` (golden-pinned bound) |
| **D5 thin bytes/token** | **deepseek-v4-flash 3.7632 · qwen3.7-flash 3.7911** | `benchmark/truth/task123_search_calibration_v1.json` (provider-reported usage, 16,863 B thin fixture block) |
| fat bytes/token | **4 (estimator)** both seats | D5 measured the thin block only — no fat family exists; `ESTIMATOR_BYTES_PER_TOKEN` used, stated |
| output allowances | visible THIN 20,000 / FAT 10,000; provider caps 36,000 / 26,000 | `kdb_search/constants.py` (D9) |
| run output cap | 65,536 | blueprint §4.8 registry edit (both seats) |
| pricing (USD per **1M** tokens) | deepseek 0.14/0.28 · qwen 0.03/0.13 | `common/models.json`; unit verified `common/llm_telemetry.py:180` |

**Source counts (measured, not assumed):**

- **Sandbox gate run target: 32 signal sources** (36 `.md` on disk outside
  `KDB/`, minus 4 `Daily Notes` force-noise). The P3a.0 brief's "~1,586
  expected" does **not** hold for the sandbox — the sandbox is a 31-compiled-source
  in-place test vault; 1,586 is the production-ingestion scale.
- **Production vault: 1,672 eligible sources** (`.md`, excluding `KDB/`,
  hidden dirs, `Daily Notes/` + `Projects/` force-noise per
  `ingestion/config/scope-config.yaml`, and the nested sandbox copy). The spec
  cites 1,586 (blueprint §5.1) / ~1,706 (spec §7.1) — the measured 1,672 sits
  between them and is what the projection uses.

## 3. Scenarios and their assumptions

Growth rate = net entities contributed per compiled source, applied along
compile order:

- **LOWER — high overlap:** r = **2.7** (≈ 50% of authored entities already in
  graph at scale). Measured today: 5.58 authored vs 5.35 net (4% dedup, early
  compile order). 50% at scale is an **assumption** — nothing yet measures
  steady-state overlap; chosen as the plausible floor. Branch rates (cost-minimal
  direction): 5% empty-space abstain, 5% thin-only.
- **EXPECTED — measured dedup:** r = **5.35** (166/31, the measured rate).
  Branch rates: 2% / 2% (never fired live; assumptions).
- **UPPER — low overlap:** r = **5.58** (raw authored mean — near-zero dedup,
  near-linear growth to the final entity count). Branch rates: 0% / 0%
  (cost-maximal direction).

Output per search (per the P3a.0 method note — allowance for EXPECTED, cap
reasoning for UPPER):

- **LOWER** — wire-derived: thin = M × (slug 25.2 B + 9 B JSON) ÷ 3.76 ≈ 1,366
  tokens; fat = 50 × (25.2 + 40) ÷ 4 ≈ 815 tokens.
- **EXPECTED** — the spec's visible output allowances: 20,000 + 10,000 =
  **30,000 tokens/search**. This is deliberately generous (the exact max
  serializations are 18,464 B / 8,404 B; real responses will be far smaller) —
  it is the ratified allowance, not a measurement.
- **UPPER** — the provider caps actually sent as `max_tokens`: 36,000 + 26,000
  = **62,000 tokens/search**, both stages. This is why the §4.8 run cap of
  65,536 suffices: the worst-case billed completion for one source's two calls
  (62,000) sits under it. Hidden reasoning tokens: both seats declare
  `thinking: disabled`, so hidden output ≈ 0 in practice; the 16,000
  `HIDDEN_OUTPUT_RESERVE` is pre-flight reservation, not expected spend.

Other assumptions, stated once: 1 attempt per stage (retry amplification is
bounded at 2× per stage by `MAX_ATTEMPTS_PER_STAGE`); thin retains
`min(N, M)` (recall-oriented prompt; no live retention measurement exists —
this maximizes fat input, i.e. conservative for cost); sources are assigned to
domains at the measured source-domain shares; no Pass-1 noise skips beyond
force-noise (Pass-1 may judge additional sources noise — every such skip only
lowers cost).

## 4. Projection table — vault scale (1,672 sources, production ingestion)

Branch accounting columns: **exec** = searches making ≥1 call, **thin-only** =
thin call but no fat call (D3), **abstain** = empty space, zero calls.

| scenario | seat | exec / thin-only / abstain | thin input tok | fat input tok | output tok | **run cost (USD)** |
|---|---|---|---|---|---|---|
| LOWER | deepseek-v4-flash | 1588 / 79 / 84 | 19,747,544 | 35,894,096 | 3,398,853 | **$8.74** |
| LOWER | qwen3.7-flash | 1588 / 79 / 84 | 19,602,215 | 35,894,096 | 3,398,853 | **$2.11** |
| EXPECTED | deepseek-v4-flash | 1639 / 33 / 33 | 36,810,191 | 40,472,770 | 48,829,088 | **$24.49** |
| EXPECTED | qwen3.7-flash | 1639 / 33 / 33 | 36,539,293 | 40,472,770 | 48,829,088 | **$8.66** |
| UPPER | deepseek-v4-flash | 1672 / 0 / 0 | 38,291,100 | 41,446,298 | 103,664,000 | **$40.19** |
| UPPER | qwen3.7-flash | 1672 / 0 / 0 | 38,009,303 | 41,446,298 | 103,664,000 | **$15.86** |

Cross-check against the spec's own cost-on-record (§7.1, M=100 era): full
re-ingest ≈ 143M expected input ⇒ ~$20 deepseek. This projection lands at 77M
input + 49M output ⇒ $24.49 — the input is lower because the compile-order
ramp (Σ r·n²/2, not final-N × sources) halves the thin exposure, and the total
is higher because output is now priced. Same order; method difference
explained.

## 5. Sandbox gate run (32 sources — `scripts/sandbox-run.sh` target)

| scenario | seat | exec / thin-only / abstain | thin input tok | fat input tok | output tok | **run cost (USD)** |
|---|---|---|---|---|---|---|
| LOWER | deepseek-v4-flash | 30 / 2 / 2 | 50,596 | 77,661 | 65,049 | **$0.04** |
| LOWER | qwen3.7-flash | 30 / 2 / 2 | 50,224 | 77,661 | 65,049 | **$0.01** |
| EXPECTED | deepseek-v4-flash | 31 / 1 / 1 | 55,869 | 117,820 | 934,528 | **$0.29** |
| EXPECTED | qwen3.7-flash | 31 / 1 / 1 | 55,458 | 117,820 | 934,528 | **$0.13** |
| UPPER | deepseek-v4-flash | 32 / 0 / 0 | 56,326 | 123,564 | 1,984,000 | **$0.58** |
| UPPER | qwen3.7-flash | 32 / 0 / 0 | 55,912 | 123,564 | 1,984,000 | **$0.26** |

## 6. Read for the seat choice (R-P3a-5)

- Absolute Pass-1.5 spend is small at every scale: **$2–$40 for the full vault
  ingestion**, **< $0.60 for the sandbox gate run**, even at the UPPER scenario
  whose output term is the provider cap rather than any expected value.
- The price ratio is stable across scenarios: **qwen3.7-flash ≈ 2.4–4.1×
  cheaper** (EXPECTED: $8.66 vs $24.49, 2.8×; the ratio narrows when output
  dominates because qwen's output discount is 2.2× vs its input discount 4.7×).
- Token density is a wash (D5 thin: 3.7911 vs 3.7632 B/token — qwen tokenizes
  the thin block 0.7% denser; nothing measured separates them on fat prose).
- **Conclusion:** cost does not constrain the seat — both seats are affordable
  at vault scale with two orders of magnitude of headroom against any
  reasonable run budget. The seat should be decided on **selector quality**
  (the D7 truth-set gates), with cost as a tiebreaker leaning qwen3.7-flash
  (~3× cheaper at EXPECTED). If the quality read is neutral, qwen3.7-flash is
  the cost-rational seat.

## Appendix — script output (verbatim, 2026-08-03)

```text
==============================================================================
MEASURED INPUTS (sandbox vault + graph, read-only)
==============================================================================
graph active entities            : 166
graph compiled sources           : 31
net entities / compiled source   : 5.35
raw SUPPORTS / source (authored) : 5.58
domain entity counts             : {'psychology': 5, 'history': 3, 'health-wellbeing': 22, 'math-statistics-logic': 5, 'personal-finance': 3, 'geopolitics': 6, 'ai-ml': 27, 'quotes': 6, 'value-investing': 54, 'software': 35}
domain source counts             : {'ai-ml': 5, 'software': 7, 'math-statistics-logic': 1, 'health-wellbeing': 3, 'psychology': 1, 'geopolitics': 1, 'quotes': 1, 'history': 1, 'value-investing': 10, 'personal-finance': 1}
thin line mean bytes (+newline)  : 88.4
fat block mean bytes (+newline)  : 682.5
slug mean bytes                  : 25.2
query block mean bytes (see note): 1222
bodies missing (graph/disk drift): 0
sandbox signal sources (.md)     : 32
production eligible sources (.md): 1672
D5 thin bytes/token              : {'deepseek-v4-flash': 3.7632, 'qwen3.7-flash': 3.7911}
fat bytes/token (estimator, both): 4

==============================================================================
VAULT SCALE (production ingestion): 1672 sources
==============================================================================
scenario  model              exec/thin1/abst       thin_in       fat_in          out   cost_usd
-----------------------------------------------------------------------------------------------
LOWER     deepseek-v4-flash  1588/79/84         19,747,544   35,894,096    3,398,853       8.74
LOWER     qwen3.7-flash      1588/79/84         19,602,215   35,894,096    3,398,853       2.11
EXPECTED  deepseek-v4-flash  1639/33/33         36,810,191   40,472,770   48,829,088      24.49
EXPECTED  qwen3.7-flash      1639/33/33         36,539,293   40,472,770   48,829,088       8.66
UPPER     deepseek-v4-flash  1672/0/0           38,291,100   41,446,298  103,664,000      40.19
UPPER     qwen3.7-flash      1672/0/0           38,009,303   41,446,298  103,664,000      15.86

==============================================================================
SANDBOX GATE RUN: 32 sources
==============================================================================
scenario  model              exec/thin1/abst       thin_in       fat_in          out   cost_usd
-----------------------------------------------------------------------------------------------
LOWER     deepseek-v4-flash  30/2/2                 50,596       77,661       65,049       0.04
LOWER     qwen3.7-flash      30/2/2                 50,224       77,661       65,049       0.01
EXPECTED  deepseek-v4-flash  31/1/1                 55,869      117,820      934,528       0.29
EXPECTED  qwen3.7-flash      31/1/1                 55,458      117,820      934,528       0.13
UPPER     deepseek-v4-flash  32/0/0                 56,326      123,564    1,984,000       0.58
UPPER     qwen3.7-flash      32/0/0                 55,912      123,564    1,984,000       0.26

fat allowance bytes per seat (0.8 budget less fat output reserve):
  deepseek-v4-flash     3,096,000 B (~4,536 mean bodies >> M=150 — pool is M-bound, not budget-bound)
  qwen3.7-flash         3,096,000 B (~4,536 mean bodies >> M=150 — pool is M-bound, not budget-bound)
```
