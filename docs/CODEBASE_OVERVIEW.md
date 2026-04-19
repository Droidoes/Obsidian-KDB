# Obsidian-KDB — Codebase Overview (North Star)

**Status:** v1 architecture locked — M0 scaffolding in progress
**Last updated:** 2026-04-18
**Owners:** Joseph (human) + Claude Opus 4.7 (staff architect) + GPT 5.4 / Codex 5.3 (external review)

This is the **single source of truth** for the Obsidian-KDB project. All design rationale, decisions, and open questions live here. External AI consultation artifacts (Grok / Gemini Pro / GPT 5.4 / Codex 5.3) are referenced but not authoritative — they fed into the consensus captured below.

---

## 1. Vision

A Karpathy-style LLM-compiled knowledge base (KDB) that lives inside Joseph's Obsidian vault without disturbing its existing human-curated structure.

**Core insight (Karpathy):** The LLM is the compiler. Raw sources (`raw/`) → compiled wiki (`wiki/`) via incremental LLM passes. Obsidian is the IDE/frontend; plain Markdown + wikilinks are the only storage format the end-user sees.

**What's novel in our build:** Most community implementations let the LLM directly write markdown files via agent tools (Claude Code / Cursor Write/Edit). That gives the LLM free authorial control and produces hallucinated paths, corrupt frontmatter, and inconsistent state. **Our architecture makes the LLM output structured JSON patch-ops; deterministic Python owns every file write.** This matches the discipline of a real compiler (LLM = parser/planner; Python = codegen/linker).

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
`raw/` → LLM → `wiki/{summaries, concepts, articles, index.md, log.md}`

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
- **LLM is stateless compute.** It receives prompt + source content; returns JSON. Never writes files. Never reads filesystem state.
- **Python is deterministic state + I/O.** Scans, hashes, chunks, applies patches, updates ledger.
- **Markdown vault is persistent state.** Everything the system knows is reconstructible from `raw/` + `wiki/` + `state/`.

### Pipeline stages

1. **Scan** (`kdb_scan.py`) — walks `raw/`, computes SHA-256, compares to `manifest.json`, emits `last_scan.json` with `to_compile` + `to_reconcile` lists. Hardened for symlinks, binaries, rename-detection (two-pass hash match). Atomic write.
2. **Plan** (`planner.py`) — reads `last_scan.json`, chunks `to_compile` into 10–20-source batches, emits job queue.
3. **Compile** (`compiler.py`) — for each source in each batch: loads source content + related wiki pages (outgoing/incoming links from manifest), calls `call_model_with_retry`, receives JSON conforming to `compile_result.schema.json`, accumulates into `compile_result.json`.
4. **Validate** (`validate_compile_result.py`) — fails fast if LLM output malformed; nothing downstream runs.
5. **Apply patches** (`patch_applier.py`) — reads validated `compile_result.json`, writes markdown files (summaries/concepts/articles, updates index.md, appends log.md) deterministically.
6. **Update manifest** (`manifest_update.py`) — atomic write with retry/backoff; journal-then-pointer pattern (writes `runs/<run_id>.json` first, then updates `manifest.json`).

---

## 6. State Model

Adopts **GPT 5.4's three-layer design**, hardened by Codex 5.3:

