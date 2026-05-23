# Session Handoff — 2026-05-23 (Saturday afternoon)

Continuation of Saturday morning's #83/#84 O1 implementation arc.
Afternoon block ~4 commits, all in service of:
- **α-split close** (S06/S07/S05) — 11/15 → 14/15 probes
- **Option A close** (S12/S18) — 14/15 → 15/15 probes (zero xfail)
- **Path 0 fire** (raw/ recompile) — empirical signal on the week's work
- **Default model swap** to `deepseek-v4-flash:direct`

Branch state: **2 commits ahead** of `origin/main` (v1.5 GREEN closer + model swap). User to fire `git push origin main`.

## Commits this session

| SHA | Subject |
|---|---|
| `c06f16d` | feat(op_1): GREEN v1.3 — unblock S06 + S07 via classifier rule + corpus hashes |
| `dde9664` | feat(op_1): GREEN v1.4 — unblock S05 via LINKS_TO-implicit-counterpart fallback |
| `344b0bf` | feat(op_1): GREEN v1.5 — 15/15 O1 probes, zero xfail; S12+S18 closed |
| `ac0a2ec` | chore(kdb-compile): switch default --model to deepseek-v4-flash:direct |

First two pushed (via Joseph firing `git push origin main` post-`dde9664`). Last two held local.

## Probe-set status

```
15/15 O1 PASS, zero xfail
  ✅ S01–S02, S05, S06, S07, S08–S09, S12–S19
Probe-corpus version: #87.1 v1.2
```

## Empirical findings from Path 0 fire (the highest-value part of the afternoon)

### 🔴 Finding 1 — #76 Domain field dormant in production (ROOT CAUSE FOUND)

A/B test on same source content (Li_Lu_Munger_College):
- gemini-3.1-flash-lite → `domain: null` on every page
- deepseek-v4-flash:direct → `domain: null` on every page

**Both top models, same null output.** Rules out model laziness.

Root cause: `~/Obsidian/KDB/KDB-Compiler-System-Prompt.md` mentions "domain" only 2x, both in vague qualitative senses ("different domain" re: slug-minting). **The prompt never instructs the LLM to populate the `domain` schema field.** Schema (`kdb_compiler/schemas/compiled_source_response.schema.json:97`) is optional + nullable + description says "Omit or null when unknown" — LLMs correctly follow the schema's permissive invitation.

**Smoking gun in project history:** TASKS.md #76's deferred-followups list explicitly says *"Other deferred (not in #76): per-source source_id on BELONGS_TO (R6 promotion), analytics.py:29 canonical-only filtering, prompt + producer-contract amendments."* The prompt-amendment follow-up was **never filed as a separate task**; got forgotten between sessions.

