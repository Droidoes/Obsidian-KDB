# Ingestion Subsystem — Brainstorm Working Agenda

**Status:** Brainstorming (Phase 1 — discussion). Working agenda, not a blueprint.
**Started:** 2026-05-17
**Participants:** Joseph (human) + Claude Opus 4.7 (staff architect) + Codex (external review)

This document is the live agenda for designing how raw sources get *into* KDB.
Items are walked one at a time; resolutions are recorded inline. When the agenda
is exhausted, the settled decisions graduate into formal design specs under
`docs/superpowers/specs/`.

---

## 1. Framing (the reframes that shape everything)

- **A harvester does not plug into the compiler.** The compiler has exactly one
  input — `raw/`. `kdb_scan.py` walks it, hashes, recompiles whatever changed
  (D46). An "ingestion pipeline" is therefore *anything that writes files into
  `raw/`*. The compiler never needs to know a harvester exists.
- **Two change-tracking layers, kept distinct:**
  1. **Upstream cursor** — "what's new at the source" (git SHA, last export
     timestamp, RSS pubdate). Per-harvester. Lives harvester-side. New.
  2. **Ownership ledger** — "which `raw/` files did this harvester put there",
     so re-harvest can prune vanished-upstream files without touching another
     harvester's files. Per-harvester. New.
  3. **`source_state.json`** — KDB *already* tracks `raw/ → compile` change
     detection (D46 hash compare). **Harvesters must not touch this.**
- **The seam:** harvester owns `upstream → raw/`; compiler owns `raw/ → graph`.
  They meet at the filesystem and nowhere else.
- **Prior art:** 10x-Learning-Engine's `SourceAdapter` ABC
  (`fetch() → IngestionResult`) is the same shape. Lifted; the only difference
  is our sink is the filesystem `raw/`, not a DB.

## 2. Vocabulary (F0 — SETTLED)

`graphdb_kdb/ingestor.py` already means *compile-result → GraphDB*, so "ingestor"
is taken. Terms for this subsystem:

| Term | Means |
|---|---|
| **harvester** | external source → `KDB/raw/<namespace>/` |
| **compiler** | `KDB/raw/` → ontology / wiki / GraphDB |
| **graph-ingestor** | (existing) ontology record → GraphDB |

## 3. Decomposition & build order (X1 — SETTLED)

Scope is all four pieces: the framework + three harvesters.

**Build order — concrete-first, extract-later (decided 2026-05-17).** The
framework is NOT designed upfront. An abstraction drawn from a single example
encodes that example's accidents as essentials (Rule of Three); KDB's own
history — manifest → GraphDB refoundation, ontology elements migrating into
`runs/` — shows the right structure emerges from refactoring once the real
shape is visible. So:

- **Spec 1** — Droidoes-docs harvester, built **concretely** (no shared ABC).
  D4, simplest source. Written with clean internal seams (`discover` /
  `fetch_one` / `write_raw` as separable functions) so later extraction is
  mechanical, not a rewrite.
- **Spec 2** — second harvester (vault or chats), also concrete.
- **Spec 3 (framework extraction)** — revisit F1/F8/F9/F10 and extract the
  shared framework as a deliberate refactor from the two working harvesters.

Per-harvester mechanics (F2–F7) are still decided — but concretely, inside each
harvester's design, not as universal abstractions.

---

## 4. Agenda

Legend: 🔴 open · 🟢 settled · 🟡 partially settled

### 4.1 Framework

**Walk order:** F0 settled. F2–F7 (per-harvester mechanics) are decided
*concretely* while building the Droidoes-docs harvester. F1/F8/F9/F10
(cross-harvester abstraction) are **DEFERRED to extraction** — settled only
after ≥2 concrete harvesters exist (see §3 build order).

| ID | Item | Status |
|---|---|---|
| F0 | Vocabulary: harvester / compiler / graph-ingestor | 🟢 |
| F1 | Harvester contract (ABC shape) | ⏸ deferred to extraction |
| F2 | Sink & namespace: write only to `raw/<namespace>/` | ⏸ reopened — blocked on kernel question (flat vs. namespaced vs. raw/→sources/; see `what-is-ontology-for-V1.md` §4) |
| F3 | Stable raw-file identity & path convention (slug sanitization, collisions, source URI, upstream ID, rename = new vs. preserved) | ⏸ reopened — blocked on kernel question |
| F4 | Raw frontmatter / provenance contract — *constraint: volatile fields must not enter the hashed body (D46)* | 🔴 decide in Spec 1 |
| F5 | Upstream cursor | 🟢 none — stateless harvester (see §6 [3]) |
| F6 | Ownership ledger | 🟢 none — wipe + re-copy (see §6 [3]) |
| F7 | Deletion / prune semantics | 🟢 wipe handles it (see §6 [3]) |
| F8 | Runner & CLI (`kdb-harvest`?) | ⏸ deferred to extraction |
| F9 | No-direct-GraphDB-write default; direct-to-graph is an explicit, separately-decided exception | ⏸ deferred to extraction |
| F10 | Package placement (`kdb_harvest/`?) | ⏸ deferred to extraction |

### 4.2 Droidoes-docs harvester (Spec 1 — proving pipeline, D4)

| ID | Item | Status |
|---|---|---|
| DD1 | Selection scope (which repos, which paths, exclusions) | ⏸ blocked on kernel question — see `what-is-ontology-for-V1.md` |
| DD2 | Upstream cursor for git (SHA vs. mtime) | 🔴 |
| DD3 | Multi-repo path collision | 🔴 |
| DD4 | Overlap with manually-curated `raw/` sources (`CODEBASE_OVERVIEW.md` is already one) | 🟢 exclude `Obsidian-KDB` repo (see §6 [2b]) |

