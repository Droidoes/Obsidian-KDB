# Session handoff — 2026-08-15

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime. Supersedes `archive/handoffs/session-handoff-2026-08-09.md` — everything still-open from that handoff is carried forward here.

## TL;DR

Joseph reorganized the vault folder tree (folders added/deleted/moved; **no file contents changed**). A read-only dry-run scan against the manifest proves the reorg is **fully absorbable**: 120 hash-matched MOVED ops, **zero DELETED, zero CHANGED** — nothing to fix, no migration. The true-up (manifest paths + graph Source-node rename) happens automatically on the next `kdb-orchestrate` run and has not run yet. Also shipped: `Stock Images/` added to the vault-in-place excludes. **#143 gmail-substack feeder: backlog fully converted.** Two live runs today — gate `--max 500` then remainder `--max 5000` — converted **4,156 messages with 0 failures** (18 dedup). `Substack_raw` label is drained (0 remaining); `Substack_ai_processed` = 4,213. Raw folder = 4,189 md files ≡ journal converted count. **Promo pre-filter then landed:** a deterministic 9-marker battery (`scripts/gmail_promo_prefilter.py`, tuned over 3 report iterations) moved **1,530 promo/truncated files (36.5%) to `_promo/`** (excluded from the pipeline), leaving **2,659 articles** for compile; pass-1 prompt broadened to name promo/truncated teasers noise. **#144 graph-viewer freeze: CLOSED same day** — precomputed layout (`1af3ff3`) + ledger row + Changelog (`17d375a`). Evening follow-ups: PendingLink ledger excluded from the viewer (investigation: all 434 pending targets are LLM-invented slugs existing nowhere in the vault — prompt violation, no code gate); **docs/ cleanup** (`d9a40fd`: 107 files archived, 5 drops deleted, refs rewritten). **Evening deliberation:** gmail corpus reframed as **info, not knowledge — search+rank, not classify+connect**; problem-statement refinement + panel brief is tomorrow's pickup (4 sharpening questions open). Remaining decisions (compile over the 2,659 vs raw-for-equity-repo; task closure) are **Joseph's call**.

---

## 1. Vault folder reorg — impact assessment (vault-in-place)

**What Joseph did:** added/deleted folders and moved folders around; files moved between folders; **contents untouched**.

**Assessment method:** read-only dry run — `scan_scope` (vault-in-place pipeline config) against the current manifest, nothing written. Manifest: 1,600 sources, all `vault-in-place`.

**Result:**

| Scan class | Count | Meaning |
|---|---|---|
| UNCHANGED | 1,480 | path + hash match |
| MOVED | 120 | hash-matched renames (Phase C, `ingestion/kdb_scan.py:276`) |
| NEW | 7 | never tracked (see below) |
| CHANGED | 0 | confirms contents untouched |
| DELETED | 0 | **no tracked source removed → zero erasure risk** |

