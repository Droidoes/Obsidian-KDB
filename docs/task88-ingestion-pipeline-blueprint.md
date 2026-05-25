# Task #88 — Ingestion System: v0.2 Blueprint

**Status:** **v0.2 — v0.1 holistic review folded** (Codex + Deepseek + Qwen, 2026-05-24). 15 amendments + 2 new work items adopted; 1 new component added (Orchestrator); 5 OQs promoted to decisions. Joseph-ratified 2026-05-25.

**Started:** 2026-05-24 (v0.1)
**v0.2 dated:** 2026-05-25
**Reviewer panel** (per `docs/external-review-panel.md`): Codex + Deepseek + Qwen.
**v0.1 review files:**
- `docs/task88-v0.1-review-codex.md`
- `docs/task88-v0.1-review-deepseek.md`
- `docs/task88-v0.1-review-qwen.md`

**Vocabulary note (D-88-9):** Task #88 is named "Ingestion Pipeline" in `docs/TASKS.md` but is renamed in v0.2 to **"Ingestion System"** to disambiguate from the internal use of "pipeline" for source-producers. The umbrella term used throughout this document is **"Ingestion System"**. Source-producers are called **"feeders"**. "Producer" is reserved for the role defined in the Producer Contract (`docs/graphdb-kdb-producer-contract.md` v1.0) — today, that's `kdb-compile`.

**Lineage:**
- Strategic pivot ratified 2026-05-23 evening — "tunnel from both ends" reframe.
- Path-0 fire (2026-05-23 PM, real-corpus recompile) surfaced #76 Domain dormancy as empirical input.
- 2026-05-24 brainstorm decomposed end-B into 5 components + 1 cross-cutting addition (Pass-2 worth-verdict in end A).
- 2026-05-24 v0.1 fired at external panel; all three reviews returned same day.
- 2026-05-25 v0.2 folds review feedback; adds Component #6 (Orchestrator) from Joseph's substantive engagement during synthesis.

**Anchors:**
- `docs/session-handoff-2026-05-23-saturday-afternoon.md` §Strategic pivot
- Memory `project_tunnel_from_both_ends_pivot`
- Memory `feedback_concrete_first_extract_later`
- Memory `feedback_no_imaginary_risk`
- `docs/graphdb-kdb-producer-contract.md` v1.0 (frozen 2026-05-23)
- `docs/JOURNEY.md`
- `docs/CODEBASE_OVERVIEW.md` §Milestone Changelog
- `docs/external-review-panel.md`

---

## 1. Strategic context

Task #88 was filed 2026-05-23 evening from a strategic pivot at session close. The metaphor: **"tunnel from both ends."** End A (the compile pipeline) has had ~6 weeks of investment and is mature. End B (ingestion) is essentially unstarted.

The pivot: **pause end A architectural development; focus all architectural design effort on end B.** Minor finishing on end A is OK; adding new architectural surface on end A is not — **except** Pass-2 worth-verdict (D-88-5), which is the necessary architectural counterpart to Pass-1 worth-verdict in end B. **Compile and ingestion are two ends of one tunnel; they must meet in the middle.**

End B is positioned as a **platform**, not a single LLM pass: pluggable strategies for multiple source storages (today: manual `.md` drops + the Obsidian vault itself; future: RSS, podcasts, YouTube transcripts, web scrapes, PDFs, emails). Ingestion produces **enriched-source files** that compile consumes as inputs; **compile continues to produce the four Producer Contract artifacts** as before. Ingestion and compile work together seamlessly — there is no bridging component; the seam is the enriched-source file format + filesystem location.

**Frame for v0.2:** decompose end B into components, settle each component independently, then compose the v1 system from settled components. **Concrete-first; abstract-later** (per memory `feedback_concrete_first_extract_later`).

---

## 2. Component decomposition framework

Six components identified through the 2026-05-24 brainstorm + 2026-05-25 v0.1 review synthesis:

