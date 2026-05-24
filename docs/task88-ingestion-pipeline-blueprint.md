# Task #88 — Ingestion Pipeline: v0.1 Checkpoint Blueprint

**Status:** **v0.1 — checkpoint draft.** Source-storage component ratified by Joseph 2026-05-24 pending external review. Other components (enrichment, trigger, model-selection, move-from-compile) outlined but not deep-designed.

**Started:** 2026-05-24
**v0.1 dated:** 2026-05-24
**Reviewer panel** (per `docs/external-review-panel.md`): Codex + Deepseek + Qwen.
**Review files (when fired):**
- `docs/task88-v0.1-review-codex.md`
- `docs/task88-v0.1-review-deepseek.md`
- `docs/task88-v0.1-review-qwen.md`

**Lineage:**
- Strategic pivot ratified 2026-05-23 evening — "tunnel from both ends" reframe.
- Path-0 fire (2026-05-23 PM, real-corpus recompile) surfaced #76 Domain dormancy as empirical input.
- 2026-05-24 brainstorm session decomposed end-B into 5 components + 1 cross-cutting addition (Pass-2 worth-verdict in end A).

**Anchors:**
- `docs/session-handoff-2026-05-23-saturday-afternoon.md` §Strategic pivot
- Memory `project_tunnel_from_both_ends_pivot`
- Memory `feedback_concrete_first_extract_later`
- Memory `feedback_no_imaginary_risk`
- `docs/graphdb-kdb-producer-contract.md` v1.0 (frozen 2026-05-23) — **the existing producer contract this design must align with**
- `docs/JOURNEY.md` (architectural inflection points)
- `docs/CODEBASE_OVERVIEW.md` §Milestone Changelog

---

## 1. Strategic context

Task #88 was filed 2026-05-23 evening from a strategic pivot at session close. The metaphor: **"tunnel from both ends."** End A (the compile pipeline) has had ~6 weeks of investment and is mature (15/15 O1 promotion-contract probes passing; schema v2.2; producer contract v1.0 frozen 2026-05-23). End B (ingestion) is essentially unstarted — files appear in `~/Obsidian/KDB/raw/` by hand; no preprocessing.

Continued deepening of end A has diminishing returns when end B doesn't exist. The pivot: **pause end A architectural development; focus all architectural design effort on end B.** Minor finishing on end A (small bug fixes, the `--force-all` CLI flag) is OK; adding new architectural surface on end A is not — **except** for the single permitted exception in D-88-5 (Pass-2 worth-verdict), which is integral to end B's design.

End B is positioned as a **platform**, not a single LLM pass: pluggable strategies for multiple source storages (today: manual `.md` drops + the Obsidian vault itself; future: RSS, podcasts, YouTube transcripts, web scrapes, PDFs, emails). All sources converge to the artifact shape the existing producer contract consumes.

**Frame for v0.1:** decompose end B into components, settle each component independently, then compose the v1 pipeline. **Concrete-first; abstract-later** (per memory `feedback_concrete_first_extract_later`).

---

## 2. Component decomposition framework

Five components identified through the 2026-05-24 brainstorm:

| # | Component | Owns | Status in v0.1 |
|---|---|---|---|
| 1 | **Enrichment** | LLM pass per source: property-tags + wikilink suggestions + Pass-1 worth-verdict + domain/sub_domain canonicalization | Outlined (§5.1); criteria + domain list designed in parallel session |
| 2 | **Source Storage** | Where + how sources are stored; what counts as a source; change-detection signals | **Ratified pending review — focus of this checkpoint** (§3) |
| 3 | **Trigger** | When enrichment fires (new / change / move detection) | Outlined (§5.2); wires up Component #2's signals |
| 4 | **Model selection** | Text-LLM vs graph-LLM vs other | Deferred to v2 |
| 5 | **Move-from-compile** | Which capabilities migrate from end A to end B | Outlined (§5.4); domain/sub_domain is first concrete |

Plus a sixth surface that emerged from the design but lives in end A:

| # | Surface | Owns | Status in v0.1 |
|---|---|---|---|
| — | **Pass-2 worth-verdict** | Compile-side ontology-aware judgment of whether a Pass-1-surviving source contributes to the ontology | Ratified pending review as the **single permitted new end-A architectural surface** (D-88-5) |

**Vocabulary note** — see OQ-88-1. Task #88 is named "Ingestion Pipeline" but internally we also use "pipeline" for source-producers (e.g., "the YouTube-transcript-fetcher pipeline writes into `raw/YT-transcriptions/`"). Reviewers may want to disambiguate; candidate replacements proposed there.