| Layer | Storage | Authority |
|---|---|---|
| **Per-page provenance** | Frontmatter in each `.md` file (`raw_path`, `raw_hash`, `raw_mtime`, `compiled_at`) | Human-readable, survives manifest loss |
| **Ledger** | `KDB/state/manifest.json` | Authoritative index of sources, pages, orphans, tombstones, runs |
| **Audit trail** | `KDB/state/runs/<run_id>.json` + `KDB/wiki/log.md` | Per-compile journal (JSON) + user-readable log (markdown) |

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
| D8 | 2026-04-18 | **LLM outputs structured JSON patch-ops; Python writes all markdown files** | Predictability, auditability, dry-run capability, no hallucinated paths / corrupt frontmatter |
| D9 | 2026-04-18 | Controller pipeline over mega-prompt (chunk 10–20 sources/batch) | Prevents prompt drift at 100+ files (Codex guidance) |
| D10 | 2026-04-18 | Reject SQLite for v1 (possibly v2 if scale demands) | JSON is LLM-inspectable, diff-friendly, OneDrive-compatible |
| D11 | 2026-04-18 | Content-hash (SHA-256) as source-of-truth; mtime is advisory only | Survives renames, OneDrive timestamp rewrites, cross-machine sync |
| D12 | 2026-04-18 | Flag-don't-nuke on delete: `orphan_candidate` + `tombstones`, never auto-delete wiki pages | User reviews orphans manually; no data loss |
| D13 | 2026-04-18 | Two-pass rename detection (hash-match before NEW/DELETED classification) | Prevents double-counting moved files (Codex fix) |
| D14 | 2026-04-18 | Atomic writes via temp + fsync + os.replace + 6-retry exponential backoff + single-writer lock | OneDrive race-safety (Codex guidance) |
| D15 | 2026-04-18 | Journal-then-pointer manifest writes (`runs/<run_id>.json` first, manifest.json last) | Crash-safe: failed runs don't corrupt ledger |
| D16 | 2026-04-18 | Provider abstraction ported from `~/Droidoes/Code-projects/youtube-comment-chat/src/llm.py` | Reuse: Anthropic / Gemini / OpenAI / Ollama already supported |
| D17 | 2026-04-18 | V1a: build full pipeline upfront (not evolve from mega-prompt) | Cleaner foundation, no rework later |

---

## 8. Open Questions

| # | Question | Status | Plan |
|---|---|---|---|
| Open-1 | Statefulness implementation | ✅ **Closed (D7–D15)** | GPT 5.4 approach + Codex hardening |
| Open-2 | Output format / schema | 🟡 Partial | Frontmatter keys locked (D7); patch-ops JSON schema pending M2 |
| Open-3 | Safety model for Human Side edits | 🔴 Deferred | Only relevant to Track 2 (`llm-linker`), not v1 |
| Open-4 | Link direction between Sides | 🔴 Deferred | Track 2 concern; recommended **Option C (asymmetric + opt-in bidirectional)** but not confirmed |
| Open-5 | Binary file handling (PDF, images) in `raw/` | 🟡 Partial | v1 marks as `compile_mode: metadata_only`; actual PDF/image parsers = v2 |
| Open-6 | Patch-ops JSON schema design | 🔴 Open — push to Codex | Will define in M2 before `compiler.py` / `patch_applier.py` |
| Open-7 | Chunk size tuning (10–20 default) | 🟡 Heuristic | Validate empirically during M2 first compile |

---

## 9. Roadmap

### M0 — Scaffolding (current)
- [x] Vault scaffold: `~/Obsidian/KDB/{raw, wiki/{summaries, concepts, articles}, state/runs, CLAUDE.md}`
- [x] Repo scaffold: `~/Droidoes/Obsidian-KDB/{docs, kdb_compiler/tests/fixtures}`
- [ ] `docs/CODEBASE_OVERVIEW.md` (this file)
- [ ] `KDB/CLAUDE.md` — compiler invariants for LLM
- [ ] `KDB/wiki/index.md`, `KDB/wiki/log.md` (empty)
- [ ] `KDB/state/manifest.json` (initial empty shape)
- [ ] `kdb_compiler/__init__.py` + module stubs (scan, manifest_update, validate, call_model, call_model_retry, planner, compiler, patch_applier)
- [ ] Initial commit

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

Reference implementations surveyed:
- Reddit #1 (fabswill) — mtime-based scan, manual orphan handling
- Ustaad (Sohardh/ustaad) — SHA-256 in frontmatter, log.md flagging
- ussumant/llm-wiki-compiler — standalone engine + MCP server
- Ar9av/obsidian-wiki — manifest-based state (closest to our v1)

Karpathy source:
- X post: https://x.com/karpathy/status/2039805659525644595