| # | Component | Owns | Status in v0.2 |
|---|---|---|---|
| 1 | **Enrichment** | LLM pass per source: property-tags + wikilink suggestions + Pass-1 worth-verdict + domain canonicalization | Outlined (§5.1); criteria + domain list designed in parallel session |
| 2 | **Source Storage** | Where + how sources are stored; what counts as a source; change-detection signals | **Ratified — focus of this blueprint** (§3) |
| 3 | **Trigger** | When enrichment fires (new / change / move / delete detection); event taxonomy + orphan-cascade | Outlined (§5.2); wires up §3.5 signals |
| 4 | **Model selection** | Text-LLM vs graph-LLM vs other | Deferred to v2 |
| 5 | **Move-from-compile** | Which capabilities migrate from end A to end B (systematic compile-survey required) | Outlined (§5.4); domain canonicalization is first concrete |
| 6 | **Orchestrator** | End-to-end pipeline control + GraphDB read-side utilization (NEW per Joseph 2026-05-25) | Outlined (§5.6); v1 minimal scope (script); v2+ for GraphDB utilization; v2/v3 for API |

Plus a cross-cutting surface that lives in end A:

| # | Surface | Owns | Status in v0.2 |
|---|---|---|---|
| — | **Pass-2 worth-verdict** | Compile-side ontology-aware judgment of whether a Pass-1-surviving source contributes to the ontology | Ratified as the **single permitted new end-A architectural surface** (D-88-5), under the "tunnel must meet in the middle" framing |

---

## 3. Source Storage component (ratified)

### 3.1 The architectural insight

The source-storage component is configurable along multiple dimensions. **Two configurations of the same component** are active in v1:

- **Config A — raw-drop:** location = `~/Obsidian/KDB/raw/...`; scope-config = empty for v1
- **Config B — vault-in-place:** location = `~/Obsidian/...`; scope-config excludes circularity dirs + Obsidian config dir

Both are read-in-place on the Obsidian vault. The naming "raw-drop vs vault-in-place" is shorthand for two configurations of one underlying component, not two distinct components.

### 3.2 Six dimensions of source storage

| # | Dimension | Config A (raw-drop) | Config B (vault-in-place) | Class |
|---|---|---|---|---|
| 1 | Location glob | `~/Obsidian/KDB/raw/**/*.md` | `~/Obsidian/**/*.md` | DIFFERS (config) |
| 2 | Access pattern | Read-in-place | Read-in-place | SAME (contingent in v1; may diverge with non-vault sources) |
| 3 | Identity scheme | vault-relative path | vault-relative path | SAME — see §3.2.1 below |
| 4 | Format(s) | `.md` | `.md` | SAME (contingent in v1; may diverge with non-Markdown sources) |
| 5a | Presence detection | filesystem-diff (new / existing / deleted) | filesystem-diff (new / existing / deleted) | SAME |
| 5b | Change detection | content/path/unchanged via tiered signals (§3.5) | content/path/unchanged via tiered signals (§3.5) | SAME |
| 6 | Scope rules (config file) | (empty for v1) | excludes `KDB/raw/*`, `KDB/wiki/*`, `KDB/state/*`, `.obsidian/*` (defense-in-depth) | DIFFERS (config) |

Of 7 sub-dimensions: 5 SAME (some contingently), 2 DIFFER. The two configs are the same component with two configurations.

#### 3.2.1 Identity = vault-relative path (trade-off documented)

Identity = vault-relative path. **Trade-off:** no rename-stability — a moved/renamed file is treated as a new source; the old path is orphaned. The orphan event is handled by Component #3 (Trigger) with cascade depth defined in OQ-88-6.

**Mitigation for cost concern:** for Config B, content-hash is used as a cross-reference key: if a moved file's content-hash matches a known hash at a different path, the system recognizes the move and updates the path in-place rather than re-firing enrichment. See §3.5 config-aware logic.

**Why keep identity-as-path despite the rename concern:**
1. Simplicity — no separate ID system
2. Human-readability — `Investing/Buffett.md` IS the ID; debuggable by eye
3. Filesystem-native — no extra index table
4. Direct alignment with the Producer Contract's `source_id` convention (path-relative)

The hybrid (path-as-identity + content-hash-as-cross-reference for moves) gets the simplicity benefits without the cost-bomb for Config B reorganizations.

### 3.3 Dir-exclusion as a general-purpose capability

