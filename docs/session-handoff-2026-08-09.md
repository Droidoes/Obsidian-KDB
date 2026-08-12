# Session handoff — 2026-08-09

> Richest single catch-up artifact for the next session. Top-level so `session-catchup` finds it by mtime.

## TL;DR

Three threads shipped today: **#139 maiden-graph analytics gate PASSED**, **#141/#142 filed** (VectorDB-vs-GraphDB evaluation; Kuzu FTS → GraphDB MCP), a **docs/reference true-up**, and the big one — **#143 Gmail/Substack ingestion pipeline: blueprint ratified, fully implemented, live-gated, and in production** (33 sources converted, zero failures). #143 is NOT closed: backlog + compile decisions are parked on Joseph. 11 commits unpushed.

---

## 1. #143 — Gmail/Substack ingestion pipeline (the day's bulk)

**What it is:** the project's first *feeder* — deterministic conversion of external info → KDB sources. Vocabulary on record (Joseph): **ingestion pipeline** = feeder (external → source files); **compile pipeline** = scan → pass-1/1.5/2 → commit. First instance: Substack financial-subscription emails in `joseph.ft.public@gmail.com` (label `Substack_raw` → `Substack_ai_processed`). Pattern intended to repeat (model-prompt archive feeder is next in line).

**Blueprint v0.1 (ratified):** `docs/superpowers/specs/2026-08-09-task143-gmail-ingestion-pipeline-blueprint-v0.1.md`; plan `docs/superpowers/plans/2026-08-09-task143-gmail-ingestion-pipeline.md`. Key decisions D1–D9: D1 deterministic code module (no LLM, no ad-hoc); D2 metadata-only frontmatter (pass-1 stays the single classification authority — no domain/source_type in feeder output); D3 Gmail state = label move (self-draining queue; the only Gmail write); D4 append-only conversion journal `KDB/state/feeders/gmail.jsonl` (audit + dedup-by-canonical-URL); D5 sources → `KDB/raw/joseph-ft-public-gmail/` (first `"raw"`-type pipeline root); D6 registry migrated `pipelines.json` → `pipelines.d/<id>.json` (plugin model; `vault-in-place` id unchanged); D7 video/podcast emails degrade gracefully (`content_kind`); D8 slice-first backlog (--max 5 → 25 → review gate) via `gws gmail` CLI; D9 one task covers registry + feeder.

**Downstream intent (recorded, out of scope):** a **separate equity-research repo** will consume these sources for investment-idea extraction/ledgers/follow-up. Joseph was explicit: KDB stores the sources; the ledger/idea work does not belong in this repo.

**Shipped (Tasks 1–9, all complete):** pipelines.d loader (`ingestion/config/pipeline_registry.py`) → prod vault registry migration → `GmailClient` gws subprocess seam → `gmail_extract` (payload→source parts) → conversion journal → `fetch()` flow (extract→dedup→write→label-move→journal, fail-forward) → `kdb-gmail-fetch` entry point → docs. Whole-branch final review found one bug family via real-payload probe (footer filter gutting bodies, open.substack.com canonical misses, `content_kind` CSS false-positives) — fixed in a review-gated wave. Task 9 live gate ran slice-first with Joseph.

