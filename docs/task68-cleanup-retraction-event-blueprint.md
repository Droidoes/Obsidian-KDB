# Task #68 — Replayable Cleanup/Retraction Event — Blueprint

> **Status:** blueprint for review (Codex pass → TDD plan → subagent-driven implementation).
> **Task:** #68 — `kdb-clean` cleanup is not graph-replayable. **HIGH PRIORITY.**
> **Decision selected:** Option (b) — a typed, replayable cleanup/retraction journal event.

---

## 1. Problem statement

`kdb-clean orphans --apply` retires `orphan_candidate` pages: it archives the
`.md` files and removes the entries from `manifest.json` (`pages{}` + `orphans{}`).
It mutates **manifest state only**. It writes a standalone audit file
(`state/kdb-clean-orphans-audit-<run-id>.json`) but **emits no run journal**.

GraphDB-KDB is independently derived (D34). `graphdb-kdb rebuild` (D39) drops
all Kuzu tables and replays the **compile-history journal stream**
(`state/runs/*.json`) chronologically. The historical compile runs that
*originally emitted* the reaped pages are still in that stream — so on replay,
`ingestor.apply_compile_result` Phase 3 (`_upsert_entity`, a `MERGE`) **re-creates
the reaped entities as active**. The cleanup is invisible to replay.

**Observed (post-`f23c74b` reap of 16 orphans, then `graphdb-kdb rebuild` + `verify`):**

| Class | Count | Cause | In #68 scope? |
|---|---|---|---|
| Reap-residue | 25 | rebuild re-introduces reaped pages — no cleanup journal to replay | **YES — this is #68** |
| Attribute drift | 8 | `compile_count` off-by-one, uniform −1 across all 4 sources | No — see §9 |
| Dead link | 1 | an active page links to a reaped slug (content fix) | No — see §9 |

**Root cause:** the cleanup is a real state transition with no record in the
replayable journal stream. Replay = `compile journals only` ≠ `actual state`.

---

## 2. Why not "just flag the entity" (DELETE-pattern defense)

The codebase has **never deleted a graph node**. `ingestor.py` `_handle_source_deleted`
sets `s.status='deleted'` (a flag); `_detect_and_mark_orphans` sets
`status='orphan_candidate'` (a flag). #68 introduces the first genuine
`DELETE` path. That is deliberate, and flag-only does **not** solve #68:

1. **Flag-only is exactly what is already broken.** The orphan entity is
   *already* flagged `orphan_candidate` in the graph. Replay re-`MERGE`s it back
   to `active` because a later/earlier compile event emits it (`MERGE` overwrites
   the status). A second flag would be overwritten the same way.
2. **The manifest has no page-scoped tombstone.** Page retirement in the manifest
   is *full removal* from `pages{}` + `orphans{}` (verified against
   `assert_manifest_invariants` — tombstones are source-scoped only). A flag-only
   graph would *diverge* from the manifest: manifest has no entry, graph has a
   flagged node. `verify` would still report drift. Only an actual `DELETE`
   converges the graph to the manifest.
3. **Replay re-emission stays correct.** The cleanup event is positioned
   chronologically. If a *later* compile run re-emits a retracted slug, `MERGE`
   correctly re-creates it (the page genuinely came back). If nothing re-emits it,
   it stays deleted. `DELETE` at the cleanup event's position is the right
   primitive — not a flag.

---

## 3. The slug-vs-page_id constraint (Codex)

`kdb-clean` reaps **`page_id`s** (`pages{}` keys, e.g. `wiki/.../foo.md`).
GraphDB-KDB `Entity` nodes are **slug-keyed** (`MERGE (p:Entity {slug: $slug})`).

A reaped page's slug must **not** be deleted from the graph if a *surviving*
(non-reaped) page still carries that slug — the same slug can exist under two
page_types (an active `article` + an orphaned `concept`); a link to it still
resolves. `reap_orphans()` already computes `surviving_slugs` for dead-link
detection.

**Therefore the retraction event carries two lists:**

- **`reaped`** — full page records (`page_id`, `slug`, `page_type`) for every
  reaped page. **Audit fidelity.** Not used for graph deletion.