Scope-rules config is a config file enumerating dirs to exclude wholesale. v1 use cases:
- **Circularity guard:** Config B excludes `KDB/wiki/*` (compile output)
- **Component-overlap prevention:** Config B excludes `KDB/raw/*` (owned by Config A)
- **Defense-in-depth:** `.obsidian/*` is non-Markdown today but explicitly excluded as a guard against future Markdown-emitting plugins
- **Wholesale knowledge exclusions:** machinery dirs (`KDB/state/*`)
- **Future user-chosen exclusions** of any kind

The capability is **general-purpose**, not circularity-specific. Daily Notes are deliberately NOT excluded — see D-88-11.

### 3.4 Subdirectory semantics

**Config A — gmail-style provenance tags.** Subdirs under `~/Obsidian/KDB/raw/` are typed semantic provenance categories. Examples:
- `~/Obsidian/KDB/raw/YT-transcriptions/` → tag = "YT-transcriptions"
- `~/Obsidian/KDB/raw/substack/` → tag = "substack"
- `~/Obsidian/KDB/raw/Droidoes-projects/` → tag = "Droidoes-projects"

**Source-feeders** (the producers writing into `raw/`) write into their own subdir.

Expected Config A change patterns (Joseph 2026-05-25):
- File-level moves between subdirs: **rare** — treat as re-ingest (provenance tag change)
- Subdir RENAMES: occur (e.g., `raw/YT-transcriptions/` → `raw/youtube/`) — cascade to all files in subdir → re-ingest all
- Subdir ADDITIONS: new feeder → new subdir — first-ingest

**Config B — user-organized vault.** Subdirs reflect the user's own organization (e.g., `Investing/`, `Reading/`). Semantically meaningful but ORGANIZATIONAL, not provenance-tagged. A file moved between dirs may carry semantic intent change OR may be routine reorganization — distinguish via content-hash (§3.5).

**Common implication:** dir-path changes are tracked as semantically significant signals; whether they trigger re-ingestion depends on config-aware logic (§3.5).

### 3.5 Change-detection signals and recompile-trigger logic

Per source, the component tracks metadata used by Component #3 (Trigger):

| Tier | Signal | Cost | Recompile trigger? | Why |
|---|---|---|---|---|
| 1 | file size + mtime | ~free (stat call) | NO — pre-filter only | If unchanged → skip hashing |
| 2 | SHA-256 content hash | ~ms per MB | YES — primary | Authoritative content-change signal |
| 2 | filename change | ~free | YES — re-ingest as new | Usually signals semantic intent change |
| 2 | dir-path change (move) | ~free | YES (Config A) / config-aware (Config B) | See logic below |
| 3 | our last-ingest-time | ~free | NO — for retry/backfill | Our state |
| 3 | source-feeder pipeline ID | ~free | NO — provenance | Metadata for debugging |
| 3 | Pass-1 audit fields | ~free | NO — diagnostic | Confidence, uncertainty_reason, reject_reason, prompt_version, model, schema_version (see §4.1) |

Per-source state schema:
```
{
  size, mtime, sha256, dir-path, filename,
  last-ingest-time, feeder-id,
  pass1: {verdict, confidence, uncertainty_reason, reject_reason,
          prompt_version, model, schema_version}
}
```

Recompile-trigger logic (pseudocode), **config-aware** (per Codex F1 / Deepseek F2 / Qwen F2-F3, with Qwen F2 ordering bug fix):

```
if (size, mtime) == last_seen:
    skip   # cheap pre-filter

elif config == "raw-drop" (Config A):
    # Path changes are provenance-tag changes — always re-ingest
    if (dir-path, filename) != last_seen:
        re-ingest as new (orphan old)
    elif sha256 != last_seen.sha256:
        re-ingest (content change)
    else:
        skip (mtime drift only)

elif config == "vault-in-place" (Config B):
    # Path changes might be reorganization — check content-hash first
    if sha256 == last_seen.sha256 and (dir-path, filename) != last_seen:
        update path in-place; no re-ingest   # move detection
    elif sha256 != last_seen.sha256:
        re-ingest (content change; path-change irrelevant)
    else:
        skip (mtime drift only)
```

**Delete handling** (file no longer present in the watched location) is a separate code path in Component #3, with orphan-cascade depth defined per OQ-88-6.