**Fix scope (~30-60 min):**
1. Amend KDB-Compiler-System-Prompt.md with explicit instruction to populate `domain`/`sub_domain` per #76 ontology
2. Optionally tighten schema: drop null from `oneOf`, remove "Omit or null when unknown" description, add to `required`
3. Re-fire on Li_Lu (with sentinel-hash trigger trick from afternoon, or via Task #17's `--force-all` flag) to verify

**Filed as Task #20.** Recommended next-session immediate target.

### 🔴 Finding 2 — #74 Canonicalization ledger never operationalized

Stage 6 runs in fallback mode (`Alias ledger not found at /mnt/c/Users/fangq/OneDrive/Documents/Obsidian Vault/KDB/state/canonicalization/aliases.json; running with empty ledger (string normalization only — D-R5-8)`).

Per #74 design, the ledger is **manually curated**. That curation step was never operationalized. Result: 0 ALIAS_OF edges in real graph since #74 v2.1 schema landed 2026-05-20.

**Fix options:**
- (a) Bootstrap an initial `aliases.json` from inspecting current entities for likely-aliases (semi-manual)
- (b) Document/clarify the alias-discovery workflow (when to add, who decides)
- (c) Treat as 'expected dormant until aliases manifest' and downgrade Stage 6 verbose warning

**Filed as Task #21.** Less urgent than #20.

### 🟡 Side finding — DeepSeek extracts ~2.2× more pages per source

| Metric | Gemini | DeepSeek |
|---|---|---|
| Li_Lu pages extracted | 5 | 11 |
| Latency | 5.8s | 32.7s (5.6× slower, matches Saturday morning bench) |
| Cost | ~$0.05 | ~$0.03 |

Per-page latency may be comparable. Worth deeper investigation in a future session — is more better (richer ontology) or worse (over-extraction)? Affects quality scoring + cost analysis.

### 🟡 Side finding — #66 trigger model has no force-recompile escape hatch

`kdb-compile` has no `--force-all` flag; the trigger model is intentionally restrictive per #66 rationale. The all-zeros-sentinel sha256 (`sha256:000...000`) works as a workaround that passes scan-schema validation. Filed as **Task #17** for a future small CLI feature.

## Latent debts unchanged

From sub-arc 3 (v1.4 commit), four debts still tracked but un-tested at current F3 shared-keys-only verifier strictness:
1. Mutator does not write object Entity nor LINKS_TO for any topology-only path
2. Mutator's `reinforces → creates_claim=True` ignores corroboration threshold N (S16/S17 expect topology-only below N)
3. No Tier-1 EVIDENCES reconstruction from `run_payloads`
4. LINKS_TO schema carries only `(run_id, created_at)` — no predicate-class / scope / polarity

All four unlock together when verifier tightens to strict equality after **promotion-replay infrastructure** lands (blueprint §6: "Rebuild re-runs the Promotion Contract").

## Methodology lessons reinforced

1. **Decomposition first.** Morning handoff's "uniform LINKS_TO-implicit-counterpart class" was wrong — three distinct root causes hid in one label. Refining the framing prevented designing one mechanism for three problems.

2. **Harness-scope lens, applied early, prevents over-engineering.** Advisor caught the sub-arc 3 over-engineering: the harness only asserts disposition + drift; everything in `expected_post_state` is documentation. Saved ~3h of unnecessary Tier-1 / schema work. Then the same lens applied to sub-arc-3 design without prompting.

3. **Munger-style "easy way out vs right thing to do" reframes.** Path 1 (hand-craft scout pass) was the easy way out; soft close + handoff is the right thing for the multi-session arc; Path 0 (recompile raw/ to exercise this week's #74/#76 work) was the genuine empirical middle path that fit today's session shape AND produced load-bearing findings.

4. **Real-corpus fire surfaces what probe tests can't.** Both findings 1 + 2 are silent design gaps the probe suite would never have caught (no LLM in loop, no real curation workflow). Path 0 cost ~$0.10 + 30 minutes and produced two of the highest-quality findings of the day.

## What to consult on session resumption

- **Task #20** (the high-leverage immediate target): `~/Obsidian/KDB/KDB-Compiler-System-Prompt.md` (mentions domain 2x in vague senses; needs amendment), `kdb_compiler/schemas/compiled_source_response.schema.json:97` (schema permissive on domain field), TASKS.md #76's deferred-followups comment (where this gap was first surfaced + forgotten)
- **Memory `feedback_user_fires_api_cost_runs`** — for any LLM-fire follow-ups in next session, present command and wait
- **Memory `feedback_concrete_first_extract_later`** — when designing the Analysis-op (the multi-session next arc), look at concrete real-corpus output first
- Path 0 backup files: `~/Obsidian/KDB/state/manifest.json.bak-2026-05-23-pre-deepseek-test` (deletable; not load-bearing). Snapshot: `~/Obsidian/KDB/state/graph-snapshots/2026-05-23T13-35-22_EDT/`.

## Strategic pivot at session close (added after Path 0)

**The "tunnel from both ends" reframe — ratified 2026-05-23 evening by Joseph.**

After Path 0's findings landed, Joseph called the architectural elephant in the room: the project has spent ~6 weeks deepening end A (compile pipeline) and zero weeks on end B (ingestion pipeline). Continued investment in end A has diminishing returns when end B doesn't exist. **Pause end A deepening; focus all architectural design effort on end B.**

### Strategic principles ratified

1. **End B = platform, not a single LLM pass.** Pluggable adapters for multiple source streams: manual `.md` drops today; future: RSS, podcasts, YouTube transcripts, web scrapes, PDFs, emails. All streams converge to a normalized internal form compile consumes.

2. **Three "big things" on the ingestion side:**
   - **Ingestion framework / platform itself** (the multi-source-stream foundation)
   - **Domain/sub_domain classification** (MOVED from end A — was Task #20)
   - **LLM preprocessing pass** (embeds frontmatter at top, suggests wiki links at end)

3. **Minor finishing on end A is OK** — `--force-all` flag (Task #17), small bug fixes. Just don't ADD new architectural surface on the compile side.

4. **Move-don't-duplicate discipline.** During ingestion design, review the compile pipeline and identify what should MOVE from end A to end B. Domain extraction is the first concrete example. AVOID building the same logic on both sides.

5. **Iterate to ONE tunnel.** End state is a single integrated pipeline. Two failure modes actively to avoid:
   - **Two parallel tunnels** — compile + ingest become silos that never converge
   - **One never-finished tunnel** — perpetual scope-creep; no v1 ever reached

   Discipline: ship a v1 that works end-to-end, then refine.

### Operational impact on Tasks

| # | Status | Note |
|---|---|---|
| #17 `--force-all` flag | Active (minor compile-side; OK to finish during ingestion design) | |
| #20 #76 prompt amendment | **Deleted / superseded** | Domain extraction MOVES to ingestion-side, so amending the compile-side prompt is the wrong layer |
| #21 #74 aliases.json setup | **Deleted / superseded** | Likely shared infrastructure between both ends; design after ingestion architecture clarifies |
| **#88 Ingestion Pipeline (NEW)** | **Open / scoping** | Umbrella for the multi-source-stream platform arc; sub-tasks emerge from blueprint |
| Analysis-op for #83/#84 (re-scoped) | Open question for #88 | Does Analysis live IN ingestion, IN compile, or as a 3rd pipeline? Resolved as part of the ingestion design phase |
| 4 latent debts from sub-arc 3 | Still deferred (post promotion-replay) | Unchanged |

## Open path — next session (REVISED post-strategic-pivot)

**Primary: brainstorm ingestion pipeline architecture.** This is the next #74-/#82-/#83-/#84-scale architectural arc. Pattern to follow:

1. `superpowers:brainstorming` on ingestion-as-platform — explore source streams, metadata schema, where the LLM pass lives, how the domain ledger interacts, how Analysis-op fits in, what gets moved from compile-side
2. Multi-model parallel design pass (Gemini + GPT + Grok + Opus per Round 6 / #82 pattern)
3. Synthesis → blueprint v1 at `docs/task88-ingestion-pipeline-blueprint.md`
4. 3-reviewer external panel (Codex + Deepseek + Qwen per `docs/external-review-panel.md`)
5. v2 synthesis + ratification
6. Implementation arcs (sub-tasks of #88)

**Realistic scope: 2-3 sessions just for design.** Implementation comes after.

**Secondary (only if energy/time):** Task #17 `--force-all` flag (~30 min) — small compile-side utility worth finishing.

## Things to consult on session resumption

- **Memory `tunnel-from-both-ends-pivot-2026-05-23`** (loaded automatically via MEMORY.md) — the strategic frame
- **Memory `feedback_concrete_first_extract_later`** — applies to ingestion: look at concrete source streams (RSS, YouTube, etc.) BEFORE designing the platform abstraction
- **Memory `feedback_no_imaginary_risk`** — applies to ingestion: don't over-engineer multi-stream support before validating single-stream end-to-end
- **Path 0 findings as design input**: #76 Domain field dormant in production (root cause = prompt under-instruction) is now design INPUT for the ingestion-side metadata extraction, not a fix-in-place target
- **`docs/external-review-panel.md`** — the 3-reviewer panel composition + flow
- **`docs/what-is-the-ontology-for.md` §9.4** — Round 6 context; Analysis-op question lives here

## Mental state for resumption

This was an unusually rich session — closure of architectural objective (15/15 GREEN) + real empirical signal from Path 0 + TWO Munger-style honest reframes (Option B as vapor option → Path 0; then end-A-deepening as wrong direction → end-B-ingestion). The pivot at close is the most strategically important moment of the day. **Don't try to start the ingestion brainstorm cold next session — let the warmup load the tunnel-pivot memory and the strategic frame settles in, THEN brainstorm.**

**Next session should start with /warmup + reading this handoff (especially the §Strategic pivot section) before any code.**