- **`retracted_slugs`** — `{reaped slugs} − {surviving slugs}`. Only slugs that
  no surviving page provides. **This is the deletion key set.** The graph
  `DETACH DELETE`s `Entity` by these and only these.

`reap_orphans()` gains one line: `retracted_slugs = sorted(reaped_slugs − surviving_slugs)`
in its return dict (the inputs already exist).

---

## 4. This is a producer-contract amendment

`docs/graphdb-kdb-producer-contract.md` describes a single event kind (the
compile run). #68 adds a second. The blueprint **must** amend the contract:

- **§3.3 (run journal):** a journal MAY carry an `event_type` field
  (`"compile"` | `"cleanup"`); **absent ⇒ `"compile"`** (back-compat — existing
  2.0 compile journals are untouched, the compile pipeline is not modified).
- **§3.4 (sidecar archive):** a `cleanup` event's sidecar contains
  `retraction.json` instead of `compile_result.json` + `last_scan.json`.
- **§4 (adapter interface):** `is_eligible` / `load_payload` / `apply` branch on
  `event_type`. `RunDescriptor` is **unchanged** — the discriminator lives in the
  journal JSON (read by `is_eligible`/`load_payload`) and in the retraction
  payload (read by `apply`); the generic rebuilder loop is unchanged.

Raising this to a contract amendment raises the review bar — it must be on the
Codex pass and the contract doc edited in the same implementation arc.

---

## 5. Data shapes

### 5.1 Cleanup run journal — `state/runs/<run_id>.json`

`run_id` = `clean-orphans-<ISO-timestamp>` (the format `kdb-clean` already uses).

```json
{
  "schema_version": "2.1",
  "event_type":     "cleanup",
  "run_id":         "clean-orphans-2026-05-16T08-14-40",
  "started_at":     "2026-05-16T08:14:40-04:00",
  "finished_at":    "2026-05-16T08:14:41-04:00",
  "success":        true,
  "dry_run":        false,
  "summary":        { "reaped_count": 16, "retracted_slug_count": 14, "dead_link_count": 1 },
  "artifacts":      { "retraction_path": "state/runs/<run_id>/retraction.json" }
}
```

- `schema_version: "2.1"` — marks "this stream may contain cleanup events".
  Recommended lean (see §8). Even at `"2.0"` an old adapter is safe (it would
  look for `compile_result.json`, not find it, skip `payload_missing`), but
  `"2.1"` is the honest signal.
- `started_at` is **mandatory and ISO-8601** — the adapter's `_descriptor_keys`
  derives `sort_key` from `started_at`, so the cleanup event interleaves
  chronologically with compile runs. The run_id string `clean-orphans-...`
  would mis-sort lexically against compile run_ids `2026-...` — `sort_key` must
  be the timestamp, never the run_id. `_descriptor_keys` already prefers
  `started_at`; the cleanup journal must supply it.
- **Format:** local-ISO-with-offset (`datetime.now().astimezone().isoformat(timespec="seconds")`)
  — matches what the compile pipeline emits (`local-time-everywhere` memory).
  `kdb_clean.py:131` currently builds the run_id stem with a naive
  `strftime` (no offset); `started_at` must carry the offset so it is
  shape-consistent with compile journals' `started_at`.

### 5.2 Retraction payload (sidecar) — `state/runs/<run_id>/retraction.json`

```json
{
  "event_type":      "cleanup",
  "run_id":          "clean-orphans-2026-05-16T08-14-40",
  "reaped":          [ {"page_id": "...", "slug": "...", "page_type": "..."}, ... ],
  "retracted_slugs": [ "concepts/foo", "concepts/bar", ... ],
  "dead_links":      [ {"from_page": "...", "to_slug": "..."}, ... ]
}
```

`event_type` is duplicated here (journal + payload) intentionally: `is_eligible`
reads the *journal*, `apply` reads the *payload* — different files, each
self-describing.

---

## 6. Code changes

### 6.1 `kdb_compiler/kdb_clean.py`

- `reap_orphans()` return dict gains `retracted_slugs` (one line — `surviving_slugs`
  already computed).