**Lifecycle event taxonomy** (per Codex F2 / Deepseek F3): `created`, `content_changed`, `path_changed`, `metadata_changed`, `deleted`, `revived`, `excluded`, `unchanged`. Each event has distinct downstream semantics in Component #3.

---

## 4. Two-pass worth-judgment architecture

### 4.1 The flow

```
[any source] ─► [DIR-EXCLUDE GATE] ─► [ENRICHMENT LLM PASS] ─► [PASS-1 GATE] ─► [COMPILE + PASS-2] ─► KDB ontology
                  (config, no LLM)      (Component #1; emits      (filter by              (Compile owns 4 Producer
                                         verdict + domain          Pass-1 verdict)         Contract artifacts;
                                         + tags + wikilinks         + Pass-2 emits
                                         + audit fields)            ontology_contribution)
```

**Pass-1 LLM output** (per source, side-output of enrichment) — schema-gated, archived:

```
{
  verdict: pass | not_pass,                # binary routing (D-88-4)
  confidence: 0.0-1.0,                     # diagnostic — preserves uncertainty signal
  uncertainty_reason: <text or null>,       # diagnostic — why "uncertain → pass"
  reject_reason: <text or null>,            # diagnostic — why "not_pass" (for false-reject audit)
  prompt_version: <semver>,
  model: <model_id>,
  schema_version: <int>,
  domain: <enum from NW-4 canonicalization list>,
  property_tags: [...],
  wikilink_suggestions: [...]
}
```

The diagnostic fields (confidence, uncertainty_reason, reject_reason) preserve the audit signal even though routing is binary — this addresses Codex F4's "binary routing is fine, binary-only observability is not" finding. **All `not_pass` decisions are persisted so false-reject audits are possible later.**

**Pass-2 output** (per source, in compile, archived in sidecar) — schema-gated, per D-88-8:

```
{
  ontology_contribution: pass | not_pass,
  reason: <text>,
  matched_existing_entities: [...],
  new_claims_or_edges_count: <int>
}
```

### 4.2 Pre-LLM ingestion gate = dir-exclusion ONLY

No LLM call is made before enrichment to gate sources. The only pre-enrichment gate is the dir-exclude config (cheap, deterministic).

**Rationale:** the enrichment LLM is already firing per source. Piggybacking the worth-verdict has near-zero marginal cost. A separate cheap-LLM pre-gate would duplicate work without adding context.

**Hedge** (D-88-3, revised v0.2): the trade-off shifts if `vault_candidate_count >= 5,000`. Cost is managed externally by the user (via benchmark rank list, model selection) and is not subject to automated check/balance code in this project — per memory `feedback_no_imaginary_risk`. Failure mode for false-rejects is mitigated by `not_pass` persistence + on-demand sample-audit (no automated cadence).

### 4.3 Pass-1 is binary

Pass-1 emits either `pass` or `not_pass`. Ambiguity ("uncertain whether this source contributes") routes to `pass` — bias to inclusion. Diagnostic fields (§4.1) preserve the uncertainty signal in the audit trail without forcing a third routing tier. Pass-2 (with ontology context) does the more discriminating call.

### 4.4 Pass-2 = the tunnel's middle (D-88-5 expanded)

The 2026-05-23 pivot ratified "pause end A deepening; no new architectural surface on end A." Pass-2 introduces a worth-verdict gate in compile. Joseph ratified this 2026-05-24 as a permitted exception, expanded 2026-05-25 with the tunnel-from-both-ends framing:

> **Compile and ingestion are two ends of one tunnel; they must meet in the middle.** Pass-2 is the meeting point — the ontology-aware judgment that completes the split begun by Pass-1.

Without Pass-2, Pass-1's content-only verdict drives all worth decisions (too narrow). Without Pass-1, compile would re-evaluate every source's worth from scratch (waste). The split is structurally necessary; the meeting is in compile because that's where the ontology context lives.

**D-88-5 exception criteria for future end-A surface additions** (per Codex F7, Deepseek F5, Qwen F8). Future exception OK only if ALL hold:
1. The new end-A surface is the **direct counterpart** of a specific end-B component
2. The end-B component **cannot function correctly without** the end-A surface
3. It **consumes a #88 artifact** (enriched-source file or contract artifact)
4. It is **schema-gated and replayable**
5. It does **not add broad new compile behavior** beyond the named gate

