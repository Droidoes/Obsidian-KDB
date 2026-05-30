# Task #66 — Compile-Trigger Model: Remove the `error_retry` Kludge

Status: **DONE** (2026-05-16). Codex-reviewed (1 round) → Proceed → implemented TDD (6 commits `160220e`→`0ca91db`, suite 504 green) → Opus final-review **APPROVED** → live migration applied (`task66-migration-2026-05-16T08-14-40`). The `error_retry` kludge is **removed**; compile eligibility is now the single honest comparison `current_hash != last_compiled_hash`, and the manifest can no longer be hand-edited to force a recompile. See D46 in `docs/CODEBASE_OVERVIEW.md` and the #66 row in `docs/TASKS.md`.

---

## 1. Why this exists

`kdb_scan.py` has a side-channel in compile eligibility:

```python
to_compile = {NEW, CHANGED}  ∪  error_retry
# error_retry = UNCHANGED files whose manifest compile_state == "error"
```

This made it possible to **force a recompile by hand-editing `compile_state: "error"`
into `manifest.json`** — which is exactly how EP1 was force-recompiled this session.
That is not acceptable: the manifest must not carry a force-recompile flag, and
`compile_state` must not participate in compile eligibility.

Root cause (verified): `manifest_update.py:311` advances a source's recorded `hash`
during the **scan** (`apply_scan_reconciliation`, the CHANGED branch) — *before* the
compile runs. So `hash` means "last hash **seen**," but the scan reads it back as
"last hash **compiled**." When a compile fails, `hash` was already advanced → the
file reads UNCHANGED next scan despite never being successfully compiled. `error_retry`
is the patch bolted over that conflation.

## 2. Locked design (per the Task #66 spec)

A raw source has **two independent facts**: (1) its current raw-file content hash,
(2) the hash that was last *successfully compiled*. The compile trigger is one
honest comparison:

```text
compile  iff  current_hash != compiled_hash
              (missing compiled_hash ⇒ never successfully compiled ⇒ compiles)
```

| # | current hash vs compiled_hash | result |
|---|---|---|
| 1 | unchanged, current hash already compiled | **skip** |
| 2 | unchanged, current hash not yet compiled  | **compile** |
| 3 | changed, a previous hash was compiled     | **compile** |
| 4 | changed, current hash not compiled        | **compile** |

**Force-recompile policy:** no manifest flag, no `--force`. The only manual force
path is a real source-content change (e.g. add/remove a trailing newline → the
content hash changes). **Content hash only — never mtime** (timestamp churn must
not recompile).

This blueprint does not re-litigate the design; it resolves the four open
sub-questions and details the implementation surface.

## 3. Resolved sub-questions

### Q1 — Field name

| Option | Note |
|---|---|
| `compiled_hash` | shorter |
| **`last_compiled_hash`** ✅ | pairs with the existing `last_compiled_at`, `last_run_id`, `last_seen_at` source fields — the manifest's established `last_*` idiom for "most recent X" |

**Recommendation: `last_compiled_hash`.** It is literally "the hash as of `last_compiled_at`" — the name matches the contents and the sibling fields.

### Q2 — Backfill / migration

Existing manifest source records have no `last_compiled_hash`. If we did nothing,
*every* source would read as "never compiled" and recompile spuriously on the
first post-#66 run. So a one-time backfill is required.

| Option | Note |
|---|---|
| **One-shot migration script** ✅ | `scripts/migrate_task66_compiled_hash.py`, run once, committed for audit trail — matches the Task #64 migration precedent; leaves no `compile_state`-reading logic in the permanent code path |
| Lazy backfill in `ensure_manifest_shape` | embeds a permanent `compile_state → last_compiled_hash` mapping in live code — ironic when the task's whole point is to retire `compile_state` as logic |

**Recommendation: one-shot script.** Backfill rule (as proposed in the spec):
- `compile_state ∈ {compiled, recompiled, metadata_only}` → `last_compiled_hash = hash`
  (the current recorded hash *was* the successfully-compiled one).
- `compile_state == "error"` or anything else → leave `last_compiled_hash` absent
  (never cleanly compiled at the current hash → eligible).

### Q3 — Scan semantics: action vs eligibility

**Recommendation: keep `action` (NEW/CHANGED/UNCHANGED/MOVED) as a pure
content-vs-last-*seen* description; compute `to_compile` independently from the
hash rule.** Action still drives MOVED rename reconciliation and `previous_versions`
— it should not be overloaded with eligibility.

To make eligibility **explicit and verifiable** (not flag-based):

| Option | Note |
|---|---|
| **Add `compiled_hash` to each scan `ScanEntry`** ✅ | the prior `last_compiled_hash` (or null); `to_compile = {f : f.current_hash != f.compiled_hash}` is then a transparent, re-checkable function of two fields on the entry |
| Add a derived `compile_eligible: bool` | more explicit but stores a redundant derived value |

