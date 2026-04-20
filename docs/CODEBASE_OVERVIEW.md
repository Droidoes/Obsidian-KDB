# Obsidian-KDB — Codebase Overview (North Star)

**Status:** v1 architecture locked — M0 scaffolding in progress
**Last updated:** 2026-04-18
**Owners:** Joseph (human) + Claude Opus 4.7 (staff architect) + GPT 5.4 / Codex 5.3 (external review)

This is the **single source of truth** for the Obsidian-KDB project. All design rationale, decisions, and open questions live here. External AI consultation artifacts (Grok / Gemini Pro / GPT 5.4 / Codex 5.3) are referenced but not authoritative — they fed into the consensus captured below.

---

## 1. Vision

A Karpathy-style LLM-compiled knowledge base (KDB) that lives inside Joseph's Obsidian vault without disturbing its existing human-curated structure.

**Core insight (Karpathy):** The LLM is the compiler. Raw sources (`raw/`) → compiled wiki (`wiki/`) via incremental LLM passes. Obsidian is the IDE/frontend; plain Markdown + wikilinks are the only storage format the end-user sees.

**What's novel in our build:** Most community implementations let the LLM directly write markdown files via agent tools (Claude Code / Cursor Write/Edit). That gives the LLM free authorial control and produces hallucinated paths, corrupt frontmatter, and inconsistent state. **Our architecture makes the LLM output structured JSON "page intents"; deterministic Python owns every file path, every byte of frontmatter, and every filesystem write.** This matches the discipline of a real compiler (LLM = parser/semantic analyzer; Python = codegen/linker).

**Design philosophy — no complexity for imaginary risk.** This system has one user, one process, and infrequent operation (minutes to hours between compiles, not milliseconds). We do not add locking/retry/transaction ceremony designed for multi-tenant or high-contention systems. Any individual file's corruption is recoverable by re-compiling — the value is in the collective body of `raw/` + `wiki/` + connections, not any single file. Cheap insurance only (atomic temp+fsync+replace, journal file, 2-retry max on transient I/O). No lock files, no two-phase commits, no cross-file transactions.

---

## 2. Two-Sided Vault Architecture

The vault has two distinct sides with different ownership:

| Side | Path | Owner | Purpose | Mutability |
|---|---|---|---|---|
| **Human Side** | `~/Obsidian/{AIML, Daily Notes, Projects, ...}` (22 existing folders) | Joseph, manually | Daily capture, thematic organization, long-form notes | Pristine — no LLM writes |
| **Machine Side** | `~/Obsidian/KDB/` | LLM compiler (via Python) | Raw sources + compiled wiki + state ledger | LLM owns `wiki/`; Python owns `state/`; Joseph owns `raw/` |

The two sides coexist as peers. Cross-linking between them is opt-in and asymmetric (see §8 Open Questions, Open-4).

---

## 3. Repo vs. Vault Separation

Two completely separate filesystems:

| Concern | Path | VCS / Backup |
|---|---|---|
| **Code** (this repo) | `~/Droidoes/Obsidian-KDB/` (WSL Linux) | git + GitHub |
| **Data** (vault) | `~/Obsidian/KDB/` (Windows local drive, OneDrive-synced) | OneDrive (30-day version history) |

The code reads from and writes to the vault via absolute paths. No nested git repos. No symlinks. OneDrive is the backup — we do **not** run a separate git repo inside the vault (earlier proposal dropped; OneDrive version history is sufficient for v1).

---

## 4. Two Tracks

### Track 1 — KDB Compiler (this project, v1 focus)
`raw/` → LLM → `wiki/{summaries, concepts, articles}`

Karpathy-pattern incremental compile. Described in detail below.

### Track 2 — `llm-linker` (deferred to v1.5 / v2)
In-place enhancer for the Human Side. Scans user-authored notes and injects `[[wikilinks]]` to KDB concepts. Renamed from "enhancer" at Joseph's request. Separate implementation; not part of this v1 scope.

---

