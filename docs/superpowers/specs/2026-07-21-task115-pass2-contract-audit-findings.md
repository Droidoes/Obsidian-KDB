# Task #115 — Pass-2 contract revision: decisions (ratified)

**Version:** v1.6 (2026-07-21) — RATIFIED product decisions (v1.4, Joseph) +
ratified integration contracts (v1.5, Joseph, after Codex R4) + carve
addendum (v1.6, Joseph, after Codex R12/R13: D-115-11 split; the
reservation/MOVED/durability subsystem moved to #116). This document
is the architecture basis for the #115 blueprint.
**Anchors:** repo `main` @ `7d8263b`; pre-move prompt SHA-256
`dcfa3d1cd9c1e7c543527b5d4357ce46fb9f1e31a766a8127b8565942c11e12a`.

---

## A. Product decisions (v1.4, ratified by Joseph in the §1–§8 walk)

### D-115-1 — Six fields leave the LLM contract

`concept_slugs`, `article_slugs`, top-level `summary_slug`, `outgoing_links`,
`source_name`, `status`. Precise scope (Codex R4 F8): **removed aggregate
projections are not reconstructed** in `CompiledSource` / `compile_result.json`;
Python independently owns operational `status` (stamps `active`), summary
identification (lookup-by-type), and graph-edge derivation (from body
wikilinks). Nothing operational reads the removed aggregates today (verified:
zero refs in `kdb_graph`, orchestrator, page_writer beyond the two summary
lookups below).

- Summary page: stays in `pages[]`, fully model-authored **including its
  slug** (Joseph's (a): uniform "model authors every page slug, gate
  validates the `summary-<stem>` convention" — no prompt-injection exception).
- **Design principle (Joseph):** the LLM contract speaks *wiki* — pages,
  bodies, `[[wikilinks]]` — never system-side projections (no edge lists, no
  runner/manifest jargon).

### D-115-2 — Prompt moves to the repo; provenance = git + two stamps

- New home: `compiler/prompts/KDB-Compiler-System-Prompt.md`;
  `prompt_builder` loads from the package; vault file retired.
- Stamps on every run: `pass2_prompt_version` (human-readable, Pass-1
  precedent) + `pass2_system_prompt_sha256` (loaded text — catches
  dirty-tree edits). The six-component fingerprint set is REJECTED (Joseph:
  unwanted complexity — git is the version control).
- Sequencing: stamps land BEFORE any contract edit.

### D-115-3 — `warnings` → `compilation_notes` (kept, optional); `log_entries` dropped

- Usage evidence: 12/115 cohort sources produced genuinely diagnostic
  strings; load-bearing in the thin-source escape valve. Renamed (content is
  observations; kills the 3-way `warnings` collision; matches "notes about
  this compile"). Optional in schema.
- `log_entries` dropped: write-only journal, no readers, fictitious
  `related_source_ids` injection (`compiler.py:508-511` stamps `[]`).

### D-115-4 — `confidence` deprecated (scope: Entity/page confidence ONLY)

Per-source semantics useless (956 high / 45 medium / 0 low; last-writer-wins
on shared Entity); per-page semantics un-answerable by the model at compile
time (it is a *derived metric* — the parked 2.0 tier holds the design seeds:
OQ-20/OQ-26). **Joseph: "a dimension we don't need."** Scope guard (Codex R4
F4): the parked Claim/Evidence tier's computed-confidence fields
(`kdb_graph/schema.py:116-117`, `core/belief_classifier.py`) are a DISTINCT
design — never touched by this removal.

### D-115-5 — `page_type` kept, required

The model's one earned classification field (concept vs article is NOT
slug-derivable). Consumers: frontmatter, `Entity.page_type`, verifier,
reader-facing distinction.

### D-115-6 — GLM mechanism: no A/B; end-state validation only

List-redundancy stays a supported hypothesis. GLM retired + impractical.
Validation = bundled revision + cohort re-fire on gpt-5.4-mini /
deepseek-v4-flash.

### D-115-7 — Live prompt defects (fix AFTER D-115-2's stamp lands)

Line-1 stray `do youd#`; line 13 "manifest snapshot"; line 209 "aborts the
run".

### D-115-8 — slug-space/source-id-space jargon removal (ratified 2026-07-20)

Prompt §1 paragraph, self-check bullet, schema descriptions.

## B. Integration contracts (v1.5, ratified by Joseph after Codex R4)

### D-115-9 — Canonical collisions: body is absolute authority

`LINKS_TO(final page)` == wikilinks in the final persisted body. Links
present only in losing bodies die with them (they were never wiki-visible).
The `canonicalize.py:410-418` outgoing_links UNION is deleted along with the
field. Cohort validation allows *explained* graph-KPI deltas on
canonical-collision cases — it does not assert KPIs cannot move.

### D-115-10 — Graph owns body→LINKS_TO derivation

`kdb_graph.intake` parses body wikilinks via a small mirrored helper
(AGENTS.md sanctions mirroring small helpers inline; layering invariant
forbids importing `compiler`). For historical payloads containing
`outgoing_links`, the legacy value is preferred (preserves original-run graph
semantics); body derivation is the new-shape path. Compiler and graph parsers
share a fixture corpus (plain/alias/heading/escaped/fenced-code/inline-code/
duplicates/malformed). System test: **final wiki-body wikilinks = live graph
LINKS_TO = rebuilt graph LINKS_TO.**

### D-115-11 — Post-canonicalization summary invariant + executable slug rule

- Exactly one `page_type == "summary"` page before AND after
  canonicalization; summary/non-summary cross-type canonical merges are
  hard-rejected.
- `manifest_writer` / `page_writer` fail CLOSED if lookup-by-type returns
  zero or multiple pages — never silently take the first.
- Executable summary-slug validation: exact algorithm from source filename
  stem (normalization rules, 120-char total budget incl. `summary-` prefix,
  non-ASCII-only stems, empty normalization) — model remains slug author;
  Python validates.
- **SPLIT BY THE v1.8 CARVE (addendum, 2026-07-21):** the original v1.5
  wording also assigned "collisions" to #115. Per the ratified carve:
  **#115 retains** deterministic per-source derivation, exactly-one-summary,
  exact expected-slug validation, underivable-stem rejection,
  post-canonical re-validation, and fail-closed writer lookup;
  **#116 owns** cross-source derived-slug collision detection,
  occupancy/reservation, and lifecycle-aware ownership. The validation
  matrix's collision item moves to #116; #115 keeps local
  length/non-ASCII/empty and exact-match boundary tests only.

### D-115-12 — `Entity.confidence`: logical deprecation now

Stop accepting/writing/querying/verifying/snapshotting/returning it
(intake, verifier, snapshot, queries, `kdb_mcp` `EntityCard`). The dead Kuzu
column stays until the next destructive schema change (no rebuild solely for
one column). North Star D-A2 updated accordingly.

### D-115-13 — Prompt packaging + clean-commit provenance gates

- `pyproject` package-data gains `compiler/prompts/*.md`; an installed-wheel
  smoke test loads the prompt from the built package.
- Cohort attribution sequence: (1) implement + commit stamps, (2) baseline
  run, (3) implement + commit contract revision, (4) comparison run from the
  second clean commit. `measurement_header.json` carries
  `pass2_prompt_version`, `pass2_system_prompt_sha256`, release commit; a
  run with `release_version == "unknown"` or dirty tree is not attributable.

### D-115-14 — Historical artifacts: optional-deprecated read-only fields

Removed fields stay as optional, deprecated, read-only properties in the
aggregate schema (`additionalProperties: false` would otherwise reject
historical `compile_result.json`); new writers never emit them. Old-shape
AND new-shape replay fixtures retained. "Read-compatible" = graph rebuild +
`kdb-validate` of historical sidecars.

### D-115-15 — `ParsedSummary` intentional migration

`warning_count` → `compilation_note_count`; `log_entry_count` and
`source_id_echoed` removed; `summary_slug` derived from the one summary
page; `outgoing_link_count` derived from bodies; loaders tolerant of
historical records. Keeps before/after cohort telemetry comparable.

## C. Target contract shape (post-#115)

```json
{
  "pages": [
    {"slug": "...", "page_type": "summary|concept|article",
     "title": "...", "body": "...with [[wikilinks]]..."}
  ],
  "compilation_notes": ["optional free-text observations"]
}
```

Python owns: source identity (`job.source_id`), `status` (stamps `active`),
link edges (graph derives from body wikilinks), summary identification (the
one `page_type == "summary"` page, fail-closed), persistence/manifest/graph
metadata. Semantic gate: exactly-one-summary (pre + post canonicalization),
executable summary-slug rule, body↔page consistency.

## D. Validation matrix (blueprint test plan input)

- packaged-wheel prompt-load smoke test;
- summary-slug boundary tests (length/non-ASCII/empty + exact-match;
  cross-source COLLISION tests are #116's, per the D-115-11 carve split) +
  post-canonicalization summary gate tests;
- canonical-collision tests pinning losing-body link behavior (D-115-9);
- compiler/graph wikilink-parser parity fixtures (D-115-10);
- live-vs-rebuild LINKS_TO equality for the new body-only payload;
- mixed historical/new journal rebuild tests (D-115-14);
- logical-deprecation tests for confidence across intake/verifier/snapshot/
  MCP (D-115-12);
- full suite green; before/after cohort from clean, distinct commits
  (D-115-13): quarantine/retry/recovery KPIs stable modulo explained
  canonical-collision graph deltas (D-115-9).

## E. Revision changelog

- v1.0–v1.3 — audit + 3 Codex rounds (see prior versions).
- **v1.4** — Joseph's decision walk: D-115-1..8 ratified.
- **v1.5** — Codex R4 (8 findings, verdict "keep product decisions; resolve
  integration contract") absorbed; Joseph ratified D-115-9..15 (all per
  recommended leans: body-authority links, graph-owned derivation, logical
  confidence deprecation, optional-deprecated compat, packaging gates,
  ParsedSummary migration, wording fix).
- **v1.6 (carve addendum, 2026-07-21)** — per blueprint v1.8 (Codex R12 +
  Joseph): the reservation/MOVED/durability subsystem leaves #115 for the
  new **Task #116** (paired with #94). D-115-11 formally split (§B/D-115-11
  above); #115 keeps per-source exactness, #116 owns cross-source
  collision/reservation. Accepted temporary behavior: normalized
  derived-slug collisions keep today's last-writer-wins (wiki) /
  co-ownership (graph) until #116. v1.7 blueprint archived as #116's CANDIDATE design seed at
  `docs/superpowers/specs/2026-07-21-task116-source-lifecycle-design-seed-v1.7.md`.