**Recommendation: carry `compiled_hash` on the `ScanEntry`.** Store the input, derive
the decision. An UNCHANGED file may legitimately appear in `to_compile` (case 2) —
but because `current_hash != compiled_hash`, never because of `compile_state`.

**`compiled_hash` is a required-but-nullable field — present on *every* file entry,
typed `"sha256:…" | null`, never absent.** A never-compiled source carries
`compiled_hash: null` explicitly. Making it mandatory (rather than optional) means
`validate_last_scan` can check `to_compile`/`to_skip` deterministically against a
field guaranteed to exist on each entry — "absent" never has to be disambiguated
from "null."

### Q4 — EP1's current state

EP1's `compile_state` is `error` **only because of the manual kludge** — it was in
fact successfully compiled by the 2026-05-14 haiku run, and its recorded `hash` is
that compiled hash. A naive Q2 backfill ("error → no `last_compiled_hash`") would
therefore wrongly mark EP1 never-compiled and auto-recompile it — recompiling off a
stale flag, the exact behavior #66 removes.

**Recommendation:** the migration's **first act** is to revert the kludge — set
EP1's `compile_state` back to `recompiled` (its true state). The uniform Q2 rule
then sets `last_compiled_hash = hash`, leaving EP1 correctly in **skip**. Post-#66,
EP1 recompiles only via a real EP1.md content change — consistent with the
force-recompile policy. (See §8.)

This EP1 revert is a **specific local data repair, not compile-state logic** — it
undoes one hand-edit applied to one source this session. The migration script
performs and logs it as a distinct, labeled one-off step (`# --- EP1 kludge revert
(one-time local repair) ---`), separate from the uniform Q2 backfill loop. No code
path — neither the migration's general loop nor the permanent scanner — ever reads
`compile_state` to make a decision; the value is corrected here purely so the Q2
backfill reads the *true* historical state.

### Q5 — MOVED files and the to_compile / to_skip partition

A MOVED file is a rename: the same content discovered at a new path. If its content
was already compiled, a rename is *not* a recompile trigger — re-running the LLM on
byte-identical content would be waste, and the force-recompile policy says only a
real content change recompiles.

So **`to_compile` / `to_skip` partition purely on the hash rule, never on `action`:**

```text
to_skip    = { every present file : current_hash == last_compiled_hash }
to_compile = { every present file : current_hash != last_compiled_hash }
```

`to_skip` therefore spans **UNCHANGED ∪ MOVED-with-compiled-content** — both are
"a present file whose current hash is already compiled." A MOVED file whose content
*also* changed (rare: rename + edit in one scan interval) lands in `to_compile` by
the same rule, with no special case.

**Rename reconciliation is orthogonal to compile eligibility.** Whether or not a
MOVED file recompiles, `apply_scan_reconciliation` still rekeys its source record
and rewrites the `source_id`/path on its pages' `source_refs` — that path-fixup
runs for every MOVED entry independent of `to_compile` membership. The scan sources
a MOVED entry's `compiled_hash` from the prior source record located at the entry's
`previous_path` (the pre-rename key), exactly as an UNCHANGED entry sources it from
its own key.

### Q6 — Binary / metadata-only sources

A binary source (`is_binary == true`) has no LLM compile step: `planner.eligible_source_ids`
already drops binaries from `CompileJob`s, and `_seed_source_record` stamps them
`compile_state: "metadata_only"`. For a binary, **recording its metadata IS the
complete, successful processing** — there is no second "compile" that could later
advance a hash.

So a binary must get its `last_compiled_hash` set **during scan reconciliation**, not
during compile: `apply_scan_reconciliation` sets `last_compiled_hash = current_hash`
whenever it seeds or updates an `is_binary` source record. A binary therefore lands
in **skip** immediately after its first scan, and re-skips on every later scan unless
the binary's content hash actually changes — identical to the text-source rule.

This is the one place `last_compiled_hash` advances outside `apply_compile_result`,
and it is correct: the metadata recording the scan just did *is* that source's
successful processing. (Pre-existing cosmetic wart: `apply_compile_result` still
error-marks binaries it sees with no job result. That is out of #66 scope and
harmless post-#66 — `compile_state` is informational only, and the binary's
`last_compiled_hash` was already set by the scan, so it stays in skip regardless.)

## 4. Decision — D46

| ID | Decision |
|----|----------|
| **D46** | **Compile eligibility is `current_hash != last_compiled_hash`.** `last_compiled_hash` is a source field advanced **only on successful processing of the current content**: by `apply_compile_result` for LLM-compiled text sources, and by `apply_scan_reconciliation` for metadata-only binaries (whose metadata recording *is* their successful processing — Q6). It is **never** advanced by the scan as a side effect of merely *seeing* a changed text source. `manifest.hash` remains "latest seen raw hash" and must not be read as the compiled hash. `to_compile`/`to_skip` partition purely on `current_hash != last_compiled_hash`, never on `action` (Q5). `error_retry` is removed; `compile_state` stays as an informational field but no longer affects scan eligibility. Force-recompile = real source-content change; no flag, no `--force`. Content hash only, never mtime. |