- `_cmd_orphans()` `--apply` path: instead of the standalone
  `kdb-clean-orphans-audit-*.json`, write the **journal** at
  `state/runs/<run_id>.json` and the **retraction sidecar** at
  `state/runs/<run_id>/retraction.json`. The journal *is* the audit record.
- **Write ordering is crash-consistency-critical and must be locked:**
  1. archive the `.md` files
  2. retraction sidecar write — inert until a journal references it
  3. **atomic manifest write** — commits live state
  4. **atomic journal write** — commits replay state
  5. live-sync through the adapter (best-effort, see 6.4)

  Rationale: the journal must never be committed before the manifest — the only
  divergence the §6.5 backfill *cannot* recover is "journal exists, manifest not
  committed" (`rebuild` would delete entities the manifest still claims active).
  The sidecar is written *early* (step 2): it is not replay-visible until the
  journal exists, so writing it before the manifest is harmless, and a crash
  after the manifest but before the journal then leaves the sidecar already in
  place — recovery is just "write the missing journal." The inverse order
  (manifest before sidecar) would leave less structured evidence on that crash.
  The TDD plan locks this: a test that emits the journal before the manifest
  must fail.
- On graph-sync failure (step 5), report it but do not fail the reap — the
  manifest is the source of truth and the graph reconverges on the next
  `rebuild` (the journal from step 4 makes that replay correct).
- Update the `--apply` console NOTE and the module docstring: cleanup is now
  graph-replayable; drop the "#68 known gap" caveat.

### 6.2 `graphdb_kdb/ingestor.py` — new `apply_cleanup`

```python
def apply_cleanup(retraction: dict, run_id: str, *, conn, now=None) -> SyncResult:
    """Retract entities a cleanup run removed. DETACH DELETE Entity by
    retraction['retracted_slugs'] only — never by every reaped slug (§3)."""
```

For each slug in `retracted_slugs`: `MATCH (e:Entity {slug:$slug}) DETACH DELETE e`.
This removes the node and its `LINKS_TO` (both directions) and `SUPPORTS` edges;
`Source` nodes are untouched. Transaction handling mirrors `apply_compile_result`.

**Open implementation detail (resolve in RED test):** Kuzu 0.11 `DETACH DELETE`
support — if unsupported, explicitly delete `LINKS_TO` (in+out) and `SUPPORTS`
edges first, then `DELETE` the node. The TDD plan's first test settles this.

### 6.3 `graphdb_kdb/adapters/obsidian_runs.py` — event routing

- `supported_journal_versions = ["2.0", "2.1"]`.
- `is_eligible`: read `event_type` (default `"compile"`). For `"cleanup"`, the
  `payload_present` check looks for `retraction.json` (not `compile_result.json`
  + `last_scan.json`). An **unknown** `event_type` (neither `"compile"` nor
  `"cleanup"`, e.g. a typo) must NOT fall through to `compile` or
  `payload_missing` — add `"unsupported_event_type"` to the `SkipReason` literal
  and return it, so replay audit names the cause precisely.
- `load_payload`: for `"cleanup"`, load `retraction.json`; return
  `(retraction_payload, {}, run_id)`.
- `apply`: route on `mutation.get("event_type", "compile")` — `"cleanup"` →
  `apply_cleanup`, else → `apply_compile_result`. The rebuilder loop is unchanged.

### 6.4 `graphdb_kdb/adapters/obsidian_runs.py` — `sync_cleanup_run`

New live-sync entry point — `sync_current_run`'s signature is **locked** by
Stage 9 (D-S0) and has no slot for a scan-less cleanup payload:

```python
def sync_cleanup_run(self, retraction: dict, run_id: str,
                     graph_dir: Path | None = None) -> SyncResult:
    """Live-sync a cleanup run (kdb-clean orphans --apply). Opens GraphDB,
    delegates to apply() which routes to apply_cleanup."""
```

Thin — mirrors `sync_current_run`; `apply` does the routing.

### 6.5 Backfill — the already-applied `f23c74b` reap