Milestone Changelog entry to add when v0.2 lands: *"2026-05-25 — Tunnel-rule amendment: Pass-2 worth-verdict ratified as the single permitted new architectural surface on end A, per Task #88 (D-88-5). Future end-A exceptions require meeting D-88-5's 5-point criteria."*

---

## 5. Other component outlines

### 5.1 Component #1 — Enrichment (LLM pass)

Per-source LLM call emitting the output schema in §4.1. Open work surfaced this round:

- **NW-1 — Pass-1 criteria.** What does "is this source signal?" actually ask the LLM? Examples: length / coherence / has-named-entities / not-meta-commentary-about-the-vault (this criterion is load-bearing for D-88-11 Daily Notes handling) / domain-relevance. Belongs to Component #1 deep-design.
- **NW-4 — domain canonicalization list.** Predefined list Pass-1 maps to. **Ratified as v0.3 at `docs/task88-nw4-domain-list-v0.3.md` (2026-05-25).** Structural #76 redemption. Per NW-4 D-NW4-1, the flat list has NO sub-domain layer; finer-grained refinement lives in `property_tags`. This blueprint's §4.1 schema reflects that (sub_domain field removed v0.3 commit).
- **NW-5 — Pass-1 benchmark** (new in v0.2 per Joseph 2026-05-25). Corpus with known signal/noise + domain ground truth. Measures verdict accuracy, confidence calibration, domain accuracy, tag quality, wikilink relevance. Likely follows Task #75 / #87 predeclared-eval-criteria pattern.
- **OQ-88-4 (now D-88-10)** — single-call Pass-1 with quality monitor.

### 5.2 Component #3 — Trigger

Wires up the change-detection signals from §3.5 + the lifecycle event taxonomy. Owns:
- Filesystem polling / watching strategy
- Event emission (created / content_changed / path_changed / etc.)
- Orphan-cascade depth on delete events (OQ-88-6)
- Batching of events into enrichment-firing batches (run-boundary decision)

### 5.3 Component #4 — Model selection

Deferred to v2 per Joseph 2026-05-24. v1 assumes text-LLM only.

### 5.4 Component #5 — Move-from-compile

**Discipline:** systematic compile-survey required as a Component #5 deep-design deliverable (per Qwen F10). First concrete: domain extraction (NW-4 v0.3). Other candidates to survey:
- Wikilink resolution logic
- Frontmatter stamping
- Canonicalization (Stage 6)
- Anything else surfaced by the systematic survey

**New work item NW-6 — Pass-2 benchmark enhancement** (new in v0.2 per Joseph 2026-05-25). Extend existing `kdb-benchmark` with ontology-aware verdict accuracy. Reuses #75/#87 mutation-eval framework. Load-bearing for confidence that Pass-2's gate is calibrated correctly.

### 5.5 Source-feeders (deferred from v1 architecture)

Source-feeders are NOT part of v1 architectural design. v1 ships with feeders that already exist informally:

| Feeder | Target | How it writes today |
|---|---|---|
| Manual file drops | Config A (`raw/`) | User drags files |
| Substack-via-gmail | Config A (`raw/substack/`) | Manual extract from gmail |
| Droidoes project mirror | Config A (`raw/Droidoes-projects/`) | Manual or scripted |
| User editing vault notes | Config B (vault-in-place) | Obsidian app |

Adding new feeders post-v1 is a "no-architecture" operation — write to a subdir of `raw/` (Config A) or anywhere in the vault (Config B). The Component #6 Orchestrator (§5.6) provides the entry point that fires the pipeline on whatever feeders have deposited.

### 5.6 Component #6 — Orchestrator (NEW in v0.2)

Per Joseph 2026-05-25: end-to-end orchestrator that moves sources start-to-end + provides other ways of utilizing the GraphDB.

**v1 scope (a) — Thin entry-point script:**
- One command (CLI or script) that fires the full pipeline: detect feeder writes → enrichment → Pass-1 gate → compile → Pass-2 → graph sync
- Initial form: bash or small Python entry point
- Wires existing components (enrichment, kdb-compile, graph sync) into one invocation

