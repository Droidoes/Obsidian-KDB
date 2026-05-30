# Session Handoff — 2026-04-20 → 2026-04-21

**Branch:** `main`  **Last commit:** `48f1666` drop log.md
**Tests:** 386/386 passing (baseline from 2026-04-19; no test-touching work today)
**Ahead of `origin/main`:** 34+ commits (push deferred — hold until KDB-Compiler-System-Prompt.md rewrite is installed + first compile against it is green)
**Next milestone:** M2 — finish `KDB/KDB-Compiler-System-Prompt.md` rewrite, then resume quality-eval work (Task #5)

---

## Who's driving and why

Opus 4.7 is driving. Today's work was design/prompt-engineering/explanatory docs — reasoning-heavy, low-mechanical. Opus stays for the system-prompt rewrite through Task #15. Switch back to Sonnet 4.6 only once we drop into implementation tasks (Task #5 scoring, Task #6 empty-plan crash fix).

---

## Where we are on Task #4 (prompt design umbrella)

Task #4 has been decomposed into Tasks #9–#15. Status at end of session:

| # | Task | Status |
|---|---|---|
| #9 | 1-sentence ask | ✅ locked |
| #10 | 3–5 bullet high-level spec | ✅ locked (v3, all 5 bullets approved) |
| #11 | Detailed behavioral sections | ⬜ **start here tomorrow** |
| #12 | Claude's draft from spec | ⬜ pending #11 |
| #13 | Parallel drafts from Grok/Gemini/QWEN/GPT5.4 + synthesize | ⬜ pending #12 |
| #14 | Optional cross-model feedback pass | ⬜ pending #13 |
| #15 | Install final KDB-Compiler-System-Prompt.md to vault | ⬜ pending #13/14 |

### Task #9 — 1-sentence ask (locked)

> "Write a system prompt that instructs an LLM to read one source document from a markdown knowledge base and return a single JSON object describing the new or updated wiki pages (summaries, concepts, articles) this source should produce."

### Task #10 — 5-bullet high-level spec (locked, v3)

1. **Input.** You will be given one source document from a markdown knowledge base (the full text appears in the user message).
2. **Output taxonomy.** Identify the wiki pages this source should produce. A "wiki page" is one of three kinds: a *summary page* (one per source, short overview), *concept pages* (one per atomic idea), or *article pages* (narrative syntheses across multiple concepts — rare, only when the source clearly warrants one).
3. **Reuse slugs where appropriate.** The user message includes an EXISTING CONTEXT list — pages already in the knowledge base (slug + title + page_type + outgoing_links, no bodies). When the current source discusses an idea that matches an entry in that list, use the existing slug verbatim rather than minting a similar-but-different one. This is how the knowledge base compounds across sources instead of fragmenting into near-duplicates.
4. **Body format.** Write the page bodies in Obsidian-flavored markdown, using `[[slug]]` wikilinks to connect concepts to each other.
5. **Output envelope.** Return one JSON object matching the schema provided in the user message. Nothing before it, nothing after it, no markdown fences.

### What this spec deliberately defers to Task #11

These land in the detailed behavioral sections, not the top-line bullets:
- When to emit an article vs. when not to
- `confidence` field semantics (low/medium/high; honest bucket > false precision)
- The `outgoing_links` ↔ body contract (every slug in `outgoing_links` must appear as `[[slug]]` in the body)
- Supporting-source declarations (`supports_page_existence`)
- Tone / length guidance for bodies
- Cold-start behavior (what to do when EXISTING CONTEXT is empty — e.g., EP1)

### Core principle carried over from today (do not drift on this)

**The LLM doesn't care about our internal architecture.** No references to Dnn decisions, no "Python does X", no "boundary purity", no mention of manifest.json / state/runs / patch_applier / validator. The compile LLM needs semantic rules for its *own* output — everything else is noise in the prompt.

If the draft starts sliding into doc-voice ("the manifest tracks...") or architect-voice ("this respects the D8 boundary..."), stop and rewrite. Instruction-voice only, addressed to the compile LLM.

---

## Work completed today

### Task #3 — Wiki type & graph case study (closed)
- `docs/wiki.md` written — purpose, three-type ontology, why three, lifecycle of a concept, graph topology, linking discipline.

### Task #7 — Drop `index.md` (D23, committed `b708d63`)
Full surface-area sweep:
- `kdb_compiler/patch_applier.py` — dropped index rendering path
- `kdb_compiler/manifest_update.py` — dropped `index_file` default
- Tests: `test_patch_applier`, `test_kdb_compile` — flipped assertions
- Docs: `CODEBASE_OVERVIEW.md`, `manifest.schema.md`
- Vault: removed `~/Obsidian/KDB/wiki/index.md`
- **Rationale (D23):** `manifest.json` is the machine index; Obsidian's file explorer is the human TOC. The generated `index.md` was a misleading graph-view hub.

### Task #8 — Drop `log.md` (D24, committed `48f1666`)
Parallel sweep to D23:
- `patch_applier` — dropped `_LOG_STUB_HEADER`, `render_log_prepend`, `_read_log`, `ApplyResult.log_appended`
- `manifest_update` — dropped `log_file` default
- `run_context.append_log` docstring updated — "persisted to state/runs/<run_id>.json journal"
- `compile_result.schema.json` — `log_entries` description updated
- Tests: 4 `render_log_prepend` tests removed; assertion flips
- Vault: removed `~/Obsidian/KDB/wiki/log.md`
- **Rationale (D24):** `state/runs/<run_id>.json` is the authoritative journal with far more detail. The prepended `log.md` stub was an isolate node in the graph view (zero wikilinks).

### Task #4 — Prompt engineering groundwork
- Confirmed `KDB/KDB-Compiler-System-Prompt.md` is the **exact** system prompt sent to Haiku (no code-side transform).
- Generated **offline** EP1 prompt reconstruction via `prompt_builder.build_prompt()` → `docs/example-prompt-ep1-china.md` (system: 6,051 chars; user: 30,217 chars; context pages: 0).
- `docs/system-prompt.context-pages.md` — the context-pages mechanism (body-free, 4 fields; selection = source-match ∪ token-match → depth-1 expansion → seeds-first cap-50; EP1 cold-start signature explained).

### Incidental
- Fixed the ASCII-drawn "architectural axis" table in `Projects/Obsidian-KDB/M2 upfront schema discussion - GPT5.4.md` — converted to proper markdown.

---

## Quick-start for tomorrow (first thing)

1. `cd ~/Droidoes/Obsidian-KDB && git log --oneline -5` — confirm at `48f1666`.
2. Re-read the **Task #10 locked spec** (above) and the **core principle** warning about architect-voice drift.
3. Start Task #11 — expand bullet by bullet into detailed sections. Suggested order:
   - Start with **bullet #2** (output taxonomy) — this is where concrete worked-examples matter most. Consider dropping in the *Attention Is All You Need* fixture we discussed (proposed `docs/example-wiki-attention-paper.json` + `.md`) as a portable anchor.
   - Then **bullet #3** (slug reuse) — extend with what to do when EXISTING CONTEXT is empty (cold start), and what to do when a match is fuzzy.
   - Then **bullets #4, #5** — the mechanical ones. Should be tight.
   - Last: **bullet #1** (input framing) — the lightest one; small tweak, if any.
4. Produce a **Claude draft** (Task #12) only after #11 is complete.
5. User will take the spec to **Grok / Gemini / QWEN / GPT5.4** for parallel drafts (Task #13). Our Claude draft goes in that same pool.

---

## Key reference docs written today

| Doc | Purpose |
|---|---|
| `docs/wiki.md` | Three-type ontology rationale (summary/concept/article) |
| `docs/system-prompt.context-pages.md` | How context pages are selected, cold-start case |
| `docs/example-prompt-ep1-china.md` | Full offline reconstruction of EP1 prompt (read before drafting the system prompt) |
| `docs/compile_result.md` (written earlier; confirmed current) | `pages[]` schema walkthrough + baton mental model |
| `docs/manifest.schema.md` (written earlier; trimmed today for D23/D24) | Manifest structure reference |

---

## Open items (carry-forward)

- [ ] **Task #11** — detailed behavioral sections (start tomorrow)
- [ ] **Task #5** — LLM response quality evaluation (still open from 2026-04-19)
- [ ] **Task #6** — `patch_applier` empty-plan crash fix (ticket `65c2f65`)
- [ ] **Task #2** — scalability discussion
- [ ] Push `main` to origin — **hold until** new KDB-Compiler-System-Prompt.md is installed and first compile against it passes
- [ ] Resolve Open-1..Open-8 in `docs/CODEBASE_OVERVIEW.md` before end of M2

---

## Working conventions (unchanged — do not drift)

- **Test command:** `python3 -m pytest kdb_compiler/tests --ignore=kdb_compiler/tests/test_call_model.py --ignore=kdb_compiler/tests/test_call_model_retry.py --ignore=kdb_compiler/tests/test_config.py`
- **Python binary:** `python3` (no `python` alias)
- **Commit gate:** explicit user approval before committing (80/20 rule, Phase 5)
- **No Dnn / architecture / Python-side references in the LLM prompt itself** — instruction-voice, addressed to the compile LLM, self-contained

---

## Auto-memory highlights relevant to tomorrow

- `feedback_no_imaginary_risk.md` — single-user single-machine; don't add locking/retry ceremony
- `feedback_measurability_over_defensive_complexity.md` — invest in observability, not machinery
- `feedback_name_must_match_contents.md` — don't use aspirational names; the LLM-facing prompt especially

---

## Last 5 commits
```
48f1666 drop log.md: state/runs/<run_id>.json is the authoritative journal
b708d63 drop index.md: Obsidian explorer + manifest already serve as TOC
65c2f65 docs: open ticket for patch_applier empty-plan crashes
b377bfc kdb_compile: 7-stage banners + per-stage timing on progress stream
9f4610e docs: role + mental-model explainers for compile_result / last_scan / manifest
```