The 16-orphan reap in `f23c74b` predates #68 and has **no cleanup journal** — so
even after #68 lands, `graphdb-kdb rebuild` will still re-introduce those 16.
One-shot backfill (`scripts/`, dry-run default):

- Read the existing `state/kdb-clean-orphans-audit-clean-orphans-*.json`
  (`reaped`, `dead_links`).
- Compute `retracted_slugs`: a reaped slug is retracted iff no page in the
  **current** (post-reap) `manifest.json` carries it.
- Synthesize the journal (`state/runs/<audit-run-id>.json`) + sidecar
  (`state/runs/<audit-run-id>/retraction.json`) per §5. Derive `started_at` by
  parsing the audit run_id's naive timestamp stem (`clean-orphans-2026-05-16T08-14-40`)
  as local time and re-emitting it with offset — so it is format-consistent with
  §5.1 and sorts after the canonical recompile runs.
- After `--apply`: `graphdb-kdb rebuild` then `verify` — expect the 25
  reap-residue issues to drop to 0.

### 6.6 Contract doc + TASKS.md

- `docs/graphdb-kdb-producer-contract.md` — amend §3.3, §3.4, §4 per §4 above.
- `docs/TASKS.md` — #68 `open` → `done` on completion.

---

## 7. Verification

| Check | Expectation |
|---|---|
| `apply_cleanup` unit | `DETACH DELETE`s only `retracted_slugs`; surviving-slug entity untouched |
| **slug-safe deletion (named RED test)** | orphan `concept` with slug `x` reaped, active `article` with slug `x` survives → graph `Entity {slug:"x"}` is **NOT** deleted |
| adapter routing unit | cleanup journal → `apply_cleanup`; compile journal → `apply_compile_result`; absent `event_type` → compile; unknown `event_type` → skip `unsupported_event_type` |
| `reap_orphans` unit | `retracted_slugs` = reaped−surviving; slug surviving under another type excluded |
| chronological-sort unit | cleanup descriptor sorts by `started_at`, interleaves with compile runs |
| write-order unit | journal emitted before manifest → test fails (§6.1 invariant) |
| end-to-end | `kdb-clean orphans --apply` (fresh fixture) → `graphdb-kdb rebuild` → reap-residue drift = 0 |
| backfill (live) | rebuild + verify: **25 reap-residue → 0**. `verify` is *not* required to reach zero issues — the 8 attribute-drift + 1 dead-link (§9) are out of scope and may remain. Acceptance criterion is **reap-residue drift = 0**, not "verify clean". |
| regression | full suite green (504 baseline) |

---

## 8. Settled leans (no open question — flag only if you disagree)

- **`schema_version: "2.1"`** for cleanup journals; compile journals stay `"2.0"`
  and are not modified; adapter declares `["2.0", "2.1"]`.
- **`event_type` absent ⇒ `"compile"`** — zero change to the compile pipeline.
- **Discriminator in journal + payload, not in `RunDescriptor`** — rebuilder loop
  untouched; routing entirely inside the adapter.
- **`apply_cleanup` in `ingestor.py`** — core owns Cypher (contract §5).
- **Journal replaces the standalone audit file** — the journal is the audit.

---

## 9. Explicitly out of scope

- **Attribute drift (8 issues, `compile_count` −1, uniform across 4 sources).**
  Pre-existing and graph-low — not a #68 regression. Likely cause: some manifest
  `compile_count` increments are not represented by replay-eligible journals,
  consistent with the D39 historical-sidecar eligibility tax (stated as a
  hypothesis, not verified). Recommend a one-line `compile_count` audit during
  implementation; file as **#69** only if it proves a real counter bug rather
  than the expected tax. **Not bundled into #68.**
- **The 1 dead link.** An active page links to a reaped slug — a content fix in
  the source, not a graph-replay defect. `kdb-clean` already *reports* dead
  links; *rewriting* active pages is a separate, also-dry-run-first cleanup mode.

---

## 10. Implementation arc

Blueprint (this doc) → **Codex review** → TDD plan (`docs/task68-*-tasks.md`) →
subagent-driven implementation → final Opus review → live backfill + `rebuild`
+ `verify` convergence → close #68.