---

## 3. Source Storage component (ratified pending review)

### 3.1 The architectural insight

The source-storage component is configurable along multiple dimensions. **Two configurations of the same component** are active in v1:

- **Config A — raw-drop:** location = `~/Obsidian/KDB/raw/...`; scope-config = empty for v1
- **Config B — vault-in-place:** location = `~/Obsidian/...`; scope-config = excludes circularity dirs

Both are read-in-place on the Obsidian vault. The naming "raw-drop vs vault-in-place" is shorthand for **two configurations of one underlying component**, not two different components. The initial framing treated them as distinct platforms; Joseph reframed: both are Obsidian-vault sources at different paths.

### 3.2 Six dimensions of source storage

| # | Dimension | Config A (raw-drop) | Config B (vault-in-place) | Same? |
|---|---|---|---|---|
| 1 | Location glob | `~/Obsidian/KDB/raw/**/*.md` | `~/Obsidian/**/*.md` | DIFFERS (config) |
| 2 | Access pattern | Read-in-place | Read-in-place | SAME |
| 3 | Identity scheme | vault-relative path | vault-relative path | SAME |
| 4 | Format(s) | `.md` | `.md` | SAME |
| 5 | Lifecycle | new / change / delete + dir-as-meta | new / change / delete + dir-as-meta | SAME |
| 6 | Scope rules (config file) | (empty for now) | excludes `KDB/raw/*`, `KDB/wiki/*`, `KDB/state/*`, `.obsidian/*`; `Daily Notes/` TBD (OQ-88-5) | DIFFERS (config) |

5 of 6 dimensions are identical across both configurations. Only **Location** and **Scope rules** differ, and both are config knobs.

### 3.3 Dir-exclusion is a general-purpose capability

The scope-rules config is implemented as a config file enumerating dirs to exclude wholesale. v1 use cases:
- **Circularity guard** — Config B must exclude `KDB/wiki/*` (which is compile output)
- **Component-overlap prevention** — Config B must exclude `KDB/raw/*` (owned by Config A)
- **Wholesale knowledge/noise exclusions** — e.g., `.obsidian/*` machinery, possibly `Daily Notes/` (OQ-88-5)
- **Future user-chosen exclusions** of any kind

The capability is **general-purpose**, not circularity-specific. Subsequent reviews should not collapse it to a circularity guard.

### 3.4 Subdirectory semantics

**Config A — gmail-style tags.** Subdirs under `~/Obsidian/KDB/raw/` are treated as **gmail-style tags** — typed semantic provenance categories. Examples:
- `~/Obsidian/KDB/raw/YT-transcriptions/` → tag = "YT-transcriptions"
- `~/Obsidian/KDB/raw/substack/` → tag = "substack"
- `~/Obsidian/KDB/raw/Droidoes-projects/` → tag = "Droidoes-projects"

Source-feeders (the producers writing into `raw/`) write into their own subdir.

**Config B — user-organized semantic.** Subdirs under `~/Obsidian/` are not tags but reflect the user's own organization (e.g., `Investing/`, `Reading/`). Still semantically meaningful: a file moved between dirs likely carries semantic intent change.

**Common implication for both configs:** dir-path changes (a file moving between subdirs, or a subdir rename) are treated as **semantically significant** and trigger re-ingestion — see §3.5 row "dir-path change."

### 3.5 Change-detection signals (Component #3 input)

Per source, the component tracks metadata used by Component #3 (Trigger) to determine when to re-fire enrichment:

| Tier | Signal | Cost | Recompile trigger? | Why |
|---|---|---|---|---|
| 1 | file size + mtime | ~free (stat call) | NO — pre-filter only | If unchanged → skip hashing |
| 2 | SHA-256 content hash | ~ms per MB | YES — primary | Authoritative content-change signal; survives mtime-preserving tools |
| 2 | filename change | ~free | YES — re-ingest as new | Usually signals semantic intent change |
| 2 | dir-path change (move) | ~free | YES (per §3.4) | Subdirs are semantic provenance tags |
| 3 | our last-ingest-time | ~free | NO — for retry/backfill | Our state, not file state |
| 3 | source-feeder pipeline ID | ~free | NO — provenance | Metadata for debugging |

Per-source state schema: `{size, mtime, sha256, dir-path, filename, last-ingest-time, feeder-id}`.