## 5. Track 1 Pipeline (V1a)

```
┌────────────────┐   ┌───────────┐   ┌──────────────────┐   ┌────────────┐   ┌───────────────────┐   ┌──────────────────┐
│   kdb_scan.py  │──▶│ planner.py│──▶│ compiler.py      │──▶│ validate.py│──▶│ patch_applier.py  │──▶│ manifest_update  │
│ (deterministic │   │ (chunk    │   │ (per-source LLM, │   │ (schema)   │   │ (Python writes    │   │  .py (atomic     │
│  scan, hashes) │   │  batches) │   │  JSON output)    │   │            │   │  all .md files)   │   │  ledger update)  │
└────────────────┘   └───────────┘   └──────────────────┘   └────────────┘   └───────────────────┘   └──────────────────┘
       │                                                                                                       │
       ▼                                                                                                       ▼
 last_scan.json                                                                                         manifest.json
                                                                                                         runs/<run_id>.json
```

**Strict separation of concerns:**
- **LLM is stateless compute.** It receives prompt + source content + manifest snapshot; returns JSON with `slug`-keyed page intents (no paths, no timestamps, no frontmatter). Never writes files. Never reads filesystem state.
- **Python is deterministic state + I/O.** Scans, hashes, chunks, resolves paths, applies page intents (writes markdown), stamps frontmatter, updates ledger.
- **Markdown vault is persistent state.** Everything the system knows is reconstructible from `raw/` + `wiki/` + `state/`.

### Page ownership split

| Page | Authored by | Strategy |
|---|---|---|
| `wiki/summaries/*.md` | LLM | Full-body replacement; Python adds frontmatter |
| `wiki/concepts/*.md` | LLM | Full-body replacement; Python adds frontmatter |
| `wiki/articles/*.md` | LLM | Full-body replacement; Python adds frontmatter |

No `index.md` (D23) and no `log.md` (D24) are generated. Obsidian's file explorer + `manifest.json` serve as the TOC; `state/runs/<run_id>.json` is the authoritative per-run journal.

### Pipeline stages

1. **Scan** (`kdb_scan.py`) — walks `raw/`, computes SHA-256, compares to `manifest.json`, emits `last_scan.json` with `to_compile` + `to_reconcile` lists. Handles symlinks (skip), binaries (flag metadata-only), two-pass rename detection. Atomic write.
2. **Plan** (`planner.py`) — reads `last_scan.json`, chunks `to_compile` into 10–20-source batches, builds per-source context snapshot from manifest.
3. **Compile** (`compiler.py`) — for each source: calls `call_model_with_retry` with source content + manifest snapshot + `CLAUDE.md`; receives `compiled_sources[]` entry (slugs + page bodies, no paths/metadata); accumulates into `compile_result.json`.
4. **Validate** (`validate_compile_result.py`) — schema-gates `compile_result.json`; aborts run with no vault writes if malformed.
5. **Compute next manifest (pure)** (`manifest_update.build_manifest_update`) — in-memory only; no writes. Produces `next_manifest` + `journal`.
6. **Apply page intents** (`patch_applier.py`) — resolves slugs to paths (`paths.py`), stamps frontmatter from `next_manifest` (`run_context.py`), writes markdown files atomically (`atomic_io.py`). Never writes state files.
7. **Persist manifest** (`manifest_update.write_outputs`) — writes `runs/<run_id>.json` journal first, then `manifest.json` atomically (D15, journal-then-pointer). Runs **after** page writes so a failed vault write leaves state unchanged and the user re-runs cleanly.

---

## 6. State Model

Adopts **GPT 5.4's three-layer design**, hardened by Codex 5.3:

| Layer | Storage | Authority |
|---|---|---|
| **Per-page provenance** | Frontmatter in each `.md` file (`raw_path`, `raw_hash`, `raw_mtime`, `compiled_at`) | Human-readable, survives manifest loss |
| **Ledger** | `KDB/state/manifest.json` | Authoritative index of sources, pages, orphans, tombstones, runs |
| **Audit trail** | `KDB/state/runs/<run_id>.json` | Per-compile journal (JSON) — authoritative; no derived `log.md` mirror (D24) |