**Live-gate findings + fixes (commit `65952e1`):**
1. **Empty-grid bodies** (Joseph's screenshot `docs/Screenshot 2026-08-09 213341.png`): markdownify converted Substack nested *layout* tables verbatim → whole article trapped in one md-table cell. Fix: `_detable()` — bs4 renames `table/thead/tbody/tfoot/tr/td/th` → `div` pre-markdownify. `beautifulsoup4>=4.12` now an explicit dep.
2. **Custom-domain publications missed `source_url`** (The Bulwark = `www.thebulwark.com/p/...`): `_SUBSTACK_ANY_POST_RE` any-host `/p/` fallback added as canonical candidate (d) LAST; precise substack.com candidates still win.

**Joseph's decisive ruling (do NOT reopen):** email extraction over URL crawling — paid subscriptions carry FULL text in email; anonymous crawl gets paywalled teasers only, which would degrade exactly the investment-idea sources this pipeline exists for. Crawling stays a possible later fallback (video transcripts). Footer truncate-at-first-marker and fail-forward write→label-move→journal order remain as designed.

**Production state right now:**
- `KDB/raw/joseph-ft-public-gmail/` = **33 sources** (5 slice + 3 arrivals from re-conversion + 25 batch), journal = **33 records** (match); all 33 emails label-moved to `Substack_ai_processed`.
- `--max 25` batch: converted 25 · dedup 0 · skipped 0 · **failed 0**. All tbl=0, bodies 3.1–40KB.
- 22/25 newest carry real canonical URLs (incl. both custom-domain Bulwark pieces + `open.substack.com/pub/...` old-format).
- 3 genuine `source_url: null`s, each verified by decoding bodies + `redirect/2` JWTs: live-video announcement (no `/p/` anywhere); alibaba/hellochinatech (only disable_email/signup JWTs); mrdeepvalue investing-performance (URL exists 3 layers deep — JWT→subscribe link→`next=` param; recoverable with a ~15-line candidate, logged as **polish residual**, not gate-blocking).

**Parked on Joseph (#143 stays OPEN until these fire):**
1. **Backlog**: his Gmail UI shows ~3,931 in Substack_raw vs API `resultSizeEstimate` ~201 — unresolved which is real; confirm before chunked `--max 100` runs.
2. **Compile**: `kdb-orchestrate --pipeline gmail-substack` (pass-1/1.5/2 on the 33) vs leave raw for the equity-research repo.
3. **Closure**: Milestone Changelog + TASKS.md #143 → Closed on his word.

**Open residuals:** `docs/reference/{graphdb-tutorial.html,test-run-procedure.md,orchestration-workflow.html}` still carry **8 stale `pipelines.json` mentions** (baba252 swept code-side only) — small unscheduled docs sweep. Task-9 minors list lives in the ledger for a possible polish pass (incl. the mrdeepvalue `next=` URL recovery).

## 2. #139 thread 2 — maiden-graph analytics gate PASSED

Ran the free analytics on the maiden graph as the gate for the belief layer: **737/12,826 cross-community edges** (vs the sandbox's degenerate 2/486), **562 interpretable communities**, **35 single-bridge pairs**. Record: Part 5 of `docs/2026-08-07-graphdb-utilization-and-kuzu-landscape.md`; commit `e9d165b`. Joseph viewed the graph HTML (noted surprise at bitcoin/crypto cluster prominence — worth a look when picking the first use case). #139 stays open: threads (1) first-use-case pick (Joseph leans **agentic query-time traversal**), (3) Kuzu dependency watch, (4) temporal queries.

## 3. Kuzu / LadybugDB — now load-bearing (filed under #139 thread 3)

KuzuDB was archived 2025-10 after the Apple acquisition; we run pinned **0.11.3** (last line). **LadybugDB** = the community continuation: Cypher-compatible fork, actively developed through 2026; GitNexus + sdl-mcp already migrated via a compat seam. Joseph's 2026-08-07 "noted fact, no action" ruling is **superseded (2026-08-08/09)**: the two planned ingestion pipelines turn the graph into a long-lived, continuously growing production dependency. Options on the table: (a) **stay on pinned Kuzu with trigger-based re-evaluation** — still very viable right now (my read, shared with Joseph: the DB is local, schema is ours, `graphdb-kdb rebuild` regenerates from journals; nothing is broken); (b) LadybugDB evaluation spike before the pipeline build-out; (c) re-platform off embedded Kuzu-lineage entirely. Discussion task is #139 — no decision demanded yet.

## 4. #141 + #142 filed — retrieval stack thinking-work

- **#141 VectorDB-vs-GraphDB retrieval evaluation** (full record `docs/2026-08-09-vectordb-vs-graphdb-retrieval.md`; commit `a36d77f`): does a vector index earn a place beside the graph. Open threads: enumerate Joseph's real query classes (the deciding artifact); FTS-before-vectors; minimal local-embedding spike if warranted; sequence after #139's use-case pick.
- **#142 Kuzu FTS extension → GraphDB MCP** (commit `60147cd`): Joseph's decision on record — "overall we want to achieve FTS capability, and specifically implement the FTS extension as part of the GraphDB MCP." Two-track split: Kuzu-extension leg = #142; general body-content leg stays in #141. D4 basis: FTS is infrastructure, never relevance authority, never pass-1.5 machinery. Design constraints recorded: MCP read path stays read-only (index lifecycle outside), version-pinning against archived Kuzu 0.11.3 (intersects #139 watch), Kuzu FTS only indexes in-graph strings.

## 5. Docs true-up + #140 reminder

- `docs/reference/orchestration-workflow.htm` + `docs/reference/graphdb-tutorial.html` trued-up to the post-#123/#130/#136 implementation; graphdb-tutorial gained an **MCP capability section (§10)**. Commit `b14c0e5` — **pushed** (Joseph approved).
- **#140** (filed): pass-1.5 stage in the run-log console — the console contract (#102) renders only pass-1/pass-2 stage pairs; pass-1.5 folds invisibly into `pass-2 ✓ <elapsed>`. Open.

## 6. Repo / environment state

- `main` at `65952e1`. **11 #143 commits unpushed** (`ec27db0..65952e1`) — push not approved. Everything through `b14c0e5` IS pushed.
- Untracked: `docs/Screenshot 2026-08-09 213341.png` (Joseph's gate screenshot — keep or delete, owner's call).
- Suite green via **exit code** — pytest 9.0.3 in this env prints NO summary count line; verify with `echo $?` + grep FAILED/ERROR = 0.
- gws auth: refresh token expired mid-session tonight; Joseph re-ran `gws auth login` (interactive). If `invalid_grant` recurs, hand him that command again.
- Vault = `/mnt/c/Users/fangq/Documents/Obsidian Vault` (`~/Obsidian` symlinks to it). No cron tasks live in any session (previous session's run monitor died with it).
- Label IDs (gmail): Substack_raw = `Label_3904419182772066476`, Substack_ai_processed = `Label_5911144970725566262`. Re-conversion recipe (if ever needed): delete file(s), filter journal lines by `message_id`, re-label via `GmailClient().modify_labels`, re-run `kdb-gmail-fetch --max N`; dry-run first — Gmail lists newest-first so batch membership shifts.

## 7. Next session — candidate priorities (Joseph's call)

1. #143 parked decisions: backlog truth → chunked runs; compile vs raw-for-equity-repo; closure.
2. Second feeder: model-prompt archive (the two prompt files already live excluded in `Projects/Obsidian-KDB/prompt/`).
3. #140 pass-1.5 console stage (small, self-contained).
4. #139 use-case pick (agentic query-time traversal lean) → informs #141/#142 sequencing.
5. Housekeeping: push the 11 #143 commits; docs/reference pipelines.json sweep; screenshot disposition.