### 4.3 Obsidian-vault harvester (Spec 2 — has the open fork)

| ID | Item | Status |
|---|---|---|
| V1 | 🔴 Architectural fork: copy-to-`raw/` vs. direct-to-GraphDB vs. `llm-linker`-only | 🔴 |
| V2 | Selection policy (which of ~22 vault folders) | 🔴 |
| V3 | `llm-linker` relationship (complementary vs. competing) | 🔴 |
| V4 | Feedback loop (must not re-ingest KDB's own `wiki/`) | 🔴 |
| V5 | Existing vault wikilinks/properties — preserve, translate, or ignore | 🔴 |

### 4.4 LLM-chat-logs harvester (Spec 3)

| ID | Item | Status |
|---|---|---|
| C1 | Acquisition / export formats per vendor (Claude/Gemini/Grok/ChatGPT) | 🔴 |
| C2 | Raw unit (conversation vs. per-turn) | 🔴 |
| C3 | Signal vs. noise | 🔴 |
| C4 | Dedup across chats | 🔴 |
| C5 | Cursor (last-exported timestamp / message ID) | 🔴 |

### 4.5 Cross-cutting

| ID | Item | Status |
|---|---|---|
| X1 | Spec sequencing (framework + Droidoes-docs → vault → chats) | 🟢 |
| X2 | `source_type` discriminator values (one per harvester) | 🔴 |
| X3 | Automation: manual runs vs. scheduled (lean manual for v1) | 🔴 |
| X4 | Privacy / security classification (include/exclude, redaction, API-exposure implications) | 🔴 |
| X5 | Backfill / cost controls (harvest-only vs. chained, dry-run count, per-run cap, model choice, staged backfill) | 🔴 |
| X6 | Feedback-loop / generated-output exclusion policy (`state/`, `.venv`, `node_modules`, benchmark outputs, prior harvest output) | 🔴 |

---

## 5. Decisions log (this brainstorm)

| When | Decision |
|---|---|
| 2026-05-17 | Scope = framework + 3 harvesters; all three designed here, delivered as 3 specs (X1). |
| 2026-05-17 | Vocabulary fixed: harvester / compiler / graph-ingestor (F0). |
| 2026-05-17 | Codex review incorporated; Codex's "X6 — ontology record authority" dropped — D51 already settles it; valid kernel folded into F9. |
| 2026-05-17 | **Build order = concrete-first, extract-later.** No upfront framework design. Build Droidoes-docs harvester concretely → second harvester → then extract the shared framework (F1/F8/F9/F10) as a refactor. Per Rule of Three + KDB's own manifest/GraphDB refactor history. F2–F7 decided concretely per harvester. |
| 2026-05-17 | **Kernel question raised — "what is the ontology for?"** DD1 (and X6 scope, C3) blocked until resolved. Philosophy A (harvester curates) vs. B (compiler filters) vs. A+B (tagged sub-graphs). Discussion captured verbatim in `docs/what-is-ontology-for-V1.md`. |
| 2026-05-17 | **F2/F3 reopened.** Joseph↔Codex Exchange 3 (raw/ structure: flat vs. namespaced vs. `sources/` vs. vault-as-corpus) recognized as the A/B divide in disguise — captured in `what-is-ontology-for-V1.md` §4. F2/F3 blocked on the kernel question. |

## 6. Resolutions (filled in as items close)

### [2b] Source removal from `raw/` — investigated 2026-05-17

**Removing a source from `raw/` is a soft, two-step, non-destructive op:**

1. *Automatic, next `kdb-compile`:* scan emits a `DELETED` reconcile op →
   `source_state` pops the source to a `tombstone` → graph `_handle_source_deleted`
   drops the `Source`'s `SUPPORTS` edges and sets `Source.status='deleted'` →
   Phase 4 orphan detection marks every now-zero-SUPPORTS page `orphan_candidate`.
   Wiki `.md` files stay on disk untouched.
2. *Manual, deliberate:* `kdb-clean orphans` archives + de-lists the orphaned
   pages and `DETACH DELETE`s the entities.

So removal → soft orphaning → `kdb-clean` (gated, destructive). No auto-delete.

**Resolution:** Do NOT remove `CODEBASE_OVERVIEW.md` from `raw/` — removal would
orphan its ~12 compiled pages (real ontology loss). Instead **exclude the
`Obsidian-KDB` repo entirely from the Droidoes-docs harvester** (X6 feedback
loop). The hand-placed `CODEBASE_OVERVIEW.md` stays a curated source as-is; the
harvester never produces a competing copy. Other repos' `CODEBASE_OVERVIEW.md`
files ARE harvested, each repo-namespaced. → feeds **DD1** (repo exclusion list)
and **DD4**.

### [3] Droidoes-docs change tracking — resolved 2026-05-17

No per-harvester change-tracking layer. The compiler already detects change via
content-hash compare (D46). Droidoes-docs harvester is **stateless**: design (i)
— wipe `raw/droidoes-docs/` + re-copy all current `.md` each run. Deletions
handled for free; content-identical files stay hash-stable (no spurious
recompiles). A git-SHA cursor is only a fetch-skip optimization — premature for
local file copies. → settles **F5/F6/F7** for this harvester.

### [F2/F3] Namespacing — REOPENED 2026-05-17

Earlier lean: harvested files repo-qualified by construction
(`raw/droidoes-docs/<repo>/…`), making collisions impossible. **Reopened** —
the Joseph↔Codex Exchange 3 (`what-is-ontology-for-V1.md` §4) showed that
"flat heap vs. structured tree vs. `raw/` → `sources/` rename vs. vault-as-corpus"
is not an implementation detail: it is the A/B kernel question in disguise. A
structured/quarantined `raw/` presupposes Philosophy A. Blocked until the
kernel question resolves.