**Rejected alternatives:** SQLite (too opaque, no diff, breaks OneDrive sync), vector DB (Karpathy explicitly rejects this), pure frontmatter-only (Grok's proposal — too lean at projected scale of thousands of files, no dependency graph).

**Manifest schema:** see `kdb_compiler/manifest.schema.md` (to be written in M1). Top-level sections: `schema_version`, `settings`, `stats`, `runs`, `sources`, `pages`, `orphans`, `tombstones`.

---

## 7. Decisions Ledger

| # | Date | Decision | Rationale |
|---|---|---|---|
| D1 | 2026-04-18 | Two-Sided Vault (Human Side / Machine Side) with `KDB/` at vault top-level | Zero disruption to existing human-curated folders; clean ownership boundary |
| D2 | 2026-04-18 | Code repo separate from vault data | Git on code (WSL), OneDrive on data (Windows); no nested repos |
| D3 | 2026-04-18 | Track 2 renamed "enhancer" → `llm-linker` | User preference; shorter |
| D4 | 2026-04-18 | v1 target use case = pull `docs/` from `~/Droidoes/*` repos as seed raw sources | Known high-value content, low risk |
| D5 | 2026-04-18 | OneNote stays on Human Side | User decision |
| D6 | 2026-04-18 | No git inside vault; OneDrive version history is sufficient backup | Avoids `.git/index.lock` races with OneDrive sync |
| D7 | 2026-04-18 | Adopt GPT 5.4 state model (manifest.json + frontmatter + log.md + runs/) | Middle ground: richer than Grok's pure-markdown, lighter than Gemini's DAG+Git+Intent Architecture, matches working community patterns |
| D8 | 2026-04-18 | **LLM outputs "page intents" (slug + title + body + logical links); Python owns paths, frontmatter, timestamps, versions, backlink reconciliation.** Revised from original "patch-ops" wording after Codex M0 review. | Predictability, auditability, dry-run capability, no hallucinated paths / corrupt frontmatter. Boundary purity: LLM = semantic analyzer, Python = codegen/linker. |
| D9 | 2026-04-18 | Controller pipeline over mega-prompt (chunk 10–20 sources/batch) | Prevents prompt drift at 100+ files (Codex guidance) |
| D10 | 2026-04-18 | Reject SQLite for v1 (possibly v2 if scale demands) | JSON is LLM-inspectable, diff-friendly, OneDrive-compatible |
| D11 | 2026-04-18 | Content-hash (SHA-256) as source-of-truth; mtime is advisory only | Survives renames, OneDrive timestamp rewrites, cross-machine sync |
| D12 | 2026-04-18 | Flag-don't-nuke on delete: `orphan_candidate` + `tombstones`, never auto-delete wiki pages | User reviews orphans manually; no data loss |
| D13 | 2026-04-18 | Two-pass rename detection (hash-match before NEW/DELETED classification) | Prevents double-counting moved files (Codex fix) |
| D14 | 2026-04-18 | Minimal atomic write: temp + fsync + os.replace + ≤2-retry on transient I/O. **No lock files, no 6-retry ladder, no multi-phase commit.** | Single-user single-process workload; heavier machinery is imaginary-risk complexity. Revised from original Codex proposal after user philosophy note. |
| D15 | 2026-04-18 | Journal-then-pointer manifest writes (`runs/<run_id>.json` first, manifest.json last) | Crash-safe: failed runs don't corrupt ledger. Cheap; keep it. |
| D16 | 2026-04-18 | Provider abstraction ported from `~/Droidoes/Code-projects/youtube-comment-chat/src/llm.py` | Reuse: Anthropic / Gemini / OpenAI / Ollama already supported |
| D17 | 2026-04-18 | V1a: build full pipeline upfront (not evolve from mega-prompt) | Cleaner foundation, no rework later |
| D18 | 2026-04-18 | **Full-body replacement** over patch-ops for LLM-authored pages | Wiki pages are 100% LLM-owned; no human edits to preserve; no concurrent writers. Patch-op language, merge semantics, and per-op test surface = complexity for zero gain. Forward-compatible: the applier can accept `body` today and `ops[]` later without schema break. |
| D19 | 2026-04-18 (revised 2026-04-20) | Page-ownership split: LLM authors `summaries/`, `concepts/`, `articles/`. Originally included Python-authored `index.md` + `log.md`; both removed (D23, D24). | Python-authored files are pure functions of state; having the LLM emit them would waste tokens and risk drift. |
| D20 | 2026-04-18 | Shared seam modules: `paths.py`, `atomic_io.py`, `types.py`, `run_context.py` | Codex M0 review: three modules independently claim atomic-write discipline; centralize to prevent subtle divergence. |
| D21 | 2026-04-18 | Reserve `prompt_builder.py`, `context_loader.py`, `response_normalizer.py` as named stubs | Codex M0 review: `compiler.py` is trending toward god-module; reserve split points before M2 to avoid accretion. |
| D22 | 2026-04-18 | Design philosophy: **no complexity for imaginary risk** | Single-user, single-process, infrequent workload. Individual file corruption is recoverable by re-compile; the value is the collective body, not any single file. Drop machinery designed for multi-tenant/concurrent scenarios. See `~/.claude/projects/.../memory/feedback_no_imaginary_risk.md`. |
| D23 | 2026-04-20 | Drop `index.md`. Obsidian's file explorer + `manifest.json.pages{}` already serve as the TOC; the generated `index.md` was adding a misleading hub node to the graph view (every page had an inbound edge from it) without unique value. | Graph noise was real; the "single entry-point file" was redundant with Obsidian's native navigation and with `manifest.json` for programmatic consumers. Revises D19. |
| D24 | 2026-04-20 | Drop `log.md`. Same reasoning as D23: derived state, zero wikilinks = isolate node in graph view, and `state/runs/<run_id>.json` already holds the authoritative per-run journal with full detail. Warnings/info surfaced via stdout banners during the run; anyone needing post-hoc detail opens the JSON journal. | Eliminates a redundant human-facing mirror; no information is lost — just stops maintaining two views of the same data. Revises D19. |

---

## 8. Open Questions

| # | Question | Status | Plan |
|---|---|---|---|
| Open-1 | Statefulness implementation | ✅ **Closed (D7–D15)** | GPT 5.4 approach + Codex hardening |
| Open-2 | Output format / schema | 🟡 Partial | Frontmatter keys locked (D7); patch-ops JSON schema pending M2 |
| Open-3 | Safety model for Human Side edits | 🔴 Deferred | Only relevant to Track 2 (`llm-linker`), not v1 |
| Open-4 | Link direction between Sides | 🔴 Deferred | Track 2 concern; recommended **Option C (asymmetric + opt-in bidirectional)** but not confirmed |
| Open-5 | Binary file handling (PDF, images) in `raw/` | 🟡 Partial | v1 marks as `compile_mode: metadata_only`; actual PDF/image parsers = v2 |
| Open-6 | Page-intents JSON schema design (shape, not mechanism) | 🟡 Skeleton in M0.1; full design in M2 | Skeleton committed at `kdb_compiler/schemas/compile_result.schema.json` |
| Open-7 | Chunk size tuning (10–20 default) | 🟡 Heuristic | Validate empirically during M2 first compile |
| Open-8 | Slug → path policy (how `[[slug]]` resolves to a file) | 🟡 Partial | `paths.py` stub declared; rules locked in M1 (see module docstring) |

---

## 9. Roadmap

### M0 — Scaffolding (commit `796848b`) ✅
- [x] Vault scaffold: `~/Obsidian/KDB/{raw, wiki/{summaries, concepts, articles}, state/runs, CLAUDE.md}`
- [x] Repo scaffold: `~/Droidoes/Obsidian-KDB/{docs, kdb_compiler/tests/fixtures}`
- [x] `docs/CODEBASE_OVERVIEW.md` (this file)
- [x] `KDB/CLAUDE.md` — compiler invariants for LLM
- [x] ~~`KDB/wiki/index.md`, `KDB/wiki/log.md` (empty)~~ — dropped by D23/D24
- [x] `KDB/state/manifest.json` (initial empty shape)
- [x] `kdb_compiler/__init__.py` + 8 module stubs
- [x] Initial commit

### M0.1 — Codex review remediation (current)
Responds to `docs/code-review-M0-codex.md`:
- [ ] Rewrite `KDB/CLAUDE.md` — logical intent output only, no paths / metadata / forced prose
- [ ] Update overview: rename patch-ops → page intents; add D18–D22
- [ ] Stub shared seams: `paths.py`, `atomic_io.py`, `types.py`, `run_context.py`
- [ ] Reserve split-point stubs: `prompt_builder.py`, `context_loader.py`, `response_normalizer.py`
- [ ] Add `kdb_compiler/schemas/compile_result.schema.json` skeleton
- [ ] Add `docs/manifest.schema.md`
- [ ] Add 3 test fixtures (manifest.empty, compile_result.valid, compile_result.invalid)

### M1 — Deterministic layer (no LLM yet)
- [ ] `kdb_scan.py` (hardened v2: symlinks, binaries, two-pass rename, atomic writes)
- [ ] `manifest_update.py` (port Codex implementation verbatim)
- [ ] `compile_result.schema.json` + `validate_compile_result.py`
- [ ] `call_model.py` (port from `youtube-comment-chat`)
- [ ] `call_model_retry.py` (port Codex wrapper)
- [ ] `tests/` — fixture-based unit tests for scanner + manifest updater
- [ ] End-to-end dry run with synthetic `compile_result.json` fixture

### M2 — LLM layer (first real compile)
- [ ] `patch_ops.schema.json` — design + Codex review
- [ ] `planner.py` (chunk scanner)
- [ ] `compiler.py` (per-source LLM call, JSON output)
- [ ] `patch_applier.py` (markdown writer from patch ops)
- [ ] First compile: seed `KDB/raw/` with 3–5 docs from `~/Droidoes/*/docs/`
- [ ] Iterate on prompt + schema based on observed quality

### M3+ (deferred)
- [ ] Track 2 (`llm-linker`) — separate sub-project
- [ ] News Clippings ingestion channel (from Google Sheet)
- [ ] Books sub-project (Track 3)
- [ ] Binary parsers (PDF, image OCR)
- [ ] Scale validation at 1,000+ sources

---

## 10. External References

Consulted AI artifacts (stored in `~/Obsidian/Projects/Obsidian-KDB/`):
- `Karpathy LLM Knowledge Base in Obsidian - Grok.md` — original design + lean v1 statefulness
- `Statefulness Implementation -Grok.md` — community impl survey
- `Karpathy's Obsidian LLM Knowledge Base -Gemini Pro.md` — academic treatise (not adopted)
- `Karpathy Obsidian LLM Complier Implementation - GPT 5.4.md` — state model baseline (adopted)
- `Codex 5.3 Reviews of GPT 5.4 Implementation of Kaparthy Obsidian LLM KDB.md` — hardening + working code (adopted)
- `docs/code-review-M0-codex.md` — Codex 5.3 review of M0 scaffold (drove M0.1 remediation; 5 findings all actioned)

Reference implementations surveyed:
- Reddit #1 (fabswill) — mtime-based scan, manual orphan handling
- Ustaad (Sohardh/ustaad) — SHA-256 in frontmatter, log.md flagging
- ussumant/llm-wiki-compiler — standalone engine + MCP server
- Ar9av/obsidian-wiki — manifest-based state (closest to our v1)

Karpathy source:
- X post: https://x.com/karpathy/status/2039805659525644595