Recompile-trigger logic (pseudocode) — applies to files that **still exist**:
```
if (size, mtime) == last_seen: skip
elif sha256 == last_seen.sha256: skip (mtime drift only)
elif (dir-path, filename) != last_seen: re-ingest as new (orphan old)
else: re-ingest (content change)
```

**Delete handling** (file no longer present in the watched location) is a separate code path in Component #3 (Trigger), not covered by the recompile-trigger pseudocode above. It produces an orphan-event the downstream pipeline reacts to. Deep design of delete-cascade behavior is deferred to Component #3 deep-design.

---

## 4. Two-pass worth-judgment architecture (ratified pending review)

### 4.1 The flow

```
[any source] ─► [DIR-EXCLUDE GATE] ─► [ENRICHMENT LLM PASS] ─► [PASS-1 GATE] ─► [COMPILE + PASS-2] ─► KDB ontology
                  (config, no LLM)      (Component #1; emits      (filter by              (existing pipeline + 
                                         verdict + domain          Pass-1 verdict)         explicit Pass-2 verdict —
                                         + tags + wikilinks)                                see OQ-88-2 for mechanism)
```

**Pass-1 LLM output** (per source, side-output of enrichment):
- `verdict`: `pass` | `not_pass` (binary; "uncertain" → `pass` per §4.3)
- `domain`, `sub_domain`: from predefined canonicalization list (NW-4, designed in parallel session)
- `property_tags`: frontmatter-shape metadata
- `wikilink_suggestions`: footer list of suggested links to other vault notes

**Pass-2:** compile-LLM, with full ontology context, decides whether a Pass-1-surviving source contributes to the ontology. Mechanism options open (OQ-88-2).

### 4.2 Pre-LLM ingestion gate = dir-exclusion ONLY

No LLM call is made before enrichment to gate sources. The only pre-enrichment gate is the dir-exclude config (cheap, deterministic).

**Rationale:** the enrichment LLM is already firing per source for property-tag + wikilink extraction. Piggybacking the worth-verdict on that call has near-zero marginal cost. A separate cheap-LLM pre-gate would duplicate the work without adding context.