## 5. Implementation surface

### 5.1 Files touched
- **`kdb_compiler/types.py`** — `ScanEntry` gains `compiled_hash: str | None` as a **required field** (always present on every entry; value is the `sha256:…` string or `null`, never absent — Q3).
- **`kdb_compiler/kdb_scan.py`** — delete `error_retry` (lines 327-343 area); `to_compile`/`to_skip` derived purely from `current_hash != compiled_hash`, never from `action` (Q5); populate `ScanEntry.compiled_hash` on every entry from `prior_sources` (for a MOVED entry, look up the prior record at `previous_path`); the prior-source projection (line ~203) carries `last_compiled_hash` instead of `compile_state`.
- **`kdb_compiler/manifest_update.py`** — `_seed_source_record` adds `last_compiled_hash: None`; `apply_compile_result` sets `rec["last_compiled_hash"] = <compiled source hash>` on each successful per-source LLM compile, and does **not** advance it for error-marked / missing sources. `apply_scan_reconciliation` (a) keeps advancing `hash` (latest seen) unchanged, (b) for `is_binary` sources sets `last_compiled_hash = current_hash` on seed/update — metadata recording is the binary's complete successful processing (Q6), (c) for a MOVED source rekeys the record and rewrites page `source_refs`, independent of `to_compile`.
- **`kdb_compiler/validate_last_scan.py`** — rewrite the `to_compile`/`to_skip` rules around the hash comparison: `to_compile == {f : current_hash != compiled_hash}`, `to_skip` the complement, disjoint, union = files[]. Drop the action-based "UNCHANGED ⇒ to_skip" assertion (an UNCHANGED *or* MOVED file may sit in either set purely by the hash rule — Q5).
- **`scripts/migrate_task66_compiled_hash.py`** (new) — one-shot backfill + EP1 un-kludge (Q2 + Q4).
- **`docs/CODEBASE_OVERVIEW.md`** — D46 ledger entry; amend any scan-pipeline section that describes `error_retry`.
- Tests across `test_kdb_scan.py`, `test_manifest_update.py`, `test_validate_last_scan.py`.

### 5.2 Sequencing
1. Code: `ScanEntry.compiled_hash` + `last_compiled_hash` seed/advance + scan trigger rewrite + `validate_last_scan` rewrite + tests. TDD, full suite green.
2. Commit code; D46 ledger entry.
3. Migration script + dry-run review; `--apply` against the live manifest (backfill + EP1 un-kludge).
4. Verify: a no-op `kdb-compile` scan post-migration classifies all 4 sources `to_skip` (none spuriously recompile).

## 6. Test surface (provisional — finalize in plan)
- Each of the 4 cases in §2 (skip / compile×3) drives `to_compile` membership correctly.
- `error_retry` is gone: a source with `compile_state == "error"` but `current_hash == last_compiled_hash` is **skipped**.
- `last_compiled_hash` advances on a successful compile; does **not** advance for an error-marked / missing source in an otherwise-valid run → that source stays eligible next scan (auto-retry, no flag).
- mtime-only churn (same content hash) → not eligible.
- MOVED file, content unchanged (`current_hash == last_compiled_hash` sourced via `previous_path`) → **to_skip**; its record is still rekeyed and page `source_refs` rewritten (Q5).
- MOVED file, content also changed → **to_compile** by the plain hash rule, no special case.
- Binary source: after first scan its `last_compiled_hash == current_hash` → **to_skip** on every subsequent no-change scan (Q6); a binary content change → eligible.
- Every `ScanEntry` carries `compiled_hash` (string or `null`) — never absent (Q3).
- `validate_last_scan` accepts an UNCHANGED *or* MOVED file in `to_compile` when `current_hash != compiled_hash`; rejects to_compile/to_skip overlap or a misclassified entry.
- Migration: backfill sets `last_compiled_hash` for compiled/recompiled/metadata_only; leaves it absent for error; reverts EP1's `compile_state`.

## 7. Acceptance / closure
- `error_retry` and every `compile_state` read in `kdb_scan.py` are gone.
- Post-migration, a no-op scan recompiles nothing.
- Full `kdb_compiler` suite green.

## 8. Interactions / out of scope
- **EP1's rich page set + Task 6.** Post-#66 EP1 is in "skip." To finally give EP1 its full ontology (the original goal), make a real EP1.md content change → it recompiles (clean, with the #65 fix live) → then the Task #64 migration / Task 6 resumes. That EP1 recompile is deliberately *not* part of #66.
- No change to the prompt, the LLM contract, or `compile_state`'s informational role.