**Why impact is minimal (by design):** moves are detected by SHA-256 content match, not path. MOVED reconcile updates the manifest path in place and, graph-side (`kdb_graph/intake.py:217` `_handle_source_moved`), transfers SUPPORTS edges to the new Source node and marks the old node `status='moved'` + `moved_to` breadcrumb. Entities / LINKS_TO / domains / wiki pages (slug-keyed) are all untouched. Pure moves do **not** recompile (hash == `last_compiled_hash` → `to_skip`). The destructive class would have been DELETED (erases sole-supported wiki pages, #130) — count is zero.

**Largest moved batches:** 28 `Value Investing/Monish Pabrai → Principles/Monish Pabrai`; 21 `Buffett Munger → Principles/`; 9 `PC-WSL-Ubuntu-Linux-Git/Obsidian-KDB → Projects/Obsidian-KDB`; 7 `Li Lu → Principles/`; 6 `MISC/Work → Projects/Work`; Equity Research folded under `Value Investing/`; `Food and Drinks → Seeking and Exploring/`. ⚠️ One to eyeball: 3 files `History/Medieval Eroupe → Seeking and Exploring/FuZlogicX LLC/Medieval Eroupe` — confirm intentional.

**7 NEW files** (will pass-1/pass-2 on next run; the daily note is force-noise): `Daily Notes/2026-08-09.md`; `History/History of China/{Sima_Qian_Records_of_the_Grand_Historian,大风歌}.md`; `PC-WSL-Ubuntu-Linux-Git/PC Troubleshooting/WIN-2026-001_BTD700_HDB630_Audio_Issue.md`; `Value Investing/Equity Research/E-comm/{alibaba-fundamental-analysis,alibaba-investment-thesis}.md`; `Value Investing/Equity Research/Mining/Barrick_IPO_Nem_Settlement_Notes.md`.

**Caveat on record:** MOVED matching is within-pipeline only (D-91-9). All moves stayed inside the vault-in-place tree, so all 120 matched. Moving files into `KDB/raw/` or an excluded folder would classify differently.

**Pending:** the true-up lands on the next `kdb-orchestrate` run (120 MOVED reconciles, no LLM cost; 6 NEW compiles, small spend). Nothing else to do.

## 2. `Stock Images/` excluded from vault-in-place scan

Joseph's request; graphDB is text-based. Folder holds 2,567 files (1,683 png / 884 jpeg), **zero .md** — so no behavioral change today (pipeline is `file_types: [".md"]`-only; nothing was ever scanned/hashed there). Value = walk-pruning + future-proofing (captions/.md landing there later, or widened file_types). Edit: `"Stock Images/"` appended to `excludes` in `<vault>/KDB/state/pipelines.d/vault-in-place.json`; registry loader verified, both pipelines load clean. Excludes match by directory **name** anywhere in the tree (same as existing entries). Effective next run.

## 3. #143 gmail-substack feeder — backlog fully converted (2026-08-15)

- **Backlog truth resolved**: `Substack_raw` held **4,174 messages** (paginated `list_message_ids` count — the API `resultSizeEstimate` of 201 was garbage; Gmail UI ~3,931 was close).
- **Two live runs today, both clean:**
  - Gate run `--max 500`: `converted 500 · dedup 0 · skipped 0 · failed 0`
  - Remainder run `--max 5000`: `converted 3656 · dedup 18 · skipped 0 · failed 0`
- **End state**: `Substack_raw` = 0 remaining (drained); `Substack_ai_processed` = 4,213 (33 pre-existing + 4,156 converted + 18 dedup + 6 prior). `KDB/raw/joseph-ft-public-gmail/` = **4,189 md files** ≡ journal `converted` count (4,189 of 4,207 records; 18 dedup). Throughput ~3 msg/s — the whole backlog took ~25 min, not hours.
- Known noise: a handful of transactional Substack mails (e.g. "Confirm your email") converted as `content_kind: article` with `source_url: null` — cosmetic, pass-1 can classify them out later.
- Vocabulary confirmed with Joseph: the feeder **converts** emails → md sources ("extraction" is the payload→parts sub-step). Frontmatter = 8-key metadata-only D2 block; pass-1 stays the single classification authority.
- **Promo pre-filter (landed 2026-08-15, Joseph's directive):** bulk of the corpus is promotional/paywalled, so noise gets marked *before* `kdb-orchestrate`. One-off `scripts/gmail_promo_prefilter.py` (report-only by default, `--apply` moves) with a 9-marker deterministic battery, tuned over 3 iterations with Joseph eyeballing samples:
  - paywalled teasers: `utm_source=paywall` checkout links (810), unlock-offer/`Claim my free post` (524), `free preview` (96), `Subscriber-only posts` (186), `Get full access` (44), `This post is for paid subscribers` (1) → 1,421 files
  - truncated-free (body cut, full text behind a jump link): `[Continue reading( for free)](substack.com/redirect/…)` (42), `… [Read more](substack.com/redirect/…)` ellipsis cue (67) → 109 files. Bare `[Read more]` without the ellipsis is the AI-news-roundup per-item format — deliberately NOT flagged.
  - transactional: `Confirm your email` (1)
  - **Result: 1,530 files (36.5%) → `_promo/`** (movelog `_promo/_movelog.jsonl`; `_promo/` added to `gmail-substack.json` excludes, loader verified) → **2,659 articles remain** for compile.
  - Key tuning findings: `Upgrade to paid` alone over-matches (header funding pitch on full free articles — stays a watch item); Substack digest/recommendation emails were already caught by strong markers; 15 residuals (11 AI-news roundups + 4 "X recommended Y") left for pass-1.
- **Pass-1 prompt broadened** (`ingestion/enrich/pass1_prompt.j2`): promotional teasers + truncated emails (paywalled or jump-linked) explicitly named `noise` — catches residuals the battery can't see. Ingestion suite 188 green.

- **Feeder promo-skip patch (landed 2026-08-15):** the tuned battery now lives in `ingestion/feeder/promo_filter.py` (`promo_markers()`), wired into `fetch()` between extract and dedup: promo messages journal `outcome: "promo"` (markers recorded, `filename: null`) and label-move to processed WITHOUT writing md. Promo wins over dedup; promo records never populate `seen_urls`, so a teaser can't block a later clean email with the same canonical URL. CLI summary gains `promo N`. 19 new tests; ingestion suite 207 green.

**Parked on Joseph (remaining):** (1) compile decision — `kdb-orchestrate --pipeline gmail-substack` over **2,659** articles (real LLM cost conversation now) vs leave raw for the equity-research repo; (2) closure — Milestone Changelog + TASKS.md #143 → Closed on his word.

## 4. #144 graph-viewer precomputed layout (2026-08-15)

- **Problem (Joseph's report):** opening `KDB/graph-view.html` hung the desktop 10-15 min — the template ran a live `d3.forceSimulation` (~300 ticks, collide×2) over 8,084 nodes / 26,790 edges on the browser main thread, recomputed on every open, never persisted.
- **Fix (Option A, Joseph's pick):** layout precomputed at build time — `tools/viewer/graph_layout.py`, a deterministic numpy/scipy port of the template's exact five d3 forces, baked into the HTML as per-node x/y (+ `layout` provenance block). Template is now static-mode: no `d3.forceSimulation` (pinned by test), drag moves nodes directly, filters/resize never re-layout. d3 many-body's Barnes-Hut is replaced by exact cKDTree local summation (same physics within distanceMax 280).
- **Debugging find of the day:** the first real-graph build exploded (positions ±1.4e13). Root cause: d3's link force is SEQUENTIAL (Gauss-Seidel — semi-implicit, stable for stiff coherent springs); a vectorized (Jacobi) update is unconditionally unstable past per-node stiffness ~5, which a coherent degree-18 cluster crosses. Fixed with a sequential link loop; real-graph layout converges in 60 s (x −519..2438, mean = canvas center). Star/clique synthetics do NOT reproduce (force-canceling geometries) — the regression pin is the real-graph range check.
- **Verification:** 9 layout tests + 2 template/builder pins green; full suite green. Joseph confirmed instant open + edges render.
- **CLOSED 2026-08-15** — code+tests `1af3ff3`; ledger row → Closed + Milestone Changelog entry `17d375a`.
- **Follow-ups (both caught by Joseph on visual inspection):**
  1. **Missing edges** — retiring the sim also retired d3.forceLink's side effect of mutating edge endpoint ID strings into node refs; first static build rendered nodes only. Template now resolves endpoints at load (`nodeById` map, pinned by test). Joseph confirmed: instant open, edges back.
  2. **PendingLink ledger rendering as nodes** — 722 placeholders, same purple as Source (unknown type → `--color-fallback` ≈ source purple). Digging in: all 434 distinct pending targets exist **nowhere** in the vault (0/434 .md basenames) — not uncompiled notes, but link targets the compile LLM **invented**, violating system-prompt §5 ("Do not link to slugs that do not exist anywhere"). No code gate enforces that rule: canonicalize remaps wikilinks but never validates targets; #136 intake pends unresolved by design. Ledger exposure was never a decision — `export()` sweeps all node tables via `show_tables()`. **Fix:** `SKIP_NODE_TABLES` gains `PendingLink` (bookkeeping ≠ knowledge; ledger stays in DB for drain-as-you-go, never renders) + fallback color purple→magenta. Rebuilt artifact: **7,362 nodes / 26,790 edges**, PendingLink gone.
- **Open thread (Joseph aware, unfiled):** canonicalize hard gate — strip wikilinks whose target is outside {response slugs ∪ EXISTING CONTEXT ∪ graph slugs}, count `links_stripped`; one-off repair of the 722 ledger rows + affected page bodies; 434 invented slugs double as a "wanted pages" signal if wanted.

## 5. Evening — PendingLink verdict, docs cleanup, gmail search-and-rank reframing

- **PendingLink verdict (Joseph's challenge: "everything is compiled — why 722 pendings?"):** queried the graph — 722 rows, **434 distinct target slugs, all from the 2026-08-07/08 compile runs, 0 targets existing as nodes, 0/434 matching any .md basename anywhere in the vault** (checked against all 12,305 vault markdown files). Conclusion: NOT uncompiled notes — the compile LLM **invented link targets**, violating system-prompt §5 ("Do not link to slugs that do not exist anywhere", `compiler/prompts/KDB-Compiler-System-Prompt.md:140`). No code gate enforces the rule: `canonicalize.py` remaps wikilinks but never validates targets; #136 intake pends unresolved by design. The ledger rendering in the viewer was never a decision — `export()` swept every node table via `show_tables()`. **Fix shipped in `1af3ff3`:** `SKIP_NODE_TABLES` gains `PendingLink` (ledger stays in DB for drain-as-you-go, never renders) + `--color-fallback` purple→magenta. **Unfiled open thread (Joseph aware):** canonicalize hard gate — strip wikilinks outside {response slugs ∪ EXISTING CONTEXT ∪ graph slugs}, count `links_stripped`; one-off repair of the 722 rows + affected page bodies; the 434 invented slugs double as a "wanted pages" signal.
- **Docs cleanup (`d9a40fd`):** 23 handoffs → `docs/archive/handoffs/` (Apr–May convention resumed; current handoff stays top-level); 84 superseded specs → `docs/superpowers/archive/specs/` (specs/ keeps 8 living docs: #123 spec+blueprint, #143 blueprint, #125 decision set); 5 drops deleted (Attention PDF 2.2 MB, M2-discussion file, 3 screenshots — Joseph's call); refs rewritten in 38 files incl. 2 `kdb_graph` code comments; suite green.
- **Gmail corpus reframing (Joseph, evening — the day's key architectural turn):** *"most of the articles are investment related and they are not necessarily related… more info than knowledge as in sources in vault-in-place… GraphDB is more for classifying and connecting… but I need to search and rank the info among the sources… we should refine our problem statement and propose to the panel."* The gmail/Substack corpus (2,659 articles, continuously growing) is **information, not knowledge** — it should NOT be processed through the knowledge pipeline unchanged. Joseph's need: **search and rank**, not classify and connect.
  - Deliberation so far: "list investment ideas" is **corpus-wide extraction/aggregation**, not retrieval — VectorDB alone structurally can't enumerate (top-k fuzzy recall); GraphDB alone is the wrong tool as-it-stands (built for knowledge compounding; 3 LLM calls/source). A dedicated extraction pass (LLM → structured idea records → JSONL/SQLite, SQL+LLM synthesis) was tabled as the only option that actually enumerates — matches #143's recorded downstream intent (separate equity-research layer).
  - **Joseph's call: don't rush — refine the problem statement, then brief the panel options-free** (#125 precedent: problem statement doubles as the panel brief).
  - **Four sharpening questions put to Joseph (UNANSWERED — tomorrow's starting point):** (1) primary job — standing idea ledger vs open-ended corpus Q&A vs incoming-flow triage (or ranked combination); (2) ranking criteria — recency / source reputation / cross-letter frequency / conviction language; (3) should ideas ever link into the vault knowledge graph, or is this corpus a deliberately separate world; (4) shelf life — does info decay with age or does history keep value (thesis evolution).
  - Planned artifact (not yet written): `docs/superpowers/specs/2026-08-16-gmail-info-search-rank-problem-statement.md`, then panel dispatch.

## 6. Carried forward from 2026-08-09 (still open, unchanged)

- ~~11 unpushed #143 commits~~ **RESOLVED 2026-08-15**: they were already on origin/main (2 more docs commits landed on top); today added `a2194b6` (promo pre-filter), `ffea7b8` + `d005ca0` (feeder promo-skip).
- **Docs sweep**: 8 stale `pipelines.json` mentions in `docs/reference/{graphdb-tutorial.html,test-run-procedure.md,orchestration-workflow.html}`.
- ~~Untracked `docs/Screenshot 2026-08-09 213341.png`~~ **RESOLVED 2026-08-15**: deleted in the docs/ cleanup (Joseph's call), along with the April screenshots, the Attention PDF, and the M2-discussion file; 23 handoffs → `archive/handoffs/`, 84 superseded specs → `superpowers/archive/specs/` (living docs kept: #123 spec+blueprint, #143 blueprint, #125 decision set); refs rewritten repo-wide (38 files).
- Polish residuals: mrdeepvalue `next=` URL recovery; Task-9 minors list in the ledger.
- **#139** open threads: first-use-case pick (Joseph leans agentic query-time traversal), Kuzu/LadybugDB dependency watch (pinned 0.11.3 still viable), temporal queries.
- **#140** pass-1.5 console stage (small, self-contained). **#141** VectorDB-vs-GraphDB evaluation. **#142** Kuzu FTS → GraphDB MCP.
- Candidate next work: second feeder (model-prompt archive).

## 7. Environment notes
- Vault = `/mnt/c/Users/fangq/Documents/Obsidian Vault` (`~/Obsidian` symlinks to it). gws auth healthy (12 scopes) this session.
- Suite verification quirk (still true): pytest 9.0.3 here prints no summary count — verify via exit code + grep FAILED/ERROR = 0.
- Gmail label IDs: Substack_raw = `Label_3904419182772066476`, Substack_ai_processed = `Label_5911144970725566262`.