**Hedge** (D-88-3): if the vault grows large (5,000+ files) AND LLM cost reverts from current promo pricing, this trade-off shifts. Failure mode is silent — false-rejects in Pass-1 are invisible (we don't know what we missed). Mitigation: periodic sample-audit of `not_pass` verdicts.

### 4.3 Pass-1 is binary

Pass-1 emits either `pass` or `not_pass`. Cases of ambiguity ("uncertain whether this source contributes") map to `pass` — bias to inclusion. Pass-2 (with ontology context) does the more discriminating call.

### 4.4 Pass-2 = the single permitted new architectural surface on end A

The 2026-05-23 pivot ratified "pause end A deepening; minor finishing OK; don't ADD new architectural surface." Pass-2 introduces a worth-verdict gate in compile (before ontology entry). Joseph ratified this 2026-05-24 as a permitted exception, because Pass-2 is the necessary architectural counterpart to Pass-1:
- Pass-1 without Pass-2 would gate on content-only judgment without ontology context.
- Pass-2 without Pass-1 would force compile to re-evaluate every source's worth from scratch (waste).

Milestone Changelog entry to add when this v0.1 lands: *"2026-05-24 — Tunnel-rule amendment: Pass-2 worth-verdict ratified as the single permitted new architectural surface on end A, per Task #88 (D-88-5)."*

---

## 5. Outline of other components (not deep-designed in this checkpoint)

### 5.1 Component #1 — Enrichment (LLM pass)

Per-source LLM call emitting four output classes (§4.1). Open work surfaced this round:
- **NW-1 — Pass-1 criteria.** What does "is this source signal?" actually ask the LLM? Examples of likely criteria: length / coherence / has-named-entities / not-meta-commentary-about-the-vault / domain-relevance. Belongs to Component #1 deep-design.
- **NW-4 — domain/sub_domain canonicalization list.** The predefined list Pass-1 maps to. **Being designed in a parallel session** (this review does not cover its content). This is the structural #76 redemption (#76 Domain field was dormant in production per Path-0 finding; this answers it on the ingestion side, not the compile side).
- **OQ-88-4 — attention dilution hedge.** Cramming four outputs into one LLM call may degrade per-axis quality. Possible split: (verdict+domain) in one call; (tags+wikilinks) in another. Trade-off in OQ-88-4.

### 5.2 Component #3 — Trigger

Mostly mechanical: wires up the change-detection signals from §3.5 into the enrichment-firing logic. No open architectural questions surfaced this round.

### 5.3 Component #4 — Model selection

Deferred to v2 per Joseph 2026-05-24. v1 assumes text-LLM only.

### 5.4 Component #5 — Move-from-compile

Discipline: review compile-side capabilities; identify which migrate to ingestion. First concrete: domain/sub_domain extraction (via NW-4), which closes #76's dormancy on real corpus. Anything else worth moving? See OQ-88-3.

### 5.5 Source-feeders (formerly proposed sub-discussion; deferred from v1)

Source-feeders are the producers that write into the source-storage component (e.g., a YouTube-transcript-fetcher that writes to `raw/YT-transcriptions/`). v1 architectural scope does NOT include a source-feeder framework. v1 ships with the feeders that already exist informally:

| Source-feeder | Target | How it writes today |
|---|---|---|
| Manual file drops | Config A (`raw/`) | User drags files |
| Substack-via-gmail | Config A (`raw/substack/`) | Manual extract from gmail |
| Droidoes project mirror | Config A (`raw/Droidoes-projects/`) | Manual or scripted |
| User editing vault notes | Config B (vault-in-place) | Obsidian app |

Adding new feeders is a "no-architecture" operation post-v1 — they just write to a subdir of `raw/` (Config A) or anywhere under the vault (Config B).

---

## 6. v1 scope crystallization

### 6.1 IN v1

1. One source-storage component implementation (config-driven location + scope) — Component #2
2. Two active configurations (Config A raw-drop + Config B vault-in-place)
3. Dir-exclude gate (config-driven, no LLM)
4. Enrichment LLM pass (property tags + wikilinks) — Component #1
5. Pass-1 worth-verdict (binary `pass` / `not_pass`; "uncertain" → `pass`) — embedded in Component #1
6. Pass-1 gate at compile entry
7. Pass-2 worth-verdict mechanism in compile — see OQ-88-2 for mechanism
8. Domain/sub_domain canonicalization in Pass-1 — NW-4 (parallel session)
9. Change-detection signal tracking — feeds Component #3
10. Move-from-compile features per Component #5 (domain first concrete)

### 6.2 OUT of v1

1. Source-feeder framework design — list informally only
2. Component #4 model selection (text vs graph) — deferred to v2
3. Pre-enrichment LLM gate (we ingest+enrich everything past dir-excludes)
4. Pass-1 → Pass-2 routing of "uncertain" verdict (Pass-1 is binary)
5. Aliases.json operationalization (#74 Path-0 finding — separate concern, out of #88 scope)

---

## 7. Decision log

### D-88-1 — Source-storage decomposition (2026-05-24)

**Decision:** Six dimensions per §3.2; "raw-drop" and "vault-in-place" are two **configurations of the same component** (5/6 dimensions identical).

**Rationale:** Initial framing treated them as distinct platforms requiring distinct code. Joseph reframed: both are Obsidian-vault sources at different paths. "One component, two configs" eliminates duplication and clarifies the abstraction seam.

### D-88-2 — Read-in-place for all configurations (2026-05-24)

**Decision:** No copy-into-managed-area pattern. Both Config A and Config B read sources where they live in the vault.

**Rationale:** Sources already live in the Obsidian vault. Copying creates two-source-of-truth problems and doubles state. Read-in-place + state-tracking-only (file metadata in our DB) is simpler.

### D-88-3 — Dir-exclusion as the only pre-LLM gate (2026-05-24)

**Decision:** Ingest+enrich everything past dir-exclusion. No early LLM-gate.

**Rationale:** Enrichment LLM is firing per source anyway. Piggybacking the worth-verdict has near-zero marginal cost. A separate cheap-LLM gate duplicates work without context.

**Rejected alternatives:**
- Pre-enrichment cheap-LLM gate (tiered gating): duplicates work.
- File-by-file user curation: doesn't scale with vault size.

**Hedge:** if vault grows large AND LLM cost reverts from current promo pricing, revisit. Failure mode is silent (false-rejects invisible). Mitigation: sample-audit of `not_pass` verdicts.

### D-88-4 — Two-pass worth-judgment (2026-05-24)

**Decision:** Pass-1 (content-only, in enrichment LLM, binary verdict) gates compile entry. Pass-2 (ontology-aware, in compile-LLM) decides ontology contribution.

**Rationale:** Splits the worth question by context-availability. Pass-1 has source content but no ontology context; Pass-2 has both. Splitting prevents the early gate from over-pruning (false-rejecting content that fits the ontology).

### D-88-5 — Pass-2 ratified as the only permitted new end-A surface (2026-05-24)

**Decision:** Pivot rule amended — Pass-2 worth-verdict is the **single architectural surface added to end A** as part of #88.

**Rationale:** Without Pass-2, Pass-1's content-only verdict drives all worth decisions — too narrow. Pass-2 is the architectural counterpart that completes the two-pass split. Mechanism details open (OQ-88-2).

### D-88-6 — Subdirs in Config A are gmail-style tags (2026-05-24)

**Decision:** Subdirs under `raw/` (e.g., `raw/YT-transcriptions/`) are semantic provenance categories, not opaque organization.

**Rationale:** Scales better than flat structure (substack vs YT vs project-mirror feeders all coexist). Also informs dir-rename → re-ingest behavior in §3.5.

### D-88-7 — Change-detection state schema (2026-05-24)

**Decision:** Per-source state: `{size, mtime, sha256, dir-path, filename, last-ingest-time, feeder-id}`. Recompile trigger logic per §3.5.

**Rationale:** Tiered signals — cheap pre-filters (size+mtime) avoid hashing; SHA-256 authoritative; dir/filename changes trigger re-ingest because of D-88-6 (semantic tags).

---

## 8. Open questions

### OQ-88-1 — Vocabulary disambiguation

The task name is "Ingestion Pipeline." Internally "pipeline" is also used for source-producers (e.g., "the YouTube-transcript-fetcher pipeline"). Reviewers may want to disambiguate.

Candidates:
- (a) Rename Task #88 umbrella to "Ingestion **System**"; use "**feeders**" for source-producers.
- (b) Keep "Ingestion Pipeline" as task name; use "**feeders**" for source-producers.
- (c) Other.

Lean: (a), with (b) as fallback if "system" feels too generic. Reviewer input welcome.

### OQ-88-2 — Pass-2 mechanism: explicit, implicit, or hybrid?

Three options:
- **Explicit:** compile-LLM emits a verdict field per source (e.g., `contributes_to_ontology: yes/no/why`). Clean signal; new code path in end A.
- **Implicit:** if compile produces zero pages / zero entities from a source, that IS the verdict ("no contribution"). Zero new code surface in end A; less inspectable.
- **Hybrid:** implicit by default + explicit field only for sources whose Pass-1 verdict was on the borderline.

Joseph lean: **explicit** (per D-88-5 framing — treats Pass-2 as a deliberate architectural surface). But the convergence was fast; reviewers may push back. This is a substantive architectural choice.

### OQ-88-3 — Move-from-compile inventory (Component #5)

Domain/sub_domain extraction is the first identified move (NW-4). What else from compile makes sense to migrate to ingestion?
- Frontmatter property-tag extraction?
- Wikilink suggestions?
- Other?

Reviewer input welcome.

### OQ-88-4 — Pass-1 attention dilution hedge

Pass-1 currently crams four outputs into one LLM call: verdict + domain/sub_domain + property_tags + wikilink_suggestions. Risk of attention dilution. Should this split?

- Single call: half the LLM-bill; risk of degraded output quality on each axis.
- Split into two calls (e.g., verdict+domain | tags+wikilinks): doubles LLM-bill; cleaner per-axis quality.

Currently single-call by default. Worth flagging for review.

### OQ-88-5 — Daily Notes scope decision

Daily notes are meta-commentary about KDB itself, not source material. Should Config B exclude them by default?
- If yes: hardcoded in scope-config; user can override.
- If no: Pass-1 verdict will (likely) reject them on content basis; cheap path but burns enrichment LLM tokens.

Touches a deeper "what is knowledge / what is noise" question Joseph deferred to its own discussion within #88.

---

## 9. Things to consult during review

For grounding:
- `docs/graphdb-kdb-producer-contract.md` v1.0 (frozen 2026-05-23) — the existing producer contract end A consumes. **#88's source storage + enrichment together produce the artifacts this contract specifies.** Codex specifically: please cross-check.
- `docs/CODEBASE_OVERVIEW.md` — end-A architectural state + Milestone Changelog
- `docs/JOURNEY.md` — three-iteration retrospective; how the project got to this pivot
- `docs/session-handoff-2026-05-23-saturday-afternoon.md` §Strategic pivot — the original pivot ratification context
- `docs/external-review-panel.md` — reviewer panel composition + review flow