**v2+ scope (b) — GraphDB utilization beyond build/populate:**
- Query interfaces (interactive + scripted)
- Analysis operations (M2 link-prediction / M3 community-detection per Round 6 §9.4.3)
- Export / visualization
- Feed-back loop: Analysis ops surface candidates → Promotion Contract (#83/#84) → graph mutations

**v2 or v3 scope (c) — GraphDB API:**
- External API for non-CLI consumers
- Programmatic read-side access
- Likely REST or GraphQL

(b) and (c) are NOT v1; named here so future planning has the architectural placeholder.

---

## 6. v1 scope crystallization

### 6.1 IN v1

1. One source-storage component implementation (config-driven location + scope) — Component #2
2. Two active configurations (Config A raw-drop + Config B vault-in-place)
3. Dir-exclude gate (config-driven, no LLM)
4. Enrichment LLM pass (property tags + wikilinks) — Component #1
5. Pass-1 worth-verdict (binary `pass` / `not_pass`; "uncertain" → `pass`) — embedded in Component #1
6. Pass-1 audit fields (confidence, uncertainty_reason, reject_reason, prompt_version, model, schema_version)
7. Pass-1 gate at compile entry
8. **Pass-2 explicit worth-verdict** mechanism in compile (D-88-8) — emits `{ontology_contribution, reason, matched_existing_entities, new_claims_or_edges_count}` schema-gated, archived in sidecar
9. Domain canonicalization in Pass-1 — NW-4 v0.3 (ratified 2026-05-25)
10. Change-detection signal tracking + config-aware recompile-trigger logic + lifecycle event taxonomy — Component #3
11. Move-from-compile features per Component #5 (domain first concrete; systematic survey required)
12. **Daily Notes IN scope** (D-88-11) — Pass-1 LLM rejects diary-shaped meta-commentary via verdict
13. **Component #6 Orchestrator (v1 minimal scope)** — thin entry-point script

### 6.2 OUT of v1

1. Source-feeder framework design — list informally only
2. Component #4 model selection (text vs graph) — deferred to v2
3. Pre-enrichment LLM gate (we ingest+enrich everything past dir-excludes)
4. Pass-1 → Pass-2 routing of "uncertain" verdict (Pass-1 is binary)
5. Aliases.json operationalization (#74 Path-0 finding — separate concern, out of #88 scope)
6. Component #6 Orchestrator v2+ scope (GraphDB utilization beyond build/populate)
7. Component #6 Orchestrator v2/v3 scope (GraphDB API)
8. Automated cost-tracking watch rules (cost is managed externally per `feedback_no_imaginary_risk`)

---

## 7. Decision log

### D-88-1 — Source-storage decomposition (2026-05-24)

**Decision:** Six base dimensions (§3.2); "raw-drop" and "vault-in-place" are two configurations of the same component (5 of 7 sub-dimensions identical, some contingently).

**Rationale:** Initial framing treated them as distinct platforms. Joseph reframed: both are Obsidian-vault sources at different paths. "One component, two configs" eliminates duplication.

### D-88-2 — Read-in-place for all configurations (2026-05-24)

**Decision:** No copy-into-managed-area pattern. Both configs read sources where they live in the vault.

**Rationale:** Sources already live in the Obsidian vault. Copying creates two-source-of-truth problems and doubles state.

### D-88-3 — Dir-exclusion as the only pre-LLM gate (2026-05-24, revised v0.2)

**Decision:** Ingest+enrich everything past dir-exclusion. No early LLM-gate.

**Rationale:** Enrichment LLM is firing per source anyway. Piggybacking the worth-verdict has near-zero marginal cost.

**v0.2 revisions:**
- Cost trigger removed. Cost is user-managed externally per `feedback_no_imaginary_risk`.
- File-count watch-rule retained: revisit if `vault_candidate_count >= 5,000`.
- All `not_pass` decisions persisted for on-demand false-reject audit (no automated cadence).
- Pass-1 audit fields (D-88-4 + §4.1) preserve diagnostic signal.

### D-88-4 — Two-pass worth-judgment with binary Pass-1 routing + audit fields (2026-05-24, revised v0.2)

**Decision:** Pass-1 (content-only, in enrichment LLM, binary verdict) gates compile entry. Pass-2 (ontology-aware, in compile-LLM) decides ontology contribution. Routing is binary; uncertainty preserved via audit fields.

**v0.2 revision:** Pass-1 schema includes `{confidence, uncertainty_reason, reject_reason, prompt_version, model, schema_version}` per Codex F4. Routing stays binary; observability does not.

### D-88-5 — Pass-2 ratified as the single permitted new end-A surface (2026-05-24, expanded v0.2)

**Decision:** Pivot rule amended — Pass-2 worth-verdict is the **single architectural surface added to end A** as part of #88. Future end-A exception additions require meeting 5-point criteria (§4.4).

**Rationale:** Pass-2 is the **tunnel's middle** — the meeting point between end-A and end-B. The criteria gate prevents the exception from becoming precedent for compile-side expansion.

### D-88-6 — Subdirs in Config A are gmail-style provenance tags (2026-05-24)

**Decision:** Subdirs under `raw/` are semantic provenance categories, not opaque organization.

**Rationale:** Scales better than flat structure. Informs Config A's dir-rename → re-ingest behavior (§3.5).

### D-88-7 — Change-detection state schema + config-aware logic (2026-05-24, revised v0.2)

**Decision:** Per-source state per §3.5 schema. Recompile-trigger logic is config-aware:
- Config A: dir-path change = provenance-tag change → re-ingest as new
- Config B: dir-path change with matching content-hash = reorganization → update path in-place; re-ingest only if content changed

**v0.2 revisions:**
- Pseudocode reordered (Qwen F2 bug fix) — dir-path check no longer short-circuited by SHA-256 match in Config A
- Config-aware branching (Deepseek F3 / Qwen F3) avoids 50-file-reorganization LLM-cost bomb in Config B
- Lifecycle event taxonomy added (Codex F2): `created / content_changed / path_changed / metadata_changed / deleted / revived / excluded / unchanged`

### D-88-8 — Pass-2 mechanism is explicit (2026-05-25, promoted from OQ-88-2)

**Decision:** Compile emits per-source `{ontology_contribution, reason, matched_existing_entities, new_claims_or_edges_count}`. Schema-gated; archived in sidecar.

**Rationale:** Implicit ("zero pages = no contribution") overloads too many states (true no-op vs compile failure vs schema suppression vs prompt weakness vs source duplication). 3/3 reviewers endorsed explicit.

### D-88-9 — Vocabulary (2026-05-25, promoted from OQ-88-1)

**Decision:**
- Task #88 umbrella term = **"Ingestion System"** (used throughout this document)
- Source-producers = **"feeders"**
- Configs = **"source storage configs"**
- **"Producer"** reserved for the role defined in the Producer Contract (today: `kdb-compile`)

**Rationale:** Disambiguates "Ingestion Pipeline" (task name) from internal "pipeline" usage. 3/3 reviewers endorsed (a).

**Implementation:** `docs/TASKS.md` entry for Task #88 updated to "Ingestion System" alongside this v0.2 commit.

### D-88-10 — Single-call Pass-1 with quality monitor (2026-05-25, promoted from OQ-88-4)

**Decision:** Ship single-call enrichment for v1 (one LLM call emits verdict + domain + tags + wikilinks + audit fields). Add structural quality monitor: flag sources where any field is null, empty, or structurally degenerate on non-trivial sources. Predeclared split triggers: if Pass-1 audit accuracy, domain accuracy, or wikilink quality falls below threshold, split into `(verdict + domain)` and `(tags + wikilinks)` calls.

**Rationale:** Splitting upfront doubles cost without empirical evidence of single-call degradation. 3/3 reviewers endorsed single-call-with-monitor.

### D-88-11 — Daily Notes IN scope; Pass-1 LLM rejects via verdict (2026-05-25, promoted from OQ-88-5)

**Decision:** Daily Notes are NOT excluded at scope-config level. They are read by Config B; enrichment LLM processes them; Pass-1 verdict rejects diary-shaped meta-commentary.

**Rationale:** Joseph (2026-05-25): "leave Daily Notes for ingestion... I would like daily notes enhanced by the llm." Consistent with the project's "let LLM decide, not scope-config" philosophy. Scope-config is for hard circularity (KDB/wiki/*) and defense-in-depth (`.obsidian/*`), not knowledge-vs-noise judgment.

**Implication:** NW-1 (Pass-1 criteria) must include "reject vault-meta-commentary (Daily Notes shape, planning shape, meta-reflection shape)" as an explicit criterion.

---

## 8. Open questions

### OQ-88-6 — Orphan-cascade depth (new in v0.2, promoted from reviewer-surfaced OQ)

When a source is orphaned (moved-as-new in Config A, or deleted), how far does the cascade propagate?
- `Source` node only?
- `SUPPORTS` edges from that source?
- `Entity` nodes that lose their last `SUPPORTS`?

Producer Contract's cleanup-event handling (Task #68 pattern) sets precedent. Belongs to Component #3 deep-design.

### OQ-88-7 — Content-hash index for cross-reference (new in v0.2, gated on D-88-7)

Config B's move-detection (matching content-hash at different path → update in-place) requires efficient lookup of `hash → source_id`. Is this:
- A new state index (separate table)?
- A query over the existing per-source state?

Implementation choice; depends on expected vault scale + reorganization frequency.

### OQ-88-8 — Component #6 v1 minimal scope (new in v0.2)

How thin is the v1 orchestrator script?
- Bash one-liner wiring existing CLIs?
- Small Python entry point with config?
- Something richer (status reporting, dry-run, idempotency)?

Belongs to Component #6 deep-design.

---

## 9. Things to consult during continued design

- `docs/graphdb-kdb-producer-contract.md` v1.0 (frozen 2026-05-23) — the existing producer contract end A still owns
- `docs/CODEBASE_OVERVIEW.md` — end-A architectural state + Milestone Changelog
- `docs/JOURNEY.md` — three-iteration retrospective
- `docs/what-is-the-ontology-for.md` §9.4 — Round 6 context for Component #6 (b) scope
- `docs/external-review-panel.md` — reviewer panel composition + flow
- `docs/task83-84-promotion-contract-belief-revision-blueprint.md` — Promotion Contract that consumes Analysis op outputs (Component #6 (b))
- `docs/task87-promotion-belief-revision-eval-criteria-blueprint.md` — predeclared-eval pattern NW-5 + NW-6 will follow

---

## 10. v0.2 amendment summary (for changelog reference)

15 amendments from v0.1 review fold + 1 new component:

| ID | Source | Status | Where in v0.2 |
|---|---|---|---|
| A1 | 3/3 + Joseph reframe | Adopted with reframe | §1 wording corrected; no bridge component |
| A2 | 3/3 | Adopted | §3.2.1 identity trade-off + utility documented |
| A3 | 3/3 | Adopted | §3.2 dim 5 split into 5a/5b + event taxonomy in §3.5 |
| A4 | 3/3, Joseph revised | Adopted with revision | §4.2 hedge; cost-trigger DROPPED |
| A5 | 3/3, Joseph reframed | Adopted with tunnel framing | §4.4 D-88-5 expanded with 5-point criteria |
| A6 | 3/3 | Adopted | D-88-8 (explicit Pass-2) |
| A7 | 3/3 | Adopted | D-88-9 (vocabulary) |
| A8 | 3/3, Joseph + NW-5/NW-6 | Adopted, benchmarks added | D-88-10 + NW-5 + NW-6 |
| A9 | 2/3 | Adopted | §3.5 config-aware logic |
| A10 | 2/3 | Adopted | §3.2 contingent SAME annotations |
| A11 | 1/3 (Codex) | Adopted | §4.1 Pass-1 audit fields + §3.5 state schema |
| A12 | 2/3, Joseph overrode | Adopted with reversal | D-88-11 — Daily Notes IN, LLM rejects |
| A13 | 1/3 (Qwen) | Adopted | §5.4 systematic compile-survey required |
| A14 | 2/3, Joseph overrode | Adopted with reversal | §3.2 dim 6 — `.obsidian/*` KEPT as defense-in-depth |
| A15 | 3/3 | Adopted | OQ-88-6, OQ-88-7 new |
| B1 | Qwen bug catch | Fixed | §3.5 pseudocode reordered + config-aware |
| NEW | Joseph 2026-05-25 | Added | Component #6 Orchestrator (§5.6); OQ-88-8 |
